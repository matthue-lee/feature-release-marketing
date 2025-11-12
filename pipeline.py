from __future__ import annotations

"""Run the full marketing asset pipeline from the command line."""

import argparse
import os
import sys
from pathlib import Path
from typing import Dict, Iterable, List

from generate import CONTENT_SPECS, build_payload
from summarise import build_prompt

try:  # Optional until user actually runs the pipeline
    from openai import OpenAI
except ImportError:  # pragma: no cover - handled at runtime
    OpenAI = None  # type: ignore


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
        default=400,
        help="Number of characters to show during approval previews (default: 400)",
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


def main(argv: Iterable[str] | None = None) -> None:
    args = parse_args(argv)

    if args.dry_run:
        print_prompts(args.types)
        return

    client = create_client(args.api_key)

    if args.summary_input:
        launch_brief = args.summary_input.read_text(encoding="utf-8").strip()
    else:
        launch_brief = run_summary(
            client,
            model=args.summary_model,
            temperature=args.summary_temperature,
            max_tokens=args.summary_max_tokens,
        )
        approved = request_approval(
            label="launch brief",
            text=launch_brief,
            auto_approve=args.auto_approve,
            preview_chars=args.preview_chars,
        )
        if not approved:
            print("Launch brief not approved. Exiting without saving drafts.")
            return
        summary_path = args.summary_output or args.assets_dir / "launch_brief.md"
        save_text(summary_path, launch_brief)
        print(f"Saved launch brief to {summary_path}")

    if not launch_brief:
        raise RuntimeError("Launch brief is empty. Provide --summary-input or allow summary generation.")

    if args.summary_input and not request_approval(
        label="launch brief (existing)",
        text=launch_brief,
        auto_approve=args.auto_approve,
        preview_chars=args.preview_chars,
    ):
        print("Launch brief not approved. Exiting without saving drafts.")
        return

    assets = run_assets(
        client,
        content_types=args.types,
        launch_brief=launch_brief,
        model=args.asset_model,
        temperature=args.asset_temperature,
        max_tokens=args.asset_max_tokens,
    )

    for content_type, text in assets.items():
        approved = request_approval(
            label=f"{content_type} draft",
            text=text,
            auto_approve=args.auto_approve,
            preview_chars=args.preview_chars,
        )
        if approved:
            path = args.assets_dir / f"{content_type}.md"
            save_text(path, text)
            print(f"Saved {content_type} asset to {path}")
        else:
            print(f"{content_type} draft not approved. Skipping save.")


if __name__ == "__main__":
    main()
