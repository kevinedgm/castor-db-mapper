"""Conservative, deterministic PHP/SQL evidence scanner. No project code execution."""
from __future__ import annotations

import hashlib
import html
import json
import re
import sqlite3
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

VERSION = "0.1.0"
EXTENSIONS = {".php", ".phtml", ".inc", ".sql"}
IGNORED = {".git", ".castor", "node_modules", "vendor", "bower_components", ".venv", "venv", "__pycache__", "dist", "build"}
SQL_START = re.compile(r"\b(SELECT|INSERT|UPDATE|DELETE|REPLACE|CREATE\s+TABLE|ALTER\s+TABLE|WITH|CALL)\b", re.I)
IDENT = re.compile(r"^[A-Za-z_][\w$]*$")
STOP = {"WHERE", "GROUP", "ORDER", "HAVING", "LIMIT", "UNION", "JOIN", "LEFT", "RIGHT", "INNER", "OUTER", "CROSS", "ON", "USING", "SET", "VALUES", "RETURNING", "FOR"}


def digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()


def node(typ: str, name: str, **meta: Any) -> dict:
    return {"id": f"{typ}:{name}", "type": typ, "label": name, "meta": meta}


def edge(source: str, target: str, kind: str, evidence: dict, **meta: Any) -> dict:
    signature = json.dumps([source, target, kind, evidence], sort_keys=True, ensure_ascii=False)
    return {"id": digest(signature)[:20], "source": source, "target": target, "type": kind, "evidence": evidence, "meta": meta}


def sql_tokens(sql: str) -> list[str]:
    """Small SQL lexer: protects quoted values and identifiers, skips comments."""
    out = []
    i = 0
    while i < len(sql):
        c = sql[i]
        if c.isspace():
            i += 1
            continue
        if (sql.startswith("--", i) and (i + 2 == len(sql) or sql[i + 2].isspace())) or c == "#":
            j = sql.find("\n", i)
            i = len(sql) if j < 0 else j + 1
            continue
        if sql.startswith("/*", i):
            j = sql.find("*/", i + 2)
            i = len(sql) if j < 0 else j + 2
            continue
        if c in "'\"`":
            start = i
            quote = c
            i += 1
            while i < len(sql):
                if sql[i] == "\\":
                    i += 2
                elif sql[i] == quote:
                    if i + 1 < len(sql) and sql[i + 1] == quote:
                        i += 2
                    else:
                        i += 1
                        break
                else:
                    i += 1
            value = sql[start:i]
            out.append(value[1:-1] if quote == "`" else "?")
            continue
        if c.isalnum() or c in "_$":
            j = i + 1
            while j < len(sql) and (sql[j].isalnum() or sql[j] in "_$"):
                j += 1
            out.append(sql[i:j])
            i = j
            continue
        out.append(c)
        i += 1
    return out


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


def table_after(tokens: list[str], index: int) -> tuple[str | None, str | None, int]:
    j = index
    while j < len(tokens) and tokens[j].upper() in {"IF", "NOT", "EXISTS", "ONLY"}:
        j += 1
    if j >= len(tokens) or not IDENT.match(tokens[j]):
        return None, None, j
    name = tokens[j].lower()
    j += 1
    if j + 1 < len(tokens) and tokens[j] == "." and IDENT.match(tokens[j + 1]):
        name += "." + tokens[j + 1].lower()
        j += 2
    alias = None
    if j < len(tokens) and tokens[j].upper() == "AS":
        j += 1
    if j < len(tokens) and IDENT.match(tokens[j]) and tokens[j].upper() not in STOP | {"SELECT", "FROM", "AS", "WHERE"}:
        alias = tokens[j].lower()
    return name, alias, j


