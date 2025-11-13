from __future__ import annotations

from dotenv import load_dotenv

"""Run the full marketing asset pipeline from the command line."""

import argparse
import os
import sys
from pathlib import Path
from typing import Dict, Iterable, List, Optional
from uuid import uuid4
import markdown as md

import requests
from dotenv import load_dotenv

from generate import CONTENT_SPECS, build_payload
from summarise import build_prompt
from approvals import ApprovalStore
from slack_helpers import SlackNotifier
from email_helpers import send_email, markdown_to_text, prep_email_with_openai

load_dotenv()

import dotenv
load_dotenv()

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None


DEFAULT_TYPES: List[str] = list(CONTENT_SPECS.keys())


def create_client(api_key: str | None) -> OpenAI:
    if OpenAI is None:
        raise RuntimeError("openai package is not installed. Run `python -m pip install openai`. ")
    key = api_key or os.getenv("OPENAI_API_KEY")
    if not key:
        raise RuntimeError("Set OPENAI_API_KEY or pass --api-key to run the pipeline.")
    return OpenAI(api_key=key)


def run_summary(
    client: OpenAI,
    *,
    model: str,
    temperature: float,
    max_tokens: int,
) -> str:
    payload = build_prompt()
    response = client.responses.create(
        model=model,
        instructions=payload["system"],
        input=[{"role": "user", "content": payload["user"]}],
        temperature=temperature,
        max_output_tokens=max_tokens,
    )
    return response.output_text.strip()


def run_assets(
    client: OpenAI,
    *,
    content_types: Iterable[str],
    launch_brief: str,
    model: str,
    temperature: float,
    max_tokens: int,
) -> Dict[str, str]:
    outputs: Dict[str, str] = {}
    for content_type in content_types:
        payload = build_payload(content_type, launch_brief)
        response = client.responses.create(
            model=model,
            instructions=payload["system"],
            input=[{"role": "user", "content": payload["user"]}],
            temperature=temperature,
            max_output_tokens=max_tokens,
        )
        outputs[content_type] = response.output_text.strip()
    return outputs


