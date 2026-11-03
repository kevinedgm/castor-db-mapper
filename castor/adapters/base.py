"""Contract between language adapters and the language-agnostic core.

A *query adapter* knows where SQL lives in one kind of file and returns
`Statement`s. The core (`castor.core.scan_sql`) turns statements into graph
nodes/edges, so adding a language never touches SQL or graph logic.
"""
from __future__ import annotations

import re
from typing import NamedTuple, Protocol

SQL_START = re.compile(r"\b(SELECT|INSERT|UPDATE|DELETE|REPLACE|CREATE\s+TABLE|ALTER\s+TABLE|WITH|CALL)\b", re.I)


class Statement(NamedTuple):
    sql: str
    line: int
    dynamic: bool  # text was built at runtime (interpolation), so analysis may be partial


class QueryAdapter(Protocol):
    name: str
    extensions: set[str]

    def statements(self, path: str, source: str) -> list[Statement]: ...