def scan_sql(sql: str, path: str, line: int, dynamic: bool = False) -> dict:
    tokens = sql_tokens(sql)
    upper = [t.upper() for t in tokens]
    n = {"nodes": [], "edges": [], "warnings": []}
    if not tokens or not any(t in upper for t in ("SELECT", "INSERT", "DELETE", "UPDATE", "REPLACE", "CREATE", "ALTER", "CALL")):
        return n
    op = next((t for t in upper if t in {"SELECT", "INSERT", "UPDATE", "DELETE", "REPLACE", "CREATE", "ALTER", "CALL"}), "UNKNOWN")
    prefix = sql[:160].replace("\n", " ")
    # Never persist arbitrary SQL string values or source fragments as evidence.
    redacted = re.sub(r"'(?:\\.|''|[^'])*'|\"(?:\\.|\"\"|[^\"])*\"", "?", prefix)
    qid = f"query:{path}:{line}:{digest(sql)[:12]}"
    n["nodes"].append({"id": qid, "type": "query", "label": f"{op} · {path}:{line}", "meta": {"operation": op, "dynamic": dynamic, "excerpt": redacted}})
    n["edges"].append(edge(f"file:{path}", qid, "CONTAINS_QUERY", {"file": path, "line": line, "kind": "CODE_OBSERVED"}))
    ev = {"file": path, "line": line, "kind": "CODE_OBSERVED"}
    if dynamic:
        n["warnings"].append({"path": path, "line": line, "reason": "Dynamic SQL/interpolation; analysis may be incomplete"})
    found = []
    aliases = {}
    for i, t in enumerate(upper):
        if t not in {"FROM", "JOIN", "UPDATE", "INTO", "TABLE"}:
            continue
        # Do not treat UPDATE in an ON DUPLICATE KEY UPDATE clause as a table.
        if t == "UPDATE" and i > 0 and upper[i - 1] == "KEY":
            continue
        name, alias, _ = table_after(tokens, i + 1)
        if not name:
            continue
        found.append((name, t))
        aliases[name.split(".")[-1]] = name
        if alias:
            aliases[alias] = name
    for table, keyword in dict.fromkeys(found):
        tid = f"table:{table}"
        n["nodes"].append(node("table", table))
        mode = "SCHEMA" if op in {"CREATE", "ALTER"} else "WRITE" if (keyword in {"UPDATE", "INTO"} or op == "DELETE" and keyword == "FROM") else "READ"
        if keyword == "JOIN" and op == "UPDATE":
            mode = "READ"
        n["edges"].append(edge(qid, tid, mode, ev))
    # Equality between two qualified columns is observed evidence of association.
    for i in range(len(tokens) - 6):
        a, dot1, ac, eq, b, dot2, bc = tokens[i:i + 7]
        if dot1 != "." or eq != "=" or dot2 != ".":
            continue
        if not (IDENT.match(a) and IDENT.match(ac) and IDENT.match(b) and IDENT.match(bc)):
            continue
        ta, tb = aliases.get(a.lower()), aliases.get(b.lower())
        if not (ta and tb and ta != tb):
            continue
        for tbl, col in [(ta, ac.lower()), (tb, bc.lower())]:
            n["nodes"].append(node("column", f"{tbl}.{col}", evidence="CODE_OBSERVED"))
            n["edges"].append(edge(f"table:{tbl}", f"column:{tbl}.{col}", "HAS_COLUMN", ev))
        n["edges"].append(edge(f"column:{ta}.{ac.lower()}", f"column:{tb}.{bc.lower()}", "RELATES_TO", ev, confidence=0.85, relationship="CODE_OBSERVED"))
    if op == "CREATE" and "TABLE" in upper:
        target, _, _ = table_after(tokens, upper.index("TABLE") + 1)
        if target:
            # Parse CREATE TABLE column list by depth rather than commas inside types.
            try:
                start = upper.index("(", upper.index("TABLE") + 1)
            except ValueError:
                start = -1
            if start >= 0:
                parts = []
                segment = []
                depth = 0
                for tok in tokens[start + 1:]:
                    if tok == "(" :
                        depth += 1
                    elif tok == ")":
                        if depth == 0:
                            if segment:
                                parts.append(segment)
                            break
                        depth -= 1
                    if tok == "," and depth == 0:
                        parts.append(segment)
                        segment = []
                    else:
                        segment.append(tok)
                for part in parts:
                    if not part:
                        continue
                    key = part[0].upper()
                    if key in {"CONSTRAINT", "FOREIGN", "PRIMARY", "UNIQUE", "KEY", "INDEX", "CHECK"}:
                        # Constraint may declare physical foreign keys.
                        up = [x.upper() for x in part]
                        if "FOREIGN" in up and "REFERENCES" in up:
                            try:
                                pos = up.index("FOREIGN")
                                local_col = part[pos + 3].lower() if up[pos + 1:pos + 3] == ["KEY", "("] else None
                                ref_pos = up.index("REFERENCES")
                                foreign_table = part[ref_pos + 1].lower()
                                foreign_col = part[ref_pos + 3].lower() if part[ref_pos + 2] == "(" else None
                                if local_col and foreign_col:
                                    for tbl, col in [(target, local_col), (foreign_table, foreign_col)]:
                                        n["nodes"].append(node("table", tbl))
                                        n["nodes"].append(node("column", f"{tbl}.{col}", evidence="DECLARED"))
                                        n["edges"].append(edge(f"table:{tbl}", f"column:{tbl}.{col}", "HAS_COLUMN", {**ev, "kind": "DECLARED"}))
                                    n["edges"].append(edge(f"column:{target}.{local_col}", f"column:{foreign_table}.{foreign_col}", "RELATES_TO", {**ev, "kind": "DECLARED"}, confidence=1.0, relationship="DECLARED"))
                            except (IndexError, ValueError):
                                n["warnings"].append({"path": path, "line": line, "reason": "Foreign key declaration could not be parsed"})
                        continue
                    col = part[0].lower()
                    if IDENT.match(col):
                        n["nodes"].append(node("column", f"{target}.{col}", evidence="DECLARED"))
                        n["edges"].append(edge(f"table:{target}", f"column:{target}.{col}", "HAS_COLUMN", {**ev, "kind": "DECLARED"}))
    if not found and op not in {"CALL"}:
        n["warnings"].append({"path": path, "line": line, "reason": "SQL recognized but no static table could be resolved"})
    return n