def save_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.strip() + "\n", encoding="utf-8")


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "types",
        metavar="TYPE",
        nargs="*",
        default=DEFAULT_TYPES,
        help=f"Content types to generate ({', '.join(DEFAULT_TYPES)}).",
    )
    parser.add_argument("--api-key", help="OpenAI API key (defaults to OPENAI_API_KEY env)")
    parser.add_argument("--summary-model", default="gpt-4o-mini", help="Model for the launch brief step")
    parser.add_argument("--asset-model", default="gpt-4o-mini", help="Model for asset generation")
    parser.add_argument("--summary-temperature", type=float, default=0.3)
    parser.add_argument("--asset-temperature", type=float, default=0.5)
    parser.add_argument("--summary-max-tokens", type=int, default=2000)
    parser.add_argument("--asset-max-tokens", type=int, default=1400)
    parser.add_argument(
        "--summary-input",
        type=Path,
        help="Path to an existing launch brief (skip summary generation)",
    )
    parser.add_argument(
        "--summary-output",
        type=Path,
        help="Where to save the generated launch brief (default outputs/launch_brief.md)",
    )
    parser.add_argument(
        "--assets-dir",
        type=Path,
        default=Path("outputs"),
        help="Directory for generated asset files (default: outputs/)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print prompts without calling OpenAI.",
    )
    parser.add_argument(
        "--auto-approve",
        action="store_true",
        help="Skip interactive approval and save all drafts automatically.",
    )
    parser.add_argument(
        "--preview-chars",
        type=int,
        default=2000,
        help="Number of characters to show during approval previews (default: 3000)",
    )

    parser.add_argument(
        "--slack-webhook-url",
        help="Slack incoming webhook URL (falls back to SLACK_WEBHOOK_URL env)",
    )
    parser.add_argument(
        "--slack-approvals",
        action="store_true",
        help="Require Slack-based approvals (needs bot token + signing endpoint)",
    )
    parser.add_argument("--slack-bot-token", help="Slack bot token for interactive approvals")
    parser.add_argument("--slack-channel-id", help="Slack channel ID for approval messages")
    parser.add_argument(
        "--approvals-db",
        type=Path,
        help="Location of the approvals SQLite DB (default outputs/approvals.db)",
    )
    parser.add_argument(
        "--approval-timeout",
        type=int,
        default=900,
        help="Seconds to wait for Slack approval before timing out (default 900)",
    )
    parser.add_argument(
        "--approval-poll-interval",
        type=float,
        default=5.0,
        help="Seconds between approval status checks",
    )
    parser.add_argument(
        "--approval-timeout-fallback",
        action="store_true",
        help="Fallback to local prompt if Slack approval times out",
    )
    parser.add_argument(
        "--send-newsletter-email",
        action="store_true",
        help="Email the approved newsletter draft automatically",
    )
    parser.add_argument(
        "--email-to",
        default="tansenmatt@gmail.com",
        help="Comma-separated list of recipient emails for newsletter send",
    )
    parser.add_argument("--email-from", help="From email address for newsletter send")
    parser.add_argument("--smtp-host", help="SMTP host for newsletter send")
    parser.add_argument(
        "--smtp-port",
        type=int,
        help="SMTP port (defaults to 587 when TLS, 465 when SSL)",
    )
    parser.add_argument("--smtp-username", help="SMTP username")
    parser.add_argument("--smtp-password", help="SMTP password / app token")
    parser.add_argument(
        "--smtp-use-tls",
        action="store_true",
        help="Use STARTTLS (set false to use implicit SSL)",
    )
    parser.add_argument(
        "--email-openai-model",
        default="gpt-4o-mini",
        help="Model to use when extracting subject/body from newsletter Markdown",
    )
    parser.add_argument(
        "--email-system-prompt",
        default="You turn newsletter Markdown into a clean email",
        help="System prompt passed to OpenAI when preparing the email",
    )
    return parser.parse_args(list(argv) if argv is not None else None)


def request_approval(
    *,
    label: str,
    text: str,
    auto_approve: bool,
    preview_chars: int,
) -> bool:
    if auto_approve:
        return True
    preview = text[:preview_chars]
    ellipsis = "..." if len(text) > preview_chars else ""
    print(f"====== {label.upper()} PREVIEW ({len(preview)} chars) ======")
    print(preview + ellipsis + "\n")
    while True:
        choice = input(f"Approve {label}? [y/N]: ").strip().lower()
        if choice in {"y", "yes"}:
            return True
        if choice in {"", "n", "no"}:
            return False
        print("Please respond with 'y' or 'n'.")


def print_prompts(types: Iterable[str]) -> None:
    summary_payload = build_prompt()
    print("# SUMMARY PROMPT")
    print(f"system = \"\"\"{summary_payload['system']}\"\"\"")
    print(f"user = \"\"\"{summary_payload['user']}\"\"\"\n")
    dummy_brief = "(launch brief goes here)"
    for content_type in types:
        payload = build_payload(content_type, dummy_brief)
        print(f"# {content_type.upper()} PROMPT")
        print(f"system = \"\"\"{payload['system']}\"\"\"")
        print(f"user = \"\"\"{payload['user']}\"\"\"\n")




def get_slack_webhook(arg_value: Optional[str]) -> Optional[str]:
    return arg_value or os.getenv("SLACK_WEBHOOK_URL")


def notify_slack(
    webhook_url: Optional[str],
    *,
    title: str,
    body: str,
    preview_chars: int,
) -> None:
    if not webhook_url:
        return
    preview = body[:preview_chars].strip()
    if len(body) > preview_chars:
        preview += "…"
    safe_preview = preview.replace("```", "`​``")
    payload = {
        "text": f"*{title}*\n```{safe_preview}```",
    }
    try:
        response = requests.post(webhook_url, json=payload, timeout=10)
        response.raise_for_status()
    except Exception as exc:  # pragma: no cover
        print(f"Warning: failed to notify Slack ({exc}). Continuing without Slack alert.")


