# Feature Release Marketing Toolkit

Utilities and prompts for turning raw source documents about Genie AI's **Document Compare** feature into launch-ready marketing assets.

## Repo overview

- `docs_in/` – drop any DOCX/PDF sources here; ingestion automatically picks up every file.
- `ingest.py` – lightweight DOCX/PDF ingestion helpers used by the notebook and CLI tools.
- `summarise.py` – exposes functions for collating sources and producing a comprehensive launch brief prompt.
- `generate.py` – builds OpenAI Chat Completions payloads for LinkedIn, newsletter, and blog posts using a launch brief as input.
- `pipeline.py` – runs ingestion → summary → asset generation from the CLI (writes outputs to `outputs/`).
- `api.py` – FastAPI server exposing summary/asset endpoints for Zapier, n8n, etc.
- `marketing-workflow.ipynb` – notebook where you orchestrate ingestion, summarisation, and generation.
- `outputs/` – optional dumping ground for generated assets (ignored by Git).

## Prerequisites

- Python 3.10+
- `pypdf` (for PDF extraction)
- `openai` (for Responses API access in `pipeline.py` or notebooks)
- `python-docx` (for exporting Markdown drafts to Word)

```bash
python -m pip install pypdf openai
```

> The DOCX parser is implemented via `zipfile` + `xml.etree`, so no extra dependency is required.

## Typical workflow

1. **Ingest** – Either open the notebook or run `python ingest.py`. This reads every DOCX/PDF inside `docs_in/`, returning a list of `{name, text}` objects for further processing.
2. **Summarise** – In the notebook, call `from summarise import collate_sources, build_prompt` to generate the comprehensive launch brief (or run `python summarise.py`). Paste that prompt into OpenAI to produce the structured summary.
3. **Generate assets** – Once you have the Markdown launch brief, feed it into `generate.py` (or the helper function inside your notebook) to produce channel-specific prompts and generate the copy with OpenAI.
4. **Pipeline (optional)** – Use `pipeline.py` to automate steps 1–3 and save the resulting Markdown files to `outputs/`.

## CLI usage

### Build a launch-brief prompt
```bash
python summarise.py > launch-brief-prompt.txt
```
Paste the resulting `system`/`user` strings into OpenAI to generate `launch_brief.md`.

### Generate channel prompts from an existing launch brief
```bash
cat launch_brief.md | python generate.py linkedin newsletter
```
By default the script emits prompts for all supported types (`linkedin`, `newsletter`, `blog`).

### Run the full pipeline end-to-end
```bash
export OPENAI_API_KEY=sk-...
python pipeline.py --summary-model gpt-4o-mini --asset-model gpt-4o-mini
```
This will:
1. Ingest every file in `docs_in/`.
2. Ask OpenAI to produce the launch brief, show you a preview, and (if approved) write it to `outputs/launch_brief.md` (override via `--summary-output`).
3. Generate LinkedIn, newsletter, and blog drafts; each preview pauses for approval before saving to `outputs/<type>.md`.

Common flags:
- `linkedin newsletter` – limit asset generation to specific channels.
- `--summary-input existing_brief.md` – skip the summary call and reuse a saved brief (still requires approval unless `--auto-approve`).
- `--dry-run` – print the prompts without calling OpenAI.
- `--auto-approve` – skip all approval prompts (useful for CI once you're confident in the flow).
- `--preview-chars 600` – increase/decrease how much text is shown in each approval gate.

### Serve the HTTP API (for Zapier/n8n integrations)
```bash
export OPENAI_API_KEY=sk-...
uvicorn api:app --host 0.0.0.0 --port 8000
```
Endpoints:
- `GET /health` – readiness check.
- `POST /summary` – generate a launch brief from the latest sources.
- `POST /assets` – create specific assets from an existing brief.
- `POST /pipeline` – run summary + asset generation in one call (or pass `launch_brief` to skip the summary stage).

Each endpoint accepts optional overrides for models, temperatures, token limits, and requested asset types. Provide an `api_key` field in the payload to override the `OPENAI_API_KEY` environment variable if needed.

## Notebook helpers

Inside `marketing-workflow.ipynb`:

```python
from ingest import ingest_documents
from summarise import collate_sources, build_prompt
from generate import build_payload

# 1. Load docs
docs, lookup = ingest_documents()

# 2. Summarise into a launch brief via OpenAI (using build_prompt)
summary_prompt = build_prompt()
# ...send to OpenAI, capture the resulting markdown as `summary_output`

# 3. Generate assets from the launch brief
payload = build_payload("linkedin", summary_output)
```

Refer to `generate.py` for a convenience `generate_asset()` pattern that wraps OpenAI’s API client.

### Convert Markdown outputs to Word docs

Use the helpers in `export.py` once you have Markdown drafts:

```python
from export import markdown_to_docx, markdown_file_to_docx

# Convert in-memory Markdown
markdown_to_docx(assets["newsletter"], "outputs/newsletter.docx", title="Newsletter Draft")

# Or convert an existing .md file (writes outputs/launch_brief.docx)
markdown_file_to_docx("outputs/launch_brief.md")
```

## Testing

- `python summarise.py | head`
- `python generate.py linkedin -s launch_brief.md | head`

## Notes

- Keep the raw documents inside `docs_in/` up to date; rerun ingestion whenever they change.
- The launch brief is the single source of truth for `generate.py`. Update the brief before regenerating marketing copy.
- If you modify helper modules after importing them in the notebook, restart the kernel or `importlib.reload(...)` to pick up the changes.
