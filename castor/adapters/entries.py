"""Entry adapter: finds references from any source file to server endpoints.

Generic idea: a front end (JS/TS/Vue/HTML) or another server file names an
endpoint file in a string literal (`axios.get('mod/api.php')`,
`include __DIR__ . '/db.php'`). We record the raw reference here; the core
resolves it against the files that were actually scanned, so a reference is
only linked when the target exists in the repository.

Limits (by design, v0.2): the endpoint is the *file*. Dispatch inside the file
(`?accion=...`, routers) and URLs built at runtime are not resolved.
"""
from __future__ import annotations

import re
from typing import NamedTuple

ENTRY_EXTENSIONS = {".js", ".mjs", ".cjs", ".jsx", ".ts", ".tsx", ".vue", ".html", ".htm", ".php", ".phtml", ".inc"}
ENDPOINT_SUFFIXES = (".php",)  # server-side file types that can be endpoints; extend per stack
MAX_BYTES = 512_000  # skip bundles/minified files: they duplicate evidence and are slow

_LITERAL = re.compile(r"""['"`]([^'"`\s<>?#]*\.(?:%s))(?=[?#'"`])""" % "|".join(s.lstrip(".") for s in ENDPOINT_SUFFIXES))
_INCLUDE = re.compile(r"\b(?:include|require)(?:_once)?\b", re.I)
_VIA = re.compile(r"\b(axios|fetch|ajax|\$\.(?:get|post|getJSON)|XMLHttpRequest|url|action|href|location|window\.open|src)\b", re.I)
_COMMENT_START = ("//", "*", "/*", "#", "<!--")


class Ref(NamedTuple):
    target: str  # raw path as written
    line: int
    kind: str  # "include" (server-side composition) | "call" (HTTP/navigation)
    via: str  # detected mechanism, e.g. axios, fetch, href; "string" if unknown


def references(path: str, source: str) -> list[Ref]:
    if len(source) > MAX_BYTES or ".min." in path:
        return []
    out = []
    for number, text in enumerate(source.split("\n"), 1):
        if ".php" not in text or text.lstrip().startswith(_COMMENT_START):
            continue
        for m in _LITERAL.finditer(text):
            raw = m.group(1)
            if not raw or raw.startswith(("http:", "https:", "//")):
                continue
            before = text[: m.start()]
            if _INCLUDE.search(before):
                out.append(Ref(raw, number, "include", "include"))
            else:
                via = _VIA.findall(before)
                out.append(Ref(raw, number, "call", via[-1].lower() if via else "string"))
    return out


def applies(path: str) -> bool:
    return "." in path and "." + path.rsplit(".", 1)[-1].lower() in ENTRY_EXTENSIONS