def setup_slack_approvals(
    *,
    enabled: bool,
    assets_dir: Path,
    db_path: Optional[Path],
    bot_token: Optional[str],
    channel_id: Optional[str],
) -> tuple[Optional[ApprovalStore], Optional[SlackNotifier], Optional[str]]:
    if not enabled:
        return None, None, None
    token = bot_token or os.getenv("SLACK_BOT_TOKEN")
    channel = channel_id or os.getenv("SLACK_CHANNEL_ID")
    if not token or not channel:
        raise RuntimeError("Slack approvals requested but bot token or channel ID missing")
    store_path = db_path or (assets_dir / "approvals.db")
    store = ApprovalStore(store_path)
    notifier = SlackNotifier(token, channel)
    return store, notifier, str(uuid4())


def request_slack_decision(
    *,
    store: ApprovalStore,
    notifier: SlackNotifier,
    run_id: str,
    label: str,
    item_id: str,
    text: str,
    preview_chars: int,
    timeout: int,
    poll_interval: float,
    auto_fallback: bool,
    auto_approve: bool,
) -> bool:
    if auto_approve:
        return True
    store.upsert_item(run_id=run_id, item_id=item_id, title=label, body=text)
    ts = notifier.post_draft(
        run_id=run_id,
        item_id=item_id,
        title=label,
        body=text,
        preview_chars=preview_chars,
    )
    store.attach_slack_refs(run_id=run_id, item_id=item_id, slack_ts=ts, channel=notifier.channel or "")
    record = store.wait_for_status(
        run_id=run_id,
        item_id=item_id,
        timeout=timeout,
        poll_interval=poll_interval,
    )
    status = (record or {}).get("status")
    if status == "approved":
        return True
    if status == "rejected":
        approver = (record or {}).get("approver_name") or (record or {}).get("approver_id") or "reviewer"
        print(f"{label} rejected by {approver}. Regenerate and rerun.")
        return False
    if auto_fallback:
        print("Slack approval timed out; falling back to local prompt.")
        return request_approval(
            label=label,
            text=text,
            auto_approve=auto_approve,
            preview_chars=preview_chars,
        )
    raise RuntimeError(
        f"Timed out waiting for Slack approval of {item_id}. Rerun with --approval-timeout-fallback to prompt locally."
    )


def parse_recipients(raw: str | None) -> list[str]:
    if not raw:
        return []
    return [addr.strip() for addr in raw.split(",") if addr.strip()]


def resolve_email_settings(args: argparse.Namespace) -> Optional[dict[str, object]]:
    if not args.send_newsletter_email:
        return None
    host = args.smtp_host or os.getenv("SMTP_HOST")
    username = args.smtp_username or os.getenv("SMTP_USERNAME")
    password = args.smtp_password or os.getenv("SMTP_PASSWORD")
    sender = args.email_from or os.getenv("EMAIL_FROM")
    raw_recipients = args.email_to or os.getenv("EMAIL_TO")
    recipients = parse_recipients(raw_recipients)
    if not (host and sender and recipients):
        raise RuntimeError(
            "Newsletter email requested but SMTP_HOST, EMAIL_FROM, or recipients missing."
        )
    use_tls = args.smtp_use_tls or os.getenv("SMTP_USE_TLS", "true").lower() in {"1", "true", "yes"}
    port = args.smtp_port
    if port is None:
        port = 587 if use_tls else 465
    return {
        "host": host,
        "port": port,
        "username": username or os.getenv("SMTP_USERNAME"),
        "password": password or os.getenv("SMTP_PASSWORD"),
        "use_tls": use_tls,
        "sender": sender,
        "recipients": recipients,
    }


