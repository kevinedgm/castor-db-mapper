"""Action dispatch inside one server file (generic for C-like languages; tuned on PHP).

Many legacy endpoints are a single file that switches on a request parameter:

    switch ($_POST["action"]) { case "guardaProducto": guardaProducto(); break; ... }

This module finds, without executing code:
- function spans (`function name(...) { ... }`) by brace matching on a masked copy
  of the source where strings and comments are blanked (offsets/lines preserved);
- dispatch switches: a `switch` on an action-like variable/parameter, or any
  top-level `switch` outside functions; each `case "x"` becomes an action whose
  span runs to the next case of the same switch;
- for each action, the set of source lines it can reach: its own span plus the
  spans of same-file functions it calls, transitively.

Out of scope (reported as limits): routers/frameworks, `if ($action == ...)`
chains, dispatch through dynamic calls (`$fn()`), cross-file function calls.
"""
from __future__ import annotations

import bisect
import re

ACTION_PARAMS = {"action", "accion", "acción", "op", "opcion", "operacion", "funcion", "cmd", "task"}
_FUNC = re.compile(r"\bfunction\s+&?\s*([A-Za-z_]\w*)\s*\(")
_SWITCH = re.compile(r"\bswitch\s*\(")
_CASE = re.compile(r"\b(case)\s+|\b(default)\s*:")
_CALL = re.compile(r"(?<![\w$>:])([A-Za-z_]\w*)\s*\(")


_MASKABLE = re.compile(r"""'(?:\\.|[^'\\])*'?|"(?:\\.|[^"\\])*"?|`(?:\\.|[^`\\])*`?|//[^\n]*|\#[^\n]*|/\*.*?(?:\*/|\Z)""", re.S)


def _blank(m: re.Match) -> str:
    text = m.group(0)
    body = "\n".join(" " * len(part) for part in text.split("\n"))
    if text[0] in "'\"`":  # keep quotes so `case "x"` stays recognizable
        body = text[0] + body[1:-1] + (text[-1] if len(text) > 1 else "")
    return body


def mask(source: str) -> str:
    """Blank string literals and comments with spaces, keeping newlines and offsets."""
    return _MASKABLE.sub(_blank, source)


def _brace_pairs(masked: str) -> dict[int, int]:
    pairs, stack = {}, []
    for m in re.finditer(r"[{}]", masked):
        if m.group(0) == "{":
            stack.append(m.start())
        elif stack:
            pairs[stack.pop()] = m.start()
    for open_at in stack:  # unbalanced: block runs to the end
        pairs[open_at] = len(masked) - 1
    return pairs


_OPEN_OR_END = re.compile(r"[{;]")


def _block(masked: str, start: int, pairs: dict[int, int]) -> tuple[int, int] | None:
    """Offsets of the `{ ... }` block opening at or after `start` (before any `;`)."""
    m = _OPEN_OR_END.search(masked, start)
    if not m or m.group(0) != "{":
        return None
    return m.start(), pairs.get(m.start(), len(masked) - 1)


def _paren(masked: str, open_at: int) -> int:
    depth = 0
    for j in range(open_at, len(masked)):
        if masked[j] == "(":
            depth += 1
        elif masked[j] == ")":
            depth -= 1
            if depth == 0:
                return j
    return len(masked) - 1


