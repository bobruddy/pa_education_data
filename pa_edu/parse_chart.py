"""Function and object titles from the chart of accounts PDF."""

from __future__ import annotations

import re
from pathlib import Path

CODE_LINE = re.compile(r"^(\d{3,4})\s+\*?\s*(.+)$")


def parse_chart(path: Path, document: dict) -> dict[str, pd.DataFrame]:
    functions, objects = titles_from_text(_pdf_text(path))
    return {
        "function": _frame(functions, "function_code"),
        "object": _frame(objects, "object_code"),
    }


def titles_from_text(text: str) -> tuple[dict[str, str], dict[str, str]]:
    functions = _section_codes(
        text, "Expenditure Function Codes", "Object Codes", width=4, minimum=10
    )
    if len(functions) < 10:
        functions = _section_codes(
            text, "1000 INSTRUCTION", "100 PERSONNEL SERVICES", width=4, minimum=1
        )
    objects = _section_codes(
        text, "100 PERSONNEL SERVICES", "Revenue Codes", width=3, minimum=10
    )
    if len(objects) < 10:
        objects = _section_codes(
            text, "100 PERSONNEL SERVICES", "6000 REVENUE", width=3, minimum=1
        )
    if len(objects) < 10:
        objects = _section_codes(
            text, "100 PERSONNEL SERVICES", "REVENUE FROM LOCAL", width=3, minimum=1
        )
    return functions, objects


def _pdf_text(path: Path) -> str:
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def _section_codes(
    text: str, start: str, end: str, width: int, minimum: int
) -> dict[str, str]:
    begin = 0
    while True:
        begin = text.find(start, begin)
        if begin < 0:
            return {}
        finish = text.find(end, begin + len(start))
        window = text[begin:] if finish < 0 else text[begin:finish]
        found = _codes_in(window, width)
        if len(found) >= minimum:
            return found
        begin += len(start)


def _codes_in(window: str, width: int) -> dict[str, str]:
    found: dict[str, str] = {}
    for line in window.splitlines():
        match = CODE_LINE.match(line.strip())
        if match is None:
            continue
        code, rest = match.group(1), match.group(2)
        if len(code) != width:
            continue
        title = _title(rest)
        if title:
            found[code] = title
    return found


_STOP = {
    "A", "An", "The", "Use", "Gross", "Activities", "This", "Record", "That",
    "Amounts", "Expenditures", "Outlays", "Includes", "PDE", "Revenue", "Charges",
    "Note:", "Beginning", "Do", "Include", "Those",
}


def _title(rest: str) -> str:
    words = []
    for word in rest.replace("*", " ").split():
        if word[:1].islower() or word in _STOP:
            break
        words.append(word)
    return " ".join(words).strip(" -–")


def _frame(codes: dict[str, str], column: str):
    import pandas as pd

    rows = [{column: code, "name": name} for code, name in sorted(codes.items())]
    return pd.DataFrame(rows, columns=[column, "name"])
