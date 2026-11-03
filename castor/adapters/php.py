"""PHP adapter: SQL candidates live in single/double quoted string literals."""
from __future__ import annotations

from .base import SQL_START, Statement


def scan_php_literals(source: str) -> list[tuple[str, int, bool]]:
    """Extract PHP single/double quoted string literals without interpreting code."""
    items = []
    i = 0
    line = 1
    php = False
    while i < len(source):
        if not php and source.startswith("<?", i):
            php = True
            i += 2
            continue
        if php and source.startswith("?>", i):
            php = False
            i += 2
            continue
        if not php:
            if source[i] == "\n":
                line += 1
            i += 1
            continue
        if source.startswith("//", i) or source[i] == "#":
            end = source.find("\n", i)
            i = len(source) if end < 0 else end
            continue
        if source.startswith("/*", i):
            end = source.find("*/", i + 2)
            end = len(source) if end < 0 else end + 2
            line += source[i:end].count("\n")
            i = end
            continue
        if source[i] not in ("'", '"'):
            if source[i] == "\n":
                line += 1
            i += 1
            continue
        quote = source[i]
        start_line = line
        i += 1
        chars = []
        while i < len(source):
            c = source[i]
            if c == "\\" and i + 1 < len(source):
                chars.extend([c, source[i + 1]])
                i += 2
                continue
            if c == quote:
                i += 1
                break
            chars.append(c)
            if c == "\n":
                line += 1
            i += 1
        value = "".join(chars)
        # PHP interpolates variables in double-quoted strings.
        dynamic = quote == '"' and "$" in value
        items.append((value, start_line, dynamic))
    return items


class PhpAdapter:
    name = "php"
    extensions = {".php", ".phtml", ".inc"}

    def statements(self, path: str, source: str) -> list[Statement]:
        return [Statement(s, ln, dyn) for s, ln, dyn in scan_php_literals(source) if SQL_START.search(s)]