def structure(source: str) -> dict:
    if "switch" not in source:  # no dispatch possible: skip the expensive part
        return {"functions": {}, "actions": {}}
    masked = mask(source)
    pairs = _brace_pairs(masked)
    newlines = [m.start() for m in re.finditer("\n", source)]

    class _Lines:
        def __getitem__(self, offset: int) -> int:
            return bisect.bisect_left(newlines, offset) + 1

    line_at = _Lines()

    functions: dict[str, tuple[int, int]] = {}
    for m in _FUNC.finditer(masked):
        blk = _block(masked, _paren(masked, m.end() - 1) + 1, pairs)
        if blk and m.group(1) not in functions:
            functions[m.group(1)] = blk
    fspans = list(functions.values())

    def inside_function(pos: int) -> bool:
        return any(a < pos < b for a, b in fspans)

    switches = []
    for m in _SWITCH.finditer(masked):
        close = _paren(masked, m.end() - 1)
        subject = source[m.end():close]
        blk = _block(masked, close + 1, pairs)
        if not blk:
            continue
        words = {w.lower() for w in re.findall(r"\w+", subject)}
        if words & ACTION_PARAMS or not inside_function(m.start()):
            switches.append(blk)

    actions: dict[str, dict] = {}
    for a, b in switches:
        inner = [(x, y) for x, y in switches if a < x and y < b]
        labels = []
        for m in _CASE.finditer(masked, a + 1, b):
            if any(x < m.start() < y for x, y in inner):
                continue
            labels.append(m)
        for k, m in enumerate(labels):
            end = labels[k + 1].start() if k + 1 < len(labels) else b
            if m.group(2):  # default:
                continue
            q = masked[m.end():m.end() + 1]
            if q not in "'\"":
                continue
            close = source.find(q, m.end() + 1)
            name = source[m.end() + 1:close].strip() if close > 0 else ""
            if not name or "\n" in name or "$" in name:
                continue
            body = masked[close + 1:end]
            calls = sorted({c for c in _CALL.findall(body) if c in functions})
            act = actions.setdefault(name, {"line": line_at[m.start()], "spans": [], "calls": []})
            last = end - 1
            while last > m.start() and masked[last].isspace():
                last -= 1
            act["spans"].append([line_at[m.start()], line_at[last]])
            act["calls"] = sorted(set(act["calls"]) | set(calls))

    # reachable functions (same file, transitive)
    calls_of = {f: sorted({c for c in _CALL.findall(masked[s:e]) if c in functions and c != f}) for f, (s, e) in functions.items()}
    for act in actions.values():
        seen, stack = set(), list(act["calls"])
        while stack:
            f = stack.pop()
            if f in seen:
                continue
            seen.add(f)
            stack.extend(calls_of.get(f, []))
        act["reach"] = sorted(seen)
    return {
        "functions": {f: [line_at[s], line_at[e]] for f, (s, e) in functions.items()},
        "actions": actions,
    }


def action_lines(struct: dict) -> dict[str, list[tuple[int, int]]]:
    """Line spans each action can execute: case body + reachable function bodies."""
    funcs = struct.get("functions", {})
    out = {}
    for name, act in struct.get("actions", {}).items():
        spans = [tuple(s) for s in act["spans"]] + [tuple(funcs[f]) for f in act.get("reach", []) if f in funcs]
        out[name] = spans
    return out


_NAMES = "|".join(sorted(ACTION_PARAMS, key=len, reverse=True))
# `action: 'x'`, `"action" => "x"` (quoted value) or `?action=x` / `&action=x` / `"action=x` (query string).
_FRONT_ACTION = re.compile(r"""(?:(?<![\w$.])["']?(?:%s)["']?\s*(?::|=>)\s*["']([A-Za-z_]\w*)["'])|(?:[?&"'](?:%s)=([A-Za-z_]\w*))""" % (_NAMES, _NAMES), re.I)


_NOT_NAMES = {"function", "true", "false", "null", "undefined", "this", "new", "return"}


def front_action(lines: list[str], index: int, after: int = 12, before: int = 15) -> str | None:
    """Action name sent with an endpoint call.

    Looks at the call line and the following lines (inline `data: {action: 'x'}`),
    then at the preceding lines (payload object built just before the call,
    `var params = {action: 'x'}; $.ajax({url: ..., data: params})`). Stops at
    another endpoint reference or a function boundary so a neighbour's action is
    not borrowed. Commented lines are ignored.
    """
    def hit(text: str) -> str | None:
        if text.lstrip().startswith(("//", "*", "/*")):
            return None
        m = _FRONT_ACTION.search(text)
        name = m and (m.group(1) or m.group(2))
        return name if name and name not in _NOT_NAMES else None

    for k in range(index, min(len(lines), index + after)):
        if k != index and re.search(r"\.php\b", lines[k]):
            break
        found = hit(lines[k])
        if found:
            return found
    for k in range(index - 1, max(-1, index - 1 - before), -1):
        text = lines[k]
        if re.search(r"\.php\b", text) or re.search(r"\bfunction\b|=>\s*\{", text):
            found = hit(text) if not re.search(r"\.php\b", text) else None
            return found
        found = hit(text)
        if found:
            return found
    return None
