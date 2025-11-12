from __future__ import annotations
from pathlib import Path
from datetime import datetime
from typing import Dict

def save_markdown_outputs(summary_output: str, assets: Dict[str, str], output_dir: str = "outputs") -> Path:
    """
    Save all generated marketing assets (summary + channel content) into a single Markdown file.

    Args:
        summary_output (str): The unified launch brief or summarised text.
        assets (Dict[str, str]): A dictionary containing channel outputs, e.g.
                                 {"linkedin": "...", "newsletter": "...", "blog": "..."}.
        output_dir (str): Directory to save the Markdown file (default: "outputs").

    Returns:
        Path: Path object of the saved Markdown file.
    """

    # Ensure output directory exists
    out_dir = Path(output_dir)
    out_dir.mkdir(exist_ok=True)

    # Build filename with timestamp
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
    md_output = out_dir / f"GenieAI_Marketing_Outputs_{timestamp}.md"

    # Build Markdown content
    content = f"""# Genie AI – Feature Launch Marketing Outputs
_Generated: {datetime.now():%Y-%m-%d %H:%M}_

---

## Unified Launch Brief
{summary_output}

---

## LinkedIn Post
{assets.get('linkedin', '⚠️ LinkedIn post not found.')}

---

## Newsletter Email
{assets.get('newsletter', '⚠️ Newsletter email not found.')}

---

## Blog Post
{assets.get('blog', '⚠️ Blog post not found.')}
"""

    # Write file
    md_output.write_text(content, encoding="utf-8")

    print(f"✅ Saved Markdown to {md_output.resolve()}")
    return md_output


if __name__ == "__main__":
    # Example usage (for standalone testing)
    dummy_assets = {
        "linkedin": "LinkedIn example post here.",
        "newsletter": "Newsletter content example here.",
        "blog": "Blog post example here."
    }
    save_markdown_outputs("Example summary text.", dummy_assets)