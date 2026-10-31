"""Minimal Markdown to DOCX converter for the manuscript review copy.

Supports headings, paragraphs, bullet lists, pipe tables, fenced code blocks,
images and bold/italic/code inline runs. Not a general Markdown parser.
"""
from pathlib import Path
import re
import sys

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Cm, Inches, Pt


def add_runs(paragraph, text):
    parts = re.split(r"(\*\*.*?\*\*|`.*?`)", text)
    for part in parts:
        if not part:
            continue
        if part.startswith("**") and part.endswith("**"):
            run = paragraph.add_run(part[2:-2])
            run.bold = True
        elif part.startswith("`") and part.endswith("`"):
            run = paragraph.add_run(part[1:-1])
            run.font.name = "Consolas"
            run.font.size = Pt(9)
        else:
            paragraph.add_run(part)


def add_table(document, rows):
    header = [cell.strip() for cell in rows[0].strip().strip("|").split("|")]
    table = document.add_table(rows=1, cols=len(header))
    table.style = "Table Grid"
    for index, text in enumerate(header):
        cell = table.rows[0].cells[index]
        cell.text = ""
        paragraph = cell.paragraphs[0]
        run = paragraph.add_run(text)
        run.bold = True
    for row in rows[2:]:
        cells = [cell.strip() for cell in row.strip().strip("|").split("|")]
        if len(cells) != len(header):
            continue
        row_cells = table.add_row().cells
        for index, text in enumerate(cells):
            row_cells[index].text = ""
            add_runs(row_cells[index].paragraphs[0], text)
    document.add_paragraph()


def convert(source, target):
    lines = source.read_text(encoding="utf-8").splitlines()
    document = Document()
    section = document.sections[0]
    section.page_height = Cm(29.7)
    section.page_width = Cm(21.0)
    section.top_margin = Cm(2.5)
    section.bottom_margin = Cm(2.5)
    section.left_margin = Cm(2.5)
    section.right_margin = Cm(2.5)

    normal = document.styles["Normal"]
    normal.font.name = "Times New Roman"
    normal.font.size = Pt(11)

    index = 0
    while index < len(lines):
        line = lines[index]
        stripped = line.strip()

        if not stripped:
            index += 1
            continue

        if stripped.startswith("```"):
            index += 1
            block = []
            while index < len(lines) and not lines[index].strip().startswith("```"):
                block.append(lines[index])
                index += 1
            index += 1
            paragraph = document.add_paragraph()
            paragraph.paragraph_format.space_after = Pt(6)
            run = paragraph.add_run("\n".join(block))
            run.font.name = "Consolas"
            run.font.size = Pt(8.5)
            continue

        if stripped.startswith("|"):
            rows = []
            while index < len(lines) and lines[index].strip().startswith("|"):
                rows.append(lines[index])
                index += 1
            if len(rows) >= 2:
                add_table(document, rows)
            continue

        image = re.match(r"!\[.*?\]\((.*?)\)", stripped)
        if image:
            path = Path(image.group(1))
            if not path.is_absolute():
                path = (source.parent / path).resolve()
            if path.exists():
                document.add_picture(str(path), width=Inches(6.0))
                document.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER
            index += 1
            continue

        if stripped.startswith("#"):
            level = len(stripped) - len(stripped.lstrip("#"))
            text = stripped[level:].strip()
            document.add_heading(text, level=min(level, 3))
            index += 1
            continue

        if stripped.startswith("> "):
            paragraph = document.add_paragraph()
            paragraph.paragraph_format.left_indent = Cm(0.8)
            run = paragraph.add_run(stripped[2:])
            run.italic = True
            index += 1
            continue

        if stripped.startswith("- "):
            paragraph = document.add_paragraph(style="List Bullet")
            add_runs(paragraph, stripped[2:])
            index += 1
            continue

        if stripped.startswith("*") and stripped.endswith("*") and len(stripped) > 2:
            paragraph = document.add_paragraph()
            run = paragraph.add_run(stripped[1:-1])
            run.italic = True
            index += 1
            continue

        add_runs(document.add_paragraph(), stripped)
        index += 1

    document.save(target)
    print("Saved:", target)


if __name__ == "__main__":
    source = Path(sys.argv[1])
    target = Path(sys.argv[2]) if len(sys.argv) > 2 else source.with_suffix(".docx")
    convert(source, target)
