from __future__ import annotations


import argparse
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable
from textwrap import dedent

AUDIENCE_BRIEF = dedent(
    """
    Audience:
    - Executives at US-based companies with roughly 4-50 employees.
    - Not legally trained; want reliable, accessible tooling.
    - Need to minimise time and money spent on legal activities while staying secure.
    """
).strip()


@dataclass(frozen=True)
class ContentSpec:
    label: str
    summary: str
    structure: str
    tone: str


CONTENT_SPECS: Dict[str, ContentSpec] = {
    "linkedin": ContentSpec(
        label="LinkedIn Post (feed-native, skim-first)",
        summary=dedent(
            """
            Purpose: spark interest and clicks; keep to 90-180 words; conversational, practical, zero jargon.
            Visual guidance: 1200x1200 image or subtle motion graphic with a single product callout.
            Do not create long threads, feature dumps, legalese, or more than one link.
            """
        ).strip(),
        structure=dedent(
            """
            Structure:
            - Hook line (1 short sentence with an outcome).
            - 1-2 tight paragraphs (2-3 lines each) with no text walls.
            - Bulleted mini-list (2-3 benefits) using emojis or dashes.
            - Soft CTA with a single link (no visible UTM parameters): e.g., "See how it works ↓".
            - 2-4 hashtags (e.g., #SmallBusiness #LegalTech #Productivity).
            """
        ).strip(),
        tone="Tone: conversational, practical, zero jargon.",
    ),
    "newsletter": ContentSpec(
        label="Newsletter Email (open + click driver)",
        summary=dedent(
            """
            Purpose: move readers to a next action (trial, demo, or blog). Length 120-180 words.
            Include tracking via UTM parameters and consider testing two subject lines.
            """
        ).strip(),
        structure=dedent(
            """
            Structure:
            - Subject line (≤45 chars): ".
            - Preview text (≤90 chars):.
            - Greeting + 2-sentence intro (job-to-be-done, pain → relief).
            - 3 bullet benefits (results-focused).
            - Primary button CTA:
            - Secondary text link (optional): "Or read the launch post".
            - Footer: reassurance line (reliability/security) + manage preferences.
            Design: single-column, mobile-first layout with large button and image alt text.
            Tone: reassuring, time-saving, clear hierarchy.
            """
        ).strip(),
        tone="Tone: reassuring, time-saving, clear hierarchy.",
    ),
    "blog": ContentSpec(
        label="Blog Post (education + SEO + conversion)",
        summary=dedent(
            """
            Purpose: explain value, build trust, rank for target phrases, and convert.
            Length: 700-1,000 words. Include meta description (150-160 chars) and schema hints (Article) if supported.
            Incorporate key phrases,  and add an internal link to pricing or security.
            """
        ).strip(),
        structure=dedent(
            """
            Structure:
            - Title (benefit-led, ≤60 chars): .
            - Intro: problem → stakes → promise (3-4 sentences).
            - H2: What is the feature? (2-3 short paragraphs).
            - H2: How it works (plain English) with bullet steps (3-5) and one annotated screenshot reference.
            - H2: Where it helps most (use cases: sales/MSAs, NDAs, vendor renewals).
            - H2: Results & proof (2-3 bullets; include a quote/metric if available).
            - H2: Get started (plan availability, setup steps in 3 bullets, CTA button).
            - Optional FAQ: 3 questions (security, accuracy, file types).
            Tone: confident, non-technical; focus on outcomes over internals.
            """
        ).strip(),
        tone="Tone: confident, non-technical; show outcomes, not internals.",
    ),
}

SYSTEM_PROMPT = dedent(
    """
    You are a senior product marketing copywriter. Translate launch research
    about Genie AI's new feature into finished marketing assets tailored
    to the specified channel while respecting word counts, tone, and structure.
    Always prioritise clarity for busy business leaders without legal training.
    """
).strip()


def build_user_instructions(spec: ContentSpec, launch_brief: str) -> str:
    return dedent(
        f"""
        Create a {spec.label} for the following audience.

        {AUDIENCE_BRIEF}

        Requirements:
        {spec.summary}

        {spec.structure}

        {spec.tone}


        Ground everything in the launch brief provided below. Highlight concrete outcomes,
        cite proof when available, and keep the voice channel-appropriate.

        Launch brief:
        {launch_brief}
        """
    ).strip()


def build_payload(content_type: str, launch_brief: str) -> Dict[str, str]:
    key = content_type.lower()
    if key not in CONTENT_SPECS:
        raise ValueError(f"Unknown content type '{content_type}'. Choose from: {', '.join(CONTENT_SPECS)}")
    spec = CONTENT_SPECS[key]
    user = build_user_instructions(spec, launch_brief)
    return {"system": SYSTEM_PROMPT, "user": user}


def print_payload(content_type: str, payload: Dict[str, str]) -> None:
    header = f"## {content_type.upper()} prompt"
    print(header)
    print(f"system = \"\"\"{payload['system']}\"\"\"")
    print(f"user = \"\"\"{payload['user']}\"\"\"")
    print()


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "types",
        metavar="TYPE",
        nargs="*",
        default=list(CONTENT_SPECS.keys()),
        help=f"Content types to generate ({', '.join(CONTENT_SPECS)}).",
    )
    parser.add_argument(
        "-s",
        "--summary-file",
        type=Path,
        help="Path to the launch brief / summary text. Reads stdin when omitted.",
    )
    return parser.parse_args(list(argv) if argv is not None else None)


def load_launch_brief(path: Path | None) -> str:
    if path is not None:
        text = path.read_text(encoding="utf-8")
    else:
        text = sys.stdin.read()
    launch_brief = text.strip()
    if not launch_brief:
        raise ValueError("Launch brief input is empty. Provide summary text via --summary-file or stdin.")
    return launch_brief


def main(argv: Iterable[str] | None = None) -> None:
    args = parse_args(argv)
    try:
        launch_brief = load_launch_brief(args.summary_file)
    except Exception as exc:  # pragma: no cover - CLI convenience
        sys.stderr.write(f"Error loading launch brief: {exc}\n")
        raise SystemExit(1) from exc
    for content_type in args.types:
        payload = build_payload(content_type, launch_brief)
        print_payload(content_type, payload)


if __name__ == "__main__":
    main()


__all__ = [
    "AUDIENCE_BRIEF",
    "CONTENT_SPECS",
    "build_payload",
    "load_launch_brief",
    "print_payload",
    "main",
]
