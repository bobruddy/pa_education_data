"""Function, object, and revenue text from the chart of accounts PDF.

The heading is the label. The description is the paragraph that sits under that
heading, through the next heading. A missing description is left off. A later
section, or a heading that no longer sits above its own paragraph, is an error.
"""

from __future__ import annotations

import re
from pathlib import Path

CODE_LINE = re.compile(r"^(\d{3,4})\s+\*?\s*(.+)$")
# `1801* Instruction` has no space before the asterisk. A following word that
# starts with a capital is a heading. A wrapped sentence that starts with a
# number ("4010 students") is not.
HEADING = re.compile(r"^(\d{3,4})(?:\s+\*?\s*|\*\s*)([A-Z].+)$")
PAGE_HEADER = re.compile(r"\b20\d\d-\d{4}\s*FY\b")
SECTION_LINE = re.compile(r"^Section\s+[A-Z]$")


def parse_chart(path: Path, document: dict) -> dict[str, pd.DataFrame]:
    text = _pdf_text(path)
    functions, objects, revenue = titles_from_text(text)
    described = descriptions_from_text(text)
    return {
        "function": _frame(functions, described[0], "function_code"),
        "object": _frame(objects, described[1], "object_code"),
        "revenue": _frame(revenue, described[2], "account_code"),
    }


def titles_from_text(text: str) -> tuple[dict[str, str], dict[str, str], dict[str, str]]:
    functions, objects, revenue = _chart_windows(text)
    return (
        _codes_in(functions, 4),
        _codes_in(objects, 3),
        {code: title for code, title in _codes_in(revenue, 4).items() if code[0] in "6789"},
    )


def descriptions_from_text(text: str) -> tuple[dict[str, str], dict[str, str], dict[str, str]]:
    functions, objects, revenue = _chart_windows(text)
    return (
        _descriptions_in(functions, 4),
        _descriptions_in(objects, 3),
        _descriptions_in(revenue, 4, revenue=True),
    )


def _chart_windows(text: str) -> tuple[str, str, str]:
    functions = _section_window(text, "Expenditure Function Codes", "Object Codes", 4, 10)
    if len(_codes_in(functions, 4)) < 10:
        functions = _section_window(text, "1000 INSTRUCTION", "100 PERSONNEL SERVICES", 4, 1)
    objects = _section_window(text, "100 PERSONNEL SERVICES", "Revenue Codes", 3, 10)
    if len(_codes_in(objects, 3)) < 10:
        objects = _section_window(text, "100 PERSONNEL SERVICES", "6000 REVENUE", 3, 1)
    if len(_codes_in(objects, 3)) < 10:
        objects = _section_window(text, "100 PERSONNEL SERVICES", "REVENUE FROM LOCAL", 3, 1)
    return functions, objects, _revenue_window(text)


def _revenue_window(text: str) -> str:
    """The revenue section, not the table of contents and not the next section.

    A year such as 1965 in the prose is not a revenue account. Revenue codes
    start at 6000. `Section H` is the funding-source section that follows.
    """
    marker = "REVENUE FROM LOCAL SOURCES"
    begin = 0
    fallback = ""
    fallback_count = 0
    while True:
        begin = text.find(marker, begin)
        if begin < 0:
            return fallback
        line_start = text.rfind("\n", 0, begin) + 1
        if "...." in text[line_start:begin]:
            begin += len(marker)
            continue
        finish = text.find("SECTION H", begin + len(marker))
        window = text[line_start:] if finish < 0 else text[line_start:finish]
        found = {
            code: title
            for code, title in _codes_in(window, 4).items()
            if code[0] in "6789"
        }
        if len(found) >= 10:
            return window
        if len(found) > fallback_count:
            fallback = window
            fallback_count = len(found)
        begin += len(marker)


