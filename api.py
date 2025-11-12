from __future__ import annotations

"""FastAPI surface for running the marketing pipeline via HTTP."""

from typing import Dict, List, Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from generate import CONTENT_SPECS
from pipeline import DEFAULT_TYPES, create_client, run_assets, run_summary

APP_DESCRIPTION = (
    "Expose the Feature marketing pipeline via HTTP so tools like Zapier "
    "or n8n can trigger summaries and channel-specific assets on demand."
)

app = FastAPI(
    title="Feature Marketing API",
    description=APP_DESCRIPTION,
    version="0.1.0",
)


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
