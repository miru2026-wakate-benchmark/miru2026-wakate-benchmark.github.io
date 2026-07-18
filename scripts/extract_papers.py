#!/usr/bin/env python3
"""Extract the public paper catalogue from the survey workbook.

Usage:
    python3 scripts/extract_papers.py static/data/<survey>.xlsx static/js/papers.js

Only Python's standard library is required.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from xml.etree import ElementTree as ET
from zipfile import ZipFile


MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
NS = {"m": MAIN_NS, "r": REL_NS}
SURVEY_SHEET_NAME = "サーベイ論文リスト"


def cell_column(reference: str) -> str:
    matched = re.match(r"[A-Z]+", reference)
    return matched.group() if matched else ""


def extract(source: Path) -> list[dict[str, str]]:
    with ZipFile(source) as archive:
        strings: list[str] = []
        if "xl/sharedStrings.xml" in archive.namelist():
            root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
            for item in root.findall("m:si", NS):
                strings.append(
                    "".join(node.text or "" for node in item.iter(f"{{{MAIN_NS}}}t"))
                )

        workbook = ET.fromstring(archive.read("xl/workbook.xml"))
        relations = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
        relation_targets = {
            relation.attrib["Id"]: relation.attrib["Target"] for relation in relations
        }
        sheets = workbook.find("m:sheets", NS)
        survey_sheet = next(
            (sheet for sheet in sheets if sheet.attrib.get("name") == SURVEY_SHEET_NAME),
            None,
        )
        if survey_sheet is None:
            available = ", ".join(sheet.attrib.get("name", "") for sheet in sheets)
            raise ValueError(
                f"sheet {SURVEY_SHEET_NAME!r} was not found (available: {available})"
            )
        sheet_target = relation_targets[survey_sheet.attrib[f"{{{REL_NS}}}id"]]
        sheet_path = (
            sheet_target if sheet_target.startswith("xl/") else "xl/" + sheet_target.lstrip("/")
        )
        sheet = ET.fromstring(archive.read(sheet_path))

        rows: list[dict[str, str]] = []
        for row in sheet.findall(".//m:sheetData/m:row", NS):
            values: dict[str, str] = {}
            for cell in row.findall("m:c", NS):
                column = cell_column(cell.attrib.get("r", ""))
                cell_type = cell.attrib.get("t")
                value_node = cell.find("m:v", NS)
                if cell_type == "inlineStr":
                    value = "".join(
                        node.text or "" for node in cell.iter(f"{{{MAIN_NS}}}t")
                    )
                elif value_node is None:
                    value = ""
                elif cell_type == "s":
                    value = strings[int(value_node.text)]
                else:
                    value = value_node.text or ""
                values[column] = value.strip()

            if values.get("D") and values["D"] != "論文名":
                rows.append(values)

        return [
            {
                "url": row.get("A", ""),
                "title": row.get("D", ""),
                "authors": row.get("E", ""),
                "venue": row.get("F", ""),
                "year": row.get("G", ""),
                "field": row.get("H", "") or "その他",
                "motivation": row.get("I", ""),
                "clarity": row.get("J", ""),
            }
            for row in rows
        ]


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit("usage: extract_papers.py INPUT.xlsx OUTPUT.js")
    source, destination = map(Path, sys.argv[1:])
    papers = extract(source)
    abstracts_path = source.parent / "abstracts_ja.json"
    if abstracts_path.exists():
        abstracts = json.loads(abstracts_path.read_text(encoding="utf-8"))
        for paper in papers:
            paper["abstractJa"] = abstracts.get(paper["title"], "")
        missing = [paper["title"] for paper in papers if not paper["abstractJa"]]
        if missing:
            print(
                "Warning: Japanese abstracts are missing for: " + ", ".join(missing),
                file=sys.stderr,
            )
        unused = sorted(set(abstracts) - {paper["title"] for paper in papers})
        if unused:
            print(
                "Warning: Japanese abstracts have no matching paper: "
                + ", ".join(unused),
                file=sys.stderr,
            )
    else:
        for paper in papers:
            paper["abstractJa"] = ""
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        "// Generated from the survey workbook and abstracts_ja.json. Do not edit by hand.\n"
        + "window.PAPERS = "
        + json.dumps(papers, ensure_ascii=False, indent=2)
        + ";\n",
        encoding="utf-8",
    )
    print(f"Wrote {len(papers)} papers to {destination}")


if __name__ == "__main__":
    main()
