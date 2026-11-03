"""Plain .sql files: every statement is a candidate."""
from __future__ import annotations

from .base import Statement


def sql_statements(source: str) -> list[tuple[str, int]]:
    """Split .sql on semicolons outside strings and comments, tracking lines."""
    result = []
    start = 0
    line = 1
    start_line = 1
    quote = None
    comment = None
    i = 0
    while i < len(source):
        c = source[i]
        if comment == "line":
            if c == "\n":
                comment = None
        elif comment == "block":
            if source.startswith("*/", i):
                comment = None
                i += 2
                continue
        elif quote:
            if c == "\\":
                i += 2
                continue
            if c == quote:
                if i + 1 < len(source) and source[i + 1] == quote:
                    i += 2
                    continue
                quote = None
        elif source.startswith("/*", i):
            comment = "block"
        elif source.startswith("--", i) and (i + 2 >= len(source) or source[i + 2].isspace()) or c == "#":
            comment = "line"
        elif c in "'\"`":
            quote = c
        elif c == ";":
            snippet = source[start:i].strip()
            if snippet:
                result.append((snippet, 1 + source.count("\n", 0, start + len(source[start:i]) - len(source[start:i].lstrip()))))
            start = i + 1
            start_line = line
        if c == "\n":
            line += 1
            if start == i + 1:
                start_line = line
        i += 1
    snippet = source[start:].strip()
    if snippet:
        result.append((snippet, 1 + source.count("\n", 0, start + len(source[start:]) - len(source[start:].lstrip()))))
    return result


class SqlFileAdapter:
    name = "sql"
    extensions = {".sql"}

    def statements(self, path: str, source: str) -> list[Statement]:
        return [Statement(s, ln, False) for s, ln in sql_statements(source)]
