from __future__ import annotations

"""Slack helper utilities for posting drafts and updating messages."""

import json
from typing import Optional

from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError


class SlackNotifier:
    def __init__(self, token: str, channel: str | None = None):
        self.client = WebClient(token=token)
        self.channel = channel

    def _safe_preview(self, text: str, preview_chars: int) -> str:
        preview = text[:preview_chars].strip()
        if len(text) > preview_chars:
            preview += "…"
        return preview.replace("```", "`\u200b``")

    def post_draft(
        self,
        *,
        run_id: str,
        item_id: str,
        title: str,
        body: str,
        preview_chars: int,
    ) -> str:
        if not self.channel:
            raise ValueError("SlackNotifier.channel is required for posting drafts")
        preview = self._safe_preview(body, preview_chars)
        payload = {"run_id": run_id, "item_id": item_id}
        blocks = [
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"*{title}*\n```{preview}```"},
            },
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "Approve"},
                        "style": "primary",
                        "value": json.dumps({"action": "approve", **payload}),
                    },
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "Request changes"},
                        "style": "danger",
                        "value": json.dumps({"action": "reject", **payload}),
                    },
                ],
            },
        ]
        response = self.client.chat_postMessage(
            channel=self.channel,
            text=f"{title} (approval needed)",
            blocks=blocks,
        )
        return response["ts"]

    def update_message(
        self,
        *,
        channel: str,
        ts: str,
        status: str,
        approver: Optional[str] = None,
    ) -> None:
        status_text = "Approved" if status == "approved" else "Changes requested"
        status_emoji = "✅" if status == "approved" else "✋"
        subtitle = f"{status_text} by {approver}" if approver else status_text
        try:
            self.client.chat_update(
                channel=channel,
                ts=ts,
                text=f"{status_text}",
                blocks=[
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": f"{status_emoji} *{status_text}*\n{subtitle}",
                        },
                    }
                ],
            )
        except SlackApiError as exc:  # pragma: no cover
            print(f"Warning: failed to update Slack message: {exc}")


__all__ = ["SlackNotifier"]
