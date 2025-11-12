from __future__ import annotations

"""Helpers for ingesting task documents into notebook-friendly objects."""

import re
from pathlib import Path
from typing import Dict, Iterable, List, Sequence, Tuple
from xml.etree import ElementTree as ET
from zipfile import ZipFile

from pypdf import PdfReader

BASE_DIR = Path(__file__).resolve().parent / "docs_in"
SUPPORTED_SUFFIXES = {".docx", ".pdf"}
WORD_NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}


def _resolve(path: Path | str, base_dir: Path) -> Path:
    return path if isinstance(path, Path) else base_dir / path


def _humanize_name(path: Path) -> str:
    name = re.sub(r"[\-_]+", " ", path.stem).strip()
    return name if name else path.stem


def _discover_files(base_dir: Path) -> List[Path]:
    if not base_dir.exists():
        raise FileNotFoundError(f"Docs directory not found: {base_dir}")
    files = [
        p
        for p in sorted(base_dir.iterdir())
        if p.is_file()
        and p.suffix.lower() in SUPPORTED_SUFFIXES
        and not p.name.startswith("~$")
    ]
    if not files:
        raise FileNotFoundError(
            f"No DOCX/PDF files found in {base_dir}. Drop sources into this folder and retry."
        )
    return files


def read_docx(filename: str | Path, *, base_dir: Path = BASE_DIR) -> str:
    """Return concatenated paragraph text from a DOCX file."""
    path = _resolve(filename, base_dir)
    with ZipFile(path) as zf:
        xml = zf.read("word/document.xml")
    root = ET.fromstring(xml)
    paragraphs: List[str] = []
    for para in root.findall(".//w:p", WORD_NS):
        texts = [node.text or "" for node in para.findall(".//w:t", WORD_NS)]
        if texts:
            paragraphs.append("".join(texts))
    return "\n".join(paragraphs).strip()


def read_pdf(filename: str | Path, *, base_dir: Path = BASE_DIR) -> str:
    """Return concatenated text from every page of a PDF file."""
    reader = PdfReader(_resolve(filename, base_dir))
    pages: List[str] = []
    for page in reader.pages:
        text = page.extract_text() or ""
        pages.append(text.strip())
    return "\n".join(pages).strip()


def ingest_documents(
    *,
    base_dir: Path = BASE_DIR,
    files: Iterable[Path | str] | None = None,
) -> Tuple[List[Dict[str, str]], Dict[str, str]]:
    """Build both the docs list and a dict keyed by name for notebook use."""
    if files is None:
        file_paths: Sequence[Path | str] = _discover_files(base_dir)
    else:
        file_paths = list(files)

    docs: List[Dict[str, str]] = []
    text_lookup: Dict[str, str] = {}

    for entry in file_paths:
        path = _resolve(entry, base_dir)
        suffix = path.suffix.lower()
        if suffix == ".pdf":
            text = read_pdf(path, base_dir=path.parent)
        else:
            text = read_docx(path, base_dir=path.parent)
        name = _humanize_name(path)
        text_lookup[name] = text
        docs.append({"name": name, "text": text})

    return docs, text_lookup


__all__ = [
    "BASE_DIR",
    "ingest_documents",
    "read_docx",
    "read_pdf",
]
