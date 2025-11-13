from __future__ import annotations

"""FastAPI surface for running the marketing pipeline via HTTP."""

import hashlib
import hmac
import json
import os
import time
import urllib.parse
from pathlib import Path
from typing import Dict, List, Optional

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, Field
from dotenv import load_dotenv

from approvals import ApprovalStore
from generate import CONTENT_SPECS
from pipeline import DEFAULT_TYPES, create_client, run_assets, run_summary
from slack_helpers import SlackNotifier

load_dotenv()

APP_DESCRIPTION = (
    "Expose the Feature marketing pipeline via HTTP so tools like Zapier "
    "or n8n can trigger summaries and channel-specific assets on demand."
)

BASE_DIR = Path(__file__).resolve().parent
OUTPUTS_DIR = BASE_DIR / "outputs"
OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
DEFAULT_APPROVALS_DB = str((OUTPUTS_DIR / "approvals.db").resolve())

app = FastAPI(
    title="Feature Marketing API",
    description=APP_DESCRIPTION,
    version="0.1.0",
)

env_approvals_db = os.getenv("APPROVALS_DB")
if not env_approvals_db:
    env_approvals_db = DEFAULT_APPROVALS_DB
APPROVALS_DB = Path(env_approvals_db)
SLACK_SIGNING_SECRET = os.getenv("SLACK_SIGNING_SECRET")
SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN")
approval_store = ApprovalStore(APPROVALS_DB)


class SummaryOptions(BaseModel):
    summary_model: str = Field(
        default="gpt-4o-mini", description="OpenAI model to use for the launch brief"
    )
    summary_temperature: float = Field(
        default=0.3, ge=0.0, le=2.0, description="Temperature for the launch brief call"
    )
    summary_max_tokens: int = Field(
        default=2000, gt=0, description="Max tokens for the launch brief response"
    )


class SummaryRequest(SummaryOptions):
    api_key: Optional[str] = Field(
        default=None,
        description="Optional OpenAI API key (falls back to OPENAI_API_KEY env variable)",
    )


class SummaryResponse(BaseModel):
    launch_brief: str


class AssetOptions(BaseModel):
    types: Optional[List[str]] = Field(
        default=None,
        description="Subset of assets to generate (default: linkedin, newsletter, blog)",
    )
    asset_model: str = Field(
        default="gpt-4o-mini", description="OpenAI model for asset generation"
    )
    asset_temperature: float = Field(
        default=0.5, ge=0.0, le=2.0, description="Temperature for asset generation"
    )
    asset_max_tokens: int = Field(
        default=1400, gt=0, description="Max tokens for each asset response"
    )


class AssetRequest(AssetOptions):
    launch_brief: str = Field(..., description="Launch brief markdown feeding the assets")
    api_key: Optional[str] = Field(
        default=None,
        description="Optional OpenAI API key (falls back to OPENAI_API_KEY env variable)",
    )


class AssetResponse(BaseModel):
    assets: Dict[str, str]


class PipelineRequest(SummaryOptions, AssetOptions):
    launch_brief: Optional[str] = Field(
        default=None,
        description="Provide to skip summary generation and only create assets",
    )
    api_key: Optional[str] = Field(
        default=None,
        description="Optional OpenAI API key (falls back to OPENAI_API_KEY env variable)",
    )


class PipelineResponse(BaseModel):
    launch_brief: str
    assets: Dict[str, str]


@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "ok"}


def _validate_types(types: Optional[List[str]]) -> List[str]:
    if not types:
        return list(DEFAULT_TYPES)
    normalized = []
    for raw in types:
        key = raw.lower()
        if key not in CONTENT_SPECS:
            raise HTTPException(status_code=400, detail=f"Unknown content type '{raw}'")
        normalized.append(key)
    return normalized


def _verify_slack_signature(*, body: bytes, timestamp: str, signature: str) -> bool:
    if not SLACK_SIGNING_SECRET:
        return False
    try:
        ts = int(timestamp)
    except (TypeError, ValueError):  # pragma: no cover
        return False
    if abs(time.time() - ts) > 60 * 5:
        return False
    basestring = f"v0:{timestamp}:{body.decode()}".encode()
    digest = hmac.new(SLACK_SIGNING_SECRET.encode(), basestring, hashlib.sha256).hexdigest()
    expected = f"v0={digest}"
    return hmac.compare_digest(expected, signature)


@app.post("/summary", response_model=SummaryResponse)
def api_summary(payload: SummaryRequest) -> SummaryResponse:
    try:
        client = create_client(payload.api_key)
        launch_brief = run_summary(
            client,
            model=payload.summary_model,
            temperature=payload.summary_temperature,
            max_tokens=payload.summary_max_tokens,
        )
    except Exception as exc:  # pragma: no cover - runtime errors surfaced via HTTP
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return SummaryResponse(launch_brief=launch_brief)


@app.post("/assets", response_model=AssetResponse)
def api_assets(payload: AssetRequest) -> AssetResponse:
    types = _validate_types(payload.types)
    if not payload.launch_brief.strip():
        raise HTTPException(status_code=400, detail="launch_brief cannot be empty")
    try:
        client = create_client(payload.api_key)
        assets = run_assets(
            client,
            content_types=types,
            launch_brief=payload.launch_brief,
            model=payload.asset_model,
            temperature=payload.asset_temperature,
            max_tokens=payload.asset_max_tokens,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return AssetResponse(assets=assets)


@app.post("/pipeline", response_model=PipelineResponse)
def api_pipeline(payload: PipelineRequest) -> PipelineResponse:
    types = _validate_types(payload.types)
    try:
        client = create_client(payload.api_key)
        launch_brief = payload.launch_brief
        if not launch_brief:
            launch_brief = run_summary(
                client,
                model=payload.summary_model,
                temperature=payload.summary_temperature,
                max_tokens=payload.summary_max_tokens,
            )
        elif not launch_brief.strip():
            raise HTTPException(status_code=400, detail="launch_brief cannot be empty")
        assets = run_assets(
            client,
            content_types=types,
            launch_brief=launch_brief,
            model=payload.asset_model,
            temperature=payload.asset_temperature,
            max_tokens=payload.asset_max_tokens,
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return PipelineResponse(launch_brief=launch_brief, assets=assets)


@app.post("/slack/actions")
async def slack_actions(request: Request) -> Dict[str, str]:
    if not SLACK_SIGNING_SECRET:
        raise HTTPException(status_code=500, detail="SLACK_SIGNING_SECRET not configured")
    body = await request.body()
    timestamp = request.headers.get("X-Slack-Request-Timestamp", "")
    signature = request.headers.get("X-Slack-Signature", "")
    if not _verify_slack_signature(body=body, timestamp=timestamp, signature=signature):
        raise HTTPException(status_code=400, detail="Invalid Slack signature")
    payload_map = urllib.parse.parse_qs(body.decode())
    raw_payload = payload_map.get("payload", [None])[0]
    if not raw_payload:
        raise HTTPException(status_code=400, detail="Missing payload")
    data = json.loads(raw_payload)
    action = (data.get("actions") or [{}])[0]
    try:
        value = json.loads(action.get("value", "{}"))
    except json.JSONDecodeError as exc:  # pragma: no cover
        raise HTTPException(status_code=400, detail="Invalid action payload") from exc
    run_id = value.get("run_id")
    item_id = value.get("item_id")
    decision = value.get("action")
    if not run_id or not item_id or decision not in {"approve", "reject"}:
        raise HTTPException(status_code=400, detail="Incomplete approval payload")
    status = "approved" if decision == "approve" else "rejected"
    approver = data.get("user", {})
    approval_store.update_status(
        run_id=run_id,
        item_id=item_id,
        status=status,
        approver_id=approver.get("id"),
        approver_name=approver.get("name") or approver.get("username"),
    )
    if SLACK_BOT_TOKEN:
        channel = data.get("channel", {}).get("id")
        ts = data.get("message", {}).get("ts")
        if channel and ts:
            notifier = SlackNotifier(SLACK_BOT_TOKEN, channel)
            notifier.update_message(
                channel=channel,
                ts=ts,
                status=status,
                approver=approver.get("name") or approver.get("username"),
            )
    status_text = "Approval recorded" if status == "approved" else "Changes requested"
    return {"response_action": "clear", "text": status_text}