def _pdf_text(path: Path) -> str:
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def _section_window(text: str, start: str, end: str, width: int, minimum: int) -> str:
    begin = 0
    while True:
        begin = text.find(start, begin)
        if begin < 0:
            return ""
        finish = text.find(end, begin + len(start))
        window = text[begin:] if finish < 0 else text[begin:finish]
        if len(_codes_in(window, width)) >= minimum:
            return window
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


def _descriptions_in(window: str, width: int, *, revenue: bool = False) -> dict[str, str]:
    found: dict[str, str] = {}
    current: tuple[str, str, str, bool] | None = None
    body: list[str] = []

    def close() -> None:
        nonlocal current, body
        if current is None:
            return
        code, name, remainder, stopped_lower = current
        description = _description(name, remainder, stopped_lower, body)
        if description:
            found[code] = description
        current = None
        body = []

    for raw in window.splitlines():
        line = raw.strip()
        if not line or PAGE_HEADER.search(line):
            continue
        if SECTION_LINE.match(line):
            if current is not None or found:
                close()
                break
            continue
        match = HEADING.match(line)
        if match:
            code, rest = match.group(1), match.group(2)
            if len(code) != width or (revenue and code[0] not in "6789"):
                raise RuntimeError(
                    "chart prose no longer sits under the heading "
                    f"near {code}: {line}"
                )
            close()
            name, remainder, stopped_lower = _split_heading(rest)
            current = (code, name, remainder, stopped_lower)
            continue
        if current is not None:
            body.append(line)
    close()
    return found


def _split_heading(rest: str) -> tuple[str, str, bool]:
    words = rest.replace("*", " ").split()
    title: list[str] = []
    for index, word in enumerate(words):
        lower = word[:1].islower()
        if lower or word in _STOP:
            return " ".join(title).strip(" -–"), " ".join(words[index:]).strip(), lower
        title.append(word)
    return " ".join(title).strip(" -–"), "", False


def _description(name: str, remainder: str, stopped_lower: bool, body: list[str]) -> str:
    prose = _paragraph(_body_lines(body))
    if prose:
        return prose
    # The test fixtures, and a few deleted-code lines, put the sentence on the
    # heading line. A lowercase stop is the rest of the heading ("and", "to").
    if name and remainder and not stopped_lower and re.search(r"[a-z]", remainder):
        return _paragraph([remainder])
    return ""


def _body_lines(lines: list[str]) -> list[str]:
    """Drop a wrapped tail of the heading (`Component`, `BY THE LEA`).

    The prose is the sentence under that tail. A heading that wraps onto the
    next line is not the description. An all-caps banner after that sentence
    (`INSTRUCTION FUNCTION AND PROGRAM CODING`) is the next block, not this
    account.
    """
    prose: list[str] = []
    started = False
    for line in lines:
        if not started and _heading_continuation(line):
            continue
        if started and _section_banner(line):
            break
        started = True
        prose.append(line)
    return prose


def _section_banner(line: str) -> bool:
    if re.search(r"[a-z]", line):
        return False
    return len(line.split()) >= 3


def _heading_continuation(line: str) -> bool:
    if re.search(r"[.!?]", line):
        return False
    words = line.split()
    if not words:
        return False
    if len(words) == 1 and re.fullmatch(r"[A-Z][a-z]+", words[0]):
        return True
    return re.search(r"[a-z]", line) is None


def _paragraph(lines: list[str]) -> str:
    parts: list[str] = []
    for line in lines:
        text = " ".join(line.split())
        if not text:
            continue
        if parts and parts[-1].endswith(("-", "/")) and text[:1].islower():
            parts[-1] = parts[-1] + text
        else:
            parts.append(text)
    return " ".join(parts).strip()


def _frame(names: dict[str, str], descriptions: dict[str, str], column: str):
    import pandas as pd

    rows = []
    for code in sorted(set(names) | set(descriptions)):
        rows.append({
            column: code,
            "name": names.get(code, pd.NA),
            "description": descriptions.get(code, pd.NA),
        })
    return pd.DataFrame(rows, columns=[column, "name", "description"])