def analyze(path: str, source: str) -> dict:
    n = {"sha256": digest(source), "nodes": [node("file", path)], "edges": [], "warnings": [], "queries": 0}
    statements = ([(s, ln, False) for s, ln in sql_statements(source)] if path.endswith(".sql") else
                  [(s, ln, dyn) for s, ln, dyn in scan_php_literals(source) if SQL_START.search(s)])
    for sql, line, dynamic in statements:
        result = scan_sql(sql, path, line, dynamic)
        if result["nodes"]:
            n["queries"] += 1
        for key in ("nodes", "edges", "warnings"):
            n[key].extend(result[key])
    return n


def infer_relationships(nodes: list[dict], edges: list[dict]) -> list[dict]:
    tables = {n["label"] for n in nodes if n["type"] == "table"}
    cols = {n["label"] for n in nodes if n["type"] == "column"}
    existing_sources = {e["source"] for e in edges if e["type"] == "RELATES_TO"}
    result = []
    for col in sorted(cols):
        if "." not in col:
            continue
        table, name = col.rsplit(".", 1)
        ref = name[3:] if name.startswith("id_") else name[:-3] if name.endswith("_id") else ""
        if not ref:
            continue
        possible = [t for t in tables if t != table and t.split(".")[-1].rstrip("s") == ref.rstrip("s")]
        if len(possible) != 1:
            continue
        foreign = possible[0]
        target = f"column:{foreign}.id"
        if f"{foreign}.id" not in cols:
            target = f"table:{foreign}"
        key = (f"column:{col}", target)
        if key[0] not in existing_sources:
            result.append(edge(*key, "POSSIBLE_RELATION", {"kind": "INFERRED", "rule": "column_name_similarity"}, confidence=0.25, relationship="INFERRED"))
    return result


