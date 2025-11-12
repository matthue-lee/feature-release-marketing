from __future__ import annotations

"""Utilities for collating task documents and building a summary prompt."""

from typing import Dict, List, Sequence
from textwrap import dedent

from ingest import ingest_documents

SYSTEM_PROMPT = dedent(
    """
    You are an expert product marketing manager preparing launch enablement for the
    new feature. Synthesise source material, resolve conflicts, and
    highlight anything that still needs answers. Always cite which source informed
    each section when uncertainty exists.
    """
).strip()

USER_TASK = dedent(
    """
    Summarise and collate every relevant detail from the provided sources to produce
    a launch-ready brief with these sections:
      1. Executive summary (2-3 sentences)
      2. Customer insights (pain points, desired outcomes)
      3. Product & engineering details (scope, status, differentiators, blockers)
      4. Messaging pillars & proof points (3 concise bullets)
      5. Launch risks / open questions (bullet list)
      6. Recommended next steps for Marketing, Product, and Engineering
    Be concise but thorough. Quote critical metrics or statements verbatim when
    they materially strengthen the narrative.
    """
).strip()


def collate_sources() -> List[Dict[str, str]]:
    """Return docs with source identifiers for downstream notebook use."""
    docs, _ = ingest_documents()
    return [
        {
            "source_id": f"Source {idx}",
            "name": doc["name"],
            "text": doc["text"],
        }
        for idx, doc in enumerate(docs, start=1)
    ]


def format_sources(sources: Sequence[Dict[str, str]] | None = None) -> str:
    """Human-readable blob of labeled sources."""
    if sources is None:
        sources = collate_sources()
    chunks = []
    for item in sources:
        chunks.append(f"{item['source_id']}: {item['name']}\n{item['text']}\n")
    return "\n".join(chunks).strip()


def build_prompt(sources: Sequence[Dict[str, str]] | None = None) -> Dict[str, str]:
    """Return the system/user strings for an OpenAI Chat Completions call."""
    if sources is None:
        sources = collate_sources()
    return {
        "system": SYSTEM_PROMPT,
        "user": f"{USER_TASK}\n\nSources:\n{format_sources(sources)}",
    }


def main() -> None:
    payload = build_prompt()
    print("# OpenAI Chat Completions payload")
    print(f"system = \"\"\"{payload['system']}\"\"\"")
    print(f"user = \"\"\"{payload['user']}\"\"\"")


if __name__ == "__main__":
    main()


__all__ = [
    "SYSTEM_PROMPT",
    "USER_TASK",
    "collate_sources",
    "format_sources",
    "build_prompt",
]
