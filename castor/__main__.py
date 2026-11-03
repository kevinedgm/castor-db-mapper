"""Run with python -m castor."""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path
from .core import endpoints, export_html, report, scan, subgraph


def main(argv=None):
    p = argparse.ArgumentParser(prog="castor", description="Static code-to-database graph mapper")
    p.add_argument("--output", type=Path, help="Catalog location (default: <project>/.castor)")
    cmds = p.add_subparsers(dest="command", required=True)
    s = cmds.add_parser("scan", help="Scan or incrementally sync a project")
    s.add_argument("project", nargs="?", default=".", type=Path)
    s.add_argument("--full", action="store_true", help="Ignore cached analyses")
    q = cmds.add_parser("query", help="Query connected nodes by term")
    q.add_argument("term")
    q.add_argument("--depth", type=int, default=2)
    q.add_argument("--limit", type=int, default=120)
    ep = cmds.add_parser("endpoints", help="Endpoint map: callers -> server file -> tables")
    ep.add_argument("term", nargs="?", default="")
    r = cmds.add_parser("report", help="Coverage and unresolved work")
    v = cmds.add_parser("visualize", help="Export standalone interactive graph.html")
    v.add_argument("--term", default="")
    v.add_argument("--limit", type=int, default=150)
    args = p.parse_args(argv)
    project = getattr(args, "project", Path("."))
    output = args.output or project / ".castor"
    try:
        if args.command == "scan":
            result = scan(project, output, full=args.full)
        elif args.command == "query":
            if args.depth < 0 or args.limit < 1:
                p.error("depth must be nonnegative and limit positive")
            result = subgraph(output, args.term, args.depth, args.limit)
        elif args.command == "endpoints":
            result = endpoints(output, args.term)
        elif args.command == "report":
            result = report(output)
        else:
            result = {"html": str(export_html(output, args.term, args.limit))}
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"castor: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