def build_graph(records: dict) -> dict:
    nodes, edges, warnings = {}, {}, []
    for record in records.values():
        for n in record["nodes"]:
            # Prefer declared metadata over an earlier observed field.
            old = nodes.get(n["id"])
            if old is None or n.get("meta", {}).get("evidence") == "DECLARED":
                nodes[n["id"]] = n
        for e in record["edges"]:
            edges[e["id"]] = e
        warnings.extend(record["warnings"])
    for e in infer_relationships(list(nodes.values()), list(edges.values())):
        edges[e["id"]] = e
    return {"version": 1, "nodes": sorted(nodes.values(), key=lambda x: x["id"]), "edges": sorted(edges.values(), key=lambda x: x["id"]), "warnings": warnings}


def files_to_scan(root: Path) -> list[Path]:
    paths = []
    for p in root.rglob("*"):
        if not p.is_file() or p.suffix.lower() not in EXTENSIONS or any(piece in IGNORED for piece in p.relative_to(root).parts):
            continue
        paths.append(p)
    return sorted(paths)


def scan(root: Path, output: Path | None = None, full: bool = False) -> dict:
    root = root.resolve()
    if not root.is_dir():
        raise ValueError(f"Not a directory: {root}")
    output = output or root / ".castor"
    output = output.resolve()
    old_path = output / "files.json"
    old = json.loads(old_path.read_text(encoding="utf-8")) if old_path.exists() and not full else {}
    records = {}
    fresh = 0
    reused = 0
    for p in files_to_scan(root):
        rel = p.relative_to(root).as_posix()
        try:
            source = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        sha = digest(source)
        if rel in old and old[rel].get("sha256") == sha:
            records[rel] = old[rel]
            reused += 1
        else:
            records[rel] = analyze(rel, source)
            fresh += 1
    graph = build_graph(records)
    output.mkdir(parents=True, exist_ok=True)
    (output / "files.json").write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
    (output / "graph.json").write_text(json.dumps(graph, ensure_ascii=False, indent=2), encoding="utf-8")
    save_sqlite(output / "index.sqlite", graph, records)
    stats = {"generated_at": datetime.now(timezone.utc).isoformat(), "root": str(root), "files": len(records), "rescanned": fresh, "cached": reused, "nodes": len(graph["nodes"]), "edges": len(graph["edges"]), "warnings": len(graph["warnings"]), "limitations": ["Static analysis only; dynamic SQL and PHP heredoc queries may be unresolved", "Observed joins do not prove physical foreign keys", "Schema metadata comes only from inspected SQL files; no live database inspected", "No code execution or database access"]}
    (output / "manifest.json").write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")
    return stats


def save_sqlite(path: Path, graph: dict, records: dict) -> None:
    with sqlite3.connect(str(path)) as db:
        db.executescript("""CREATE TABLE IF NOT EXISTS nodes (id TEXT PRIMARY KEY, type TEXT, label TEXT, meta TEXT);
        CREATE TABLE IF NOT EXISTS edges (id TEXT PRIMARY KEY, source TEXT, target TEXT, type TEXT, evidence TEXT, meta TEXT);
        CREATE INDEX IF NOT EXISTS idx_edges_source ON edges(source);
        CREATE INDEX IF NOT EXISTS idx_edges_target ON edges(target);
        CREATE INDEX IF NOT EXISTS idx_nodes_label ON nodes(label);
        CREATE TABLE IF NOT EXISTS scanned_files (path TEXT PRIMARY KEY, sha256 TEXT, queries INTEGER);
        DELETE FROM nodes; DELETE FROM edges; DELETE FROM scanned_files;""")
        db.executemany("INSERT INTO nodes VALUES (?, ?, ?, ?)", [(n["id"], n["type"], n["label"], json.dumps(n["meta"], ensure_ascii=False)) for n in graph["nodes"]])
        db.executemany("INSERT INTO edges VALUES (?, ?, ?, ?, ?, ?)", [(e["id"], e["source"], e["target"], e["type"], json.dumps(e["evidence"], ensure_ascii=False), json.dumps(e["meta"], ensure_ascii=False)) for e in graph["edges"]])
        db.executemany("INSERT INTO scanned_files VALUES (?, ?, ?)", [(p, r["sha256"], r["queries"]) for p, r in records.items()])


