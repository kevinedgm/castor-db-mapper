"""Adapter registry. Add a language by appending an adapter to QUERY_ADAPTERS."""
from __future__ import annotations

from .base import QueryAdapter, Statement
from .php import PhpAdapter
from .sqlfile import SqlFileAdapter

QUERY_ADAPTERS: list[QueryAdapter] = [PhpAdapter(), SqlFileAdapter()]
EXTENSIONS = set().union(*(a.extensions for a in QUERY_ADAPTERS))


def adapters_for(path: str) -> list[QueryAdapter]:
    suffix = "." + path.rsplit(".", 1)[-1].lower() if "." in path else ""
    return [a for a in QUERY_ADAPTERS if suffix in a.extensions]


__all__ = ["EXTENSIONS", "QUERY_ADAPTERS", "QueryAdapter", "Statement", "adapters_for"]