def main(argv: Iterable[str] | None = None) -> None:
    args = parse_args(argv)

    if args.dry_run:
        print_prompts(args.types)
        return

    client = create_client(args.api_key)
    slack_webhook = get_slack_webhook(args.slack_webhook_url)
    slack_store, slack_notifier, slack_run_id = setup_slack_approvals(
        enabled=args.slack_approvals and not args.auto_approve,
        assets_dir=args.assets_dir,
        db_path=args.approvals_db,
        bot_token=args.slack_bot_token,
        channel_id=args.slack_channel_id,
    )
    email_settings = resolve_email_settings(args)

    def slack_preview(title: str, body: str, *, full: bool = False) -> None:
        if slack_webhook:
            preview_chars = len(body) if full else args.preview_chars
            notify_slack(
                slack_webhook,
                title=title,
                body=body,
                preview_chars=preview_chars,
            )

    def approve(label: str, item_id: str, text: str) -> bool:
        if args.auto_approve:
            return True
        if slack_store and slack_notifier and slack_run_id:
            return request_slack_decision(
                store=slack_store,
                notifier=slack_notifier,
                run_id=slack_run_id,
                label=label,
                item_id=item_id,
                text=text,
                preview_chars=args.preview_chars,
                timeout=args.approval_timeout,
                poll_interval=args.approval_poll_interval,
                auto_fallback=args.approval_timeout_fallback,
                auto_approve=args.auto_approve,
            )
        return request_approval(
            label=label,
            text=text,
            auto_approve=args.auto_approve,
            preview_chars=args.preview_chars,
        )

    if args.summary_input:
        launch_brief = args.summary_input.read_text(encoding="utf-8").strip()
        slack_preview("Launch brief (existing)", launch_brief, full=args.preview_chars == -1)
        if not approve("launch brief (existing)", "launch-brief", launch_brief):
            print("Launch brief not approved. Exiting without saving drafts.")
            return
    else:
        launch_brief = run_summary(
            client,
            model=args.summary_model,
            temperature=args.summary_temperature,
            max_tokens=args.summary_max_tokens,
        )
        slack_preview("Launch brief draft", launch_brief, full=args.preview_chars == -1)
        if not approve("launch brief", "launch-brief", launch_brief):
            print("Launch brief not approved. Exiting without saving drafts.")
            return
        summary_path = args.summary_output or args.assets_dir / "launch_brief.md"
        save_text(summary_path, launch_brief)
        print(f"Saved launch brief to {summary_path}")

    if not launch_brief:
        raise RuntimeError("Launch brief is empty. Provide --summary-input or allow summary generation.")

    assets = run_assets(
        client,
        content_types=args.types,
        launch_brief=launch_brief,
        model=args.asset_model,
        temperature=args.asset_temperature,
        max_tokens=args.asset_max_tokens,
    )

    for content_type, text in assets.items():
        slack_preview(f"{content_type.title()} draft", text, full=args.preview_chars == -1)
        approved = approve(f"{content_type} draft", content_type, text)
        if approved:
            path = args.assets_dir / f"{content_type}.md"
            save_text(path, text)
            print(f"Saved {content_type} asset to {path}")
            if content_type == "newsletter" and email_settings:
                subject, prepared_body = prep_email_with_openai(
                    client=client,
                    model=args.email_openai_model,
                    system_prompt=args.email_system_prompt,
                    newsletter_markdown=text,
                )
                html_body = md.markdown(prepared_body)
                send_email(
                    smtp_host=email_settings["host"],
                    smtp_port=email_settings["port"],
                    username=email_settings["username"],
                    password=email_settings["password"],
                    use_tls=email_settings["use_tls"],
                    subject=subject,
                    body=html_body,
                    sender=email_settings["sender"],
                    recipients=email_settings["recipients"],
                )
                print("Newsletter emailed to", ", ".join(email_settings["recipients"]))
        else:
            print(f"{content_type} draft not approved. Skipping save.")


if __name__ == "__main__":
    main()
