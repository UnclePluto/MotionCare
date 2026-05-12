"""Dump all tables from the CRF revision DOCX to a UTF-8 text file."""

from __future__ import annotations

from pathlib import Path

from docx import Document

ROOT = Path(__file__).resolve().parents[1]
DOCX_PATH = ROOT / "docs/other/认知衰弱数字疗法研究_CRF表_修订稿.docx"
OUTPUT_PATH = ROOT / "specs/patient-rehab-system/crf/_docx_table_dump.txt"


def main() -> None:
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    doc = Document(str(DOCX_PATH))
    lines: list[str] = []

    for i, table in enumerate(doc.tables, start=1):
        row_count = len(table.rows)
        col_count = len(table.columns) if table.rows else 0
        lines.append(f"=== TABLE {i} rows={row_count} cols={col_count} ===")
        for row in table.rows:
            texts = [c.text.strip() for c in row.cells]
            non_empty = [t for t in texts if t]
            lines.append(" | ".join(non_empty))

    OUTPUT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