def subgraph(output: Path, term: str, depth: int = 2, limit: int = 120) -> dict:
    with sqlite3.connect(str(output / "index.sqlite")) as db:
        db.row_factory = sqlite3.Row
        q = "%" + term.lower().replace("%", "\\%").replace("_", "\\_") + "%"
        seeds = [r["id"] for r in db.execute("SELECT id FROM nodes WHERE lower(id) LIKE ? ESCAPE '\\' OR lower(label) LIKE ? ESCAPE '\\' LIMIT 25", (q, q))]
        found = set(seeds)
        queue = deque((i, 0) for i in seeds)
        edges = {}
        while queue and len(found) < limit:
            current, distance = queue.popleft()
            if distance >= depth:
                continue
            for row in db.execute("SELECT * FROM edges WHERE source=? OR target=? LIMIT 160", (current, current)):
                e = dict(row)
                e["evidence"] = json.loads(e["evidence"])
                e["meta"] = json.loads(e["meta"])
                other = e["target"] if e["source"] == current else e["source"]
                if other not in found and len(found) < limit:
                    found.add(other)
                    queue.append((other, distance + 1))
                if other in found:
                    edges[e["id"]] = e
        nodes = []
        for ident in sorted(found):
            r = db.execute("SELECT * FROM nodes WHERE id=?", (ident,)).fetchone()
            if r:
                d = dict(r)
                d["meta"] = json.loads(d["meta"])
                nodes.append(d)
        return {"term": term, "seeds": seeds, "nodes": nodes, "edges": list(edges.values())}


def report(output: Path) -> dict:
    p = output / "manifest.json"
    if not p.exists():
        raise FileNotFoundError(f"Run scan first: {p}")
    m = json.loads(p.read_text(encoding="utf-8"))
    g = json.loads((output / "graph.json").read_text(encoding="utf-8"))
    m["unresolved"] = g["warnings"][:150]
    return m


