"""Document Parser for Prime RAG.

Parses PDF, DOCX, Markdown, HTML, Code, Text, JSON, and CSV into structured segments
preserving heading, page, section, line numbers, and file metadata.
"""

from __future__ import annotations
import hashlib
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional
from bs4 import BeautifulSoup
import pypdf
import docx


@dataclass
class DocumentSection:
    content: str
    section_title: str = "General"
    page_number: Optional[int] = None
    line_start: Optional[int] = None
    line_end: Optional[int] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ParsedDocument:
    file_path: str
    file_name: str
    file_type: str
    file_size: int
    sha256: str
    sections: List[DocumentSection]


class DocumentParser:
    """Parses diverse file formats into structured, attributable sections."""

    @staticmethod
    def get_sha256(path: str) -> str:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            while chunk := f.read(65536):
                h.update(chunk)
        return h.hexdigest()

    def parse(self, file_path: str) -> ParsedDocument:
        p = Path(file_path)
        if not p.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        ext = p.suffix.lower()
        size = p.stat().st_size
        sha = self.get_sha256(file_path)

        if ext == ".pdf":
            sections = self._parse_pdf(file_path)
        elif ext in [".docx", ".doc"]:
            sections = self._parse_docx(file_path)
        elif ext in [".html", ".htm"]:
            sections = self._parse_html(file_path)
        elif ext in [".md", ".markdown"]:
            sections = self._parse_markdown(file_path)
        elif ext in [".json"]:
            sections = self._parse_json(file_path)
        elif ext in [".py", ".ts", ".js", ".c", ".cpp", ".rs", ".go", ".ps1", ".sh"]:
            sections = self._parse_code(file_path)
        else:
            sections = self._parse_text(file_path)

        return ParsedDocument(
            file_path=str(p.resolve()),
            file_name=p.name,
            file_type=ext.lstrip("."),
            file_size=size,
            sha256=sha,
            sections=sections
        )

    def _parse_pdf(self, path: str) -> List[DocumentSection]:
        sections = []
        with open(path, "rb") as f:
            reader = pypdf.PdfReader(f)
            for idx, page in enumerate(reader.pages):
                text = page.extract_text() or ""
                if text.strip():
                    sections.append(DocumentSection(
                        content=text.strip(),
                        section_title=f"Page {idx + 1}",
                        page_number=idx + 1
                    ))
        return sections

    def _parse_docx(self, path: str) -> List[DocumentSection]:
        doc = docx.Document(path)
        sections = []
        current_heading = "Document Start"
        current_paras = []

        for p in doc.paragraphs:
            text = p.text.strip()
            if not text:
                continue
            if p.style.name.startswith("Heading"):
                if current_paras:
                    sections.append(DocumentSection(
                        content="\n".join(current_paras),
                        section_title=current_heading
                    ))
                    current_paras = []
                current_heading = text
            else:
                current_paras.append(text)

        if current_paras:
            sections.append(DocumentSection(
                content="\n".join(current_paras),
                section_title=current_heading
            ))
        return sections

    def _parse_markdown(self, path: str) -> List[DocumentSection]:
        sections = []
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()

        current_heading = "Introduction"
        current_lines = []
        start_line = 1

        for idx, line in enumerate(lines, start=1):
            stripped = line.strip()
            if stripped.startswith("#"):
                if current_lines:
                    sections.append(DocumentSection(
                        content="".join(current_lines).strip(),
                        section_title=current_heading,
                        line_start=start_line,
                        line_end=idx - 1
                    ))
                    current_lines = []
                current_heading = stripped.lstrip("#").strip()
                start_line = idx
            else:
                current_lines.append(line)

        if current_lines:
            sections.append(DocumentSection(
                content="".join(current_lines).strip(),
                section_title=current_heading,
                line_start=start_line,
                line_end=len(lines)
            ))
        return sections

    def _parse_html(self, path: str) -> List[DocumentSection]:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            soup = BeautifulSoup(f.read(), "html.parser")

        sections = []
        headings = soup.find_all(["h1", "h2", "h3", "p"])
        current_heading = soup.title.string if soup.title else "HTML Body"
        current_texts = []

        for elem in headings:
            text = elem.get_text().strip()
            if not text:
                continue
            if elem.name in ["h1", "h2", "h3"]:
                if current_texts:
                    sections.append(DocumentSection(
                        content="\n".join(current_texts),
                        section_title=current_heading
                    ))
                    current_texts = []
                current_heading = text
            else:
                current_texts.append(text)

        if current_texts:
            sections.append(DocumentSection(
                content="\n".join(current_texts),
                section_title=current_heading
            ))
        return sections

    def _parse_code(self, path: str) -> List[DocumentSection]:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
        sections = []
        current_block = []
        current_name = "Header / Imports"
        start_line = 1

        for idx, line in enumerate(lines, start=1):
            stripped = line.strip()
            if stripped.startswith(("def ", "class ", "function ", "export ", "async function ", "struct ", "impl ")):
                if current_block:
                    sections.append(DocumentSection(
                        content="".join(current_block).strip(),
                        section_title=current_name,
                        line_start=start_line,
                        line_end=idx - 1
                    ))
                    current_block = []
                current_name = stripped.split("(")[0].split("{")[0].strip()
                start_line = idx
            current_block.append(line)

        if current_block:
            sections.append(DocumentSection(
                content="".join(current_block).strip(),
                section_title=current_name,
                line_start=start_line,
                line_end=len(lines)
            ))
        return sections

    def _parse_json(self, path: str) -> List[DocumentSection]:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            data = json.load(f)
        formatted = json.dumps(data, indent=2)
        return [DocumentSection(content=formatted, section_title="JSON Data")]

    def _parse_text(self, path: str) -> List[DocumentSection]:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            text = f.read()
        return [DocumentSection(content=text.strip(), section_title="Main Content")]
