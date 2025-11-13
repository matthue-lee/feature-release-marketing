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
- `requests` (for Slack notifications in the CLI pipeline)
- `slack-sdk` (for interactive Slack approvals)
- `pandoc` (optional; improves Markdown→plain-text conversion for newsletter emails)

```bash
python -m pip install -r requirements.txt
```

> The DOCX parser is implemented via `zipfile` + `xml.etree`, so no extra dependency is required.

## Typical workflow

1. **Ingest** – Either open the notebook or run `python ingest.py`. This reads every DOCX/PDF inside `docs_in/`, returning a list of `{name, text}` objects for further processing.
2. **Summarise** – In the notebook, call `from summarise import collate_sources, build_prompt` to generate the comprehensive launch brief (or run `python summarise.py`). Paste that prompt into OpenAI to produce the structured summary.
3. **Generate assets** – Once you have the Markdown launch brief, feed it into `generate.py` (or the helper function inside your notebook) to produce channel-specific prompts and generate the copy with OpenAI.
4. **Pipeline (optional)** – Use `pipeline.py` to automate steps 1–3 and save the resulting Markdown files to `outputs/`.

## CLI usage

### Environment variables / .env

Both the CLI and FastAPI server automatically load values from a `.env` file (via `python-dotenv`). Create `.env` in the repo root with entries like:

```
OPENAI_API_KEY=sk-...
SLACK_BOT_TOKEN=xoxb-...
SLACK_SIGNING_SECRET=...
SLACK_CHANNEL_ID=C12345678
EMAIL_FROM=bot@example.com
EMAIL_TO=tansenmatt@gmail.com
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=bot@example.com
SMTP_PASSWORD=app-password
SMTP_USE_TLS=true
```

Adjust as needed; these become defaults for `pipeline.py` and `uvicorn api:app` so you don’t need to export them manually.

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
4. (Optional) Post launch brief + drafts to Slack for review when `SLACK_WEBHOOK_URL` or `--slack-webhook-url` is configured.
5. (Optional) Require Slack button approvals (`--slack-approvals`) so reviewers can approve/deny directly inside Slack before files are written.

Common flags:
- `linkedin newsletter` – limit asset generation to specific channels.
- `--summary-input existing_brief.md` – skip the summary call and reuse a saved brief (still requires approval unless `--auto-approve`).
- `--dry-run` – print the prompts without calling OpenAI.
- `--auto-approve` – skip all approval prompts (useful for CI once you're confident in the flow).
- `--preview-chars 600` – increase/decrease how much text is shown in each approval gate.
- `--slack-webhook-url https://hooks.slack.com/...` – push each draft preview to Slack before the approval prompt (or set `SLACK_WEBHOOK_URL`).
- `--slack-approvals --slack-channel-id C123 --slack-bot-token xoxb-...` – send interactive Slack messages with Approve/Request Changes buttons and wait for responses (requires the FastAPI server to expose `/slack/actions`).
- `--approval-timeout 900 --approval-timeout-fallback` – control how long to wait for Slack responses and whether to fall back to local prompts if reviewers are idle.
- `--approvals-db custom/path.db` – share the approval store between the CLI and API if you prefer a different location (also set `APPROVALS_DB=...` for the API).
- `--send-newsletter-email --email-to you@example.com --email-from bot@yourdomain.com --smtp-host smtp.example.com --smtp-username ... --smtp-password ... --smtp-use-tls` – automatically email the newsletter draft to the specified recipients once it’s approved (env vars `EMAIL_TO`, `EMAIL_FROM`, `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_USE_TLS` can provide defaults).

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
- `POST /slack/actions` – Slack interactivity callback endpoint (configure this URL in your Slack app for button approvals).

### Slack Approvals

1. Create a Slack app with the `chat:write` scope and enable **Interactivity & Shortcuts**.
2. Set the Request URL to `https://<your-host>/slack/actions` (served by `uvicorn api:app`).
3. Save the bot token and signing secret as `SLACK_BOT_TOKEN` and `SLACK_SIGNING_SECRET` (and optionally `SLACK_CHANNEL_ID`).
4. Run the CLI with `--slack-approvals` (plus the token/channel flags or env vars). Each draft posts to Slack with Approve/Request Changes buttons, and the pipeline waits for a button click before saving.
5. Make sure the API and CLI share the same approvals database (`APPROVALS_DB` / `--approvals-db`, default `outputs/approvals.db`).

### Automatic Newsletter Email

Set your SMTP credentials and recipients as env vars or CLI flags, then run the pipeline with `--send-newsletter-email`. When the newsletter draft is approved (locally or via Slack), the CLI sends the final copy to the configured inbox (defaults to `tansenmatt@gmail.com`). Example:

```bash
export SMTP_HOST=smtp.gmail.com
export SMTP_USERNAME=bot@example.com
export SMTP_PASSWORD=app-password
export EMAIL_FROM=bot@example.com
python pipeline.py --send-newsletter-email --smtp-use-tls --email-to you@example.com
```

The helper uses STARTTLS by default (port 587). Disable `--smtp-use-tls` to use implicit SSL (port 465). If you leave `--email-to` unset, it defaults to `tansenmatt@gmail.com`.
For the cleanest plain-text email body, install Pandoc so the Markdown newsletter is converted via `pandoc -f markdown -t plain` before sending (falls back to a regex converter if pandoc is unavailable).
Before sending, the CLI also calls OpenAI to extract the `subject` and final message body from the newsletter Markdown (fields such as `Subject:` or `Preview:` inside `newsletter.md`). Override the model/prompt with `--email-openai-model` and `--email-system-prompt` if needed.

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
- Slack approvals require a Slack app with `chat:write` + Interactivity enabled. Set `SLACK_BOT_TOKEN`, `SLACK_SIGNING_SECRET`, and `SLACK_CHANNEL_ID`, point the app’s Request URL to `/slack/actions`, and run `uvicorn api:app ...` so Slack can reach the endpoint.
- Ensure the FastAPI server and CLI share the same approvals database (default `outputs/approvals.db`, configurable via `--approvals-db` and `APPROVALS_DB`).