def export_html(output: Path, term: str = "", limit: int = 150) -> Path:
    """Dependency-free interactive SVG graph; label click reveals evidence."""
    g = json.loads((output / "graph.json").read_text(encoding="utf-8"))
    if term:
        g = subgraph(output, term, depth=3, limit=limit)
    else:
        # Prefer database-side relationships for a legible overview.
        selected = [n for n in g["nodes"] if n["type"] == "table"][:limit]
        keep = {n["id"] for n in selected}
        relations = [e for e in g["edges"] if e["type"] in {"RELATES_TO", "POSSIBLE_RELATION"}]
        for e in relations:
            keep.add(e["source"])
            keep.add(e["target"])
        g = {"nodes": [n for n in g["nodes"] if n["id"] in keep][:limit], "edges": []}
        keep = {n["id"] for n in g["nodes"]}
        g["edges"] = [e for e in relations if e["source"] in keep and e["target"] in keep]
    payload = json.dumps(g, ensure_ascii=False).replace("<", "\\u003c")
    page = r'''<!doctype html><html lang="es"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Castor Knowledge Graph</title>
<style>body{margin:0;font:14px system-ui;color:#e2e8f0;background:#101827}header{display:flex;flex-wrap:wrap;gap:12px;align-items:center;padding:16px;border-bottom:1px solid #334155}button,input{background:#253148;color:#fff;border:1px solid #64748b;border-radius:7px;padding:9px}main{display:grid;grid-template-columns:minmax(0,1fr) 330px;height:calc(100vh - 78px)}svg{width:100%;height:100%;touch-action:none}aside{border-left:1px solid #334155;padding:20px;overflow:auto}aside pre{white-space:pre-wrap;word-break:break-word}small{color:#94a3b8}text{fill:#f1f5f9;font:12px system-ui;pointer-events:none}.node{cursor:pointer}.edge{stroke:#64748b;stroke-opacity:.65}.declared{stroke:#4ade80}.observed{stroke:#38bdf8}.inferred{stroke:#fbbf24;stroke-dasharray:4 3}@media(max-width:800px){main{grid-template-columns:1fr;grid-template-rows:55vh 40vh}aside{border-left:0;border-top:1px solid #334155}}</style>
<header><strong>Castor DB Mapper</strong><input id="search" placeholder="Filtrar nodo" aria-label="Filtrar nodos"><button id="reset">Restablecer</button><small>Verde: declarada · Azul: observada · Amarillo: inferida</small></header><main><svg id="canvas" viewBox="0 0 1100 700" role="img" aria-label="Grafo de dependencias"></svg><aside><h2>Detalle</h2><p>Selecciona un nodo o relación para ver su evidencia. Desplaza para acercar; arrastra para mover el grafo.</p><pre id="detail"></pre></aside></main>
<script>const graph=__DATA__;const svg=document.getElementById('canvas'),detail=document.getElementById('detail');const NS='http://www.w3.org/2000/svg';const nodes=graph.nodes||[],edges=graph.edges||[];const ids=new Map(nodes.map((n,i)=>[n.id,i]));let scale=1,ox=0,oy=0;const cols=Math.max(1,Math.ceil(Math.sqrt(nodes.length*1.6)));nodes.forEach((n,i)=>{n.x=70+(i%cols)*Math.min(170,960/cols);n.y=70+Math.floor(i/cols)*Math.min(130,560/Math.max(1,Math.ceil(nodes.length/cols)));});function elem(name,attrs,parent){const x=document.createElementNS(NS,name);for(const[k,v]of Object.entries(attrs))x.setAttribute(k,v);parent.appendChild(x);return x}const content=elem('g',{},svg);function draw(filter=''){content.textContent='';content.setAttribute('transform',`translate(${ox} ${oy}) scale(${scale})`);for(const e of edges){const a=nodes[ids.get(e.source)],b=nodes[ids.get(e.target)];if(!a||!b)continue;if(filter&&!a.label.toLowerCase().includes(filter)&&!b.label.toLowerCase().includes(filter))continue;const kind=e.evidence?.kind||e.meta?.relationship||'';const cls=kind==='DECLARED'?'declared':kind==='INFERRED'?'inferred':'observed';const l=elem('line',{x1:a.x,y1:a.y,x2:b.x,y2:b.y,class:`edge ${cls}`,'stroke-width':1.8},content);l.onclick=()=>detail.textContent=JSON.stringify(e,null,2)}for(const n of nodes){if(filter&&!n.label.toLowerCase().includes(filter))continue;const group=elem('g',{class:'node'},content);const color={table:'#047857',column:'#7c3aed',file:'#2563eb',query:'#b45309'}[n.type]||'#64748b';elem('circle',{cx:n.x,cy:n.y,r:19,fill:color,stroke:'#e2e8f0','stroke-width':1},group);const txt=elem('text',{x:n.x+23,y:n.y+4},group);txt.textContent=n.label.length>28?n.label.slice(0,26)+'…':n.label;group.onclick=()=>detail.textContent=JSON.stringify(n,null,2);}}draw();document.getElementById('search').oninput=e=>draw(e.target.value.toLowerCase());document.getElementById('reset').onclick=()=>{scale=1;ox=0;oy=0;draw(document.getElementById('search').value.toLowerCase())};svg.addEventListener('wheel',e=>{e.preventDefault();scale=Math.min(4,Math.max(.25,scale*(e.deltaY<0?1.15:.87)));draw(document.getElementById('search').value.toLowerCase())},{passive:false});let drag;svg.addEventListener('pointerdown',e=>{drag={x:e.clientX,y:e.clientY};svg.setPointerCapture(e.pointerId)});svg.addEventListener('pointermove',e=>{if(!drag)return;ox+=e.clientX-drag.x;oy+=e.clientY-drag.y;drag={x:e.clientX,y:e.clientY};draw(document.getElementById('search').value.toLowerCase())});svg.addEventListener('pointerup',()=>drag=null);</script></html>'''
    dest = output / "graph.html"
    dest.write_text(page.replace("__DATA__", payload), encoding="utf-8")
    return dest
