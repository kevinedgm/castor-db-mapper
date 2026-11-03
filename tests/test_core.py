import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from castor.core import analyze, endpoints, export_relations_html, relations_map, scan, subgraph, sql_tokens, export_html
from castor.adapters import adapters_for
from castor.adapters.entries import references


class AnalyzerTests(unittest.TestCase):
    def test_observed_join_without_fk(self):
        parsed = analyze("api.php", '<?php $sql = "SELECT * FROM muestras m JOIN clientes c ON m.id_cliente = c.id_cliente WHERE m.id=?"; ?>')
        relations = [e for e in parsed["edges"] if e["type"] == "RELATES_TO"]
        self.assertEqual(len(relations), 1)
        self.assertEqual(relations[0]["evidence"]["kind"], "CODE_OBSERVED")
        self.assertIn("column:muestras.id_cliente", [relations[0]["source"], relations[0]["target"]])

    def test_crud(self):
        parsed = analyze("save.php", '<?php $a = "INSERT INTO muestras (id) VALUES (?)"; $b = "UPDATE muestras SET estado=? WHERE id=?"; ?>')
        self.assertEqual(parsed["queries"], 2)
        self.assertEqual({e["type"] for e in parsed["edges"] if e["target"] == "table:muestras"}, {"WRITE"})

    def test_declared_fk(self):
        parsed = analyze("schema.sql", "CREATE TABLE muestras (id INT, cliente_id INT, CONSTRAINT fk_c FOREIGN KEY (cliente_id) REFERENCES clientes(id));")
        rel = [e for e in parsed["edges"] if e["type"] == "RELATES_TO"]
        self.assertEqual(len(rel), 1)
        self.assertEqual(rel[0]["evidence"]["kind"], "DECLARED")

    def test_strings_and_comments_are_not_sql_keywords(self):
        self.assertEqual(sql_tokens("SELECT 'FROM secret' FROM `clientes` -- JOIN password\n WHERE id=?"), ["SELECT", "?", "FROM", "clientes", "WHERE", "id", "=", "?"])

    def test_php_comments_not_indexed(self):
        parsed = analyze("ignored.php", '<?php // "DELETE FROM users"\n $x = "SELECT * FROM muestras"; ?>')
        self.assertEqual(parsed["queries"], 1)

    def test_incremental_and_deletion(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "api.php").write_text('<?php $x = "SELECT * FROM clientes"; ?>')
            first = scan(root)
            self.assertEqual(first["rescanned"], 1)
            second = scan(root)
            self.assertEqual(second["cached"], 1)
            result = subgraph(root / ".castor", "clientes")
            self.assertTrue(result["nodes"])
            page = export_html(root / ".castor")
            self.assertIn("Castor DB Mapper", page.read_text())
            (root / "api.php").unlink()
            third = scan(root)
            self.assertEqual(third["files"], 0)
            with sqlite3.connect(root / ".castor" / "index.sqlite") as db:
                self.assertEqual(db.execute("SELECT COUNT(*) FROM nodes").fetchone()[0], 0)

    def test_dynamic_not_confirmed(self):
        parsed = analyze("dyn.php", '<?php $sql = "SELECT * FROM $table WHERE id=?"; ?>')
        self.assertGreaterEqual(len(parsed["warnings"]), 1)
        self.assertFalse(any(e["target"] == "table:$table" for e in parsed["edges"]))


class AdapterTests(unittest.TestCase):
    def test_registry_routes_by_extension(self):
        self.assertEqual([a.name for a in adapters_for("x/api.php")], ["php"])
        self.assertEqual([a.name for a in adapters_for("schema.SQL")], ["sql"])
        self.assertEqual(adapters_for("app.js"), [])

    def test_references_classify_calls_and_includes(self):
        js = "// see `old.php`\nconst r = await axios.get('mod/api.php', {params});\nfetch(\"mod/save.php?_=\" + Date.now())"
        refs = references("mod/index.js", js)
        self.assertEqual([(r.target, r.kind, r.via) for r in refs], [("mod/api.php", "call", "axios"), ("mod/save.php", "call", "fetch")])
        php = "<?php require_once __DIR__ . '/db.php'; ?>"
        self.assertEqual(references("mod/api.php", php)[0].kind, "include")


class EndpointMapTests(unittest.TestCase):
    def test_front_to_endpoint_to_tables(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "mod").mkdir()
            (root / "mod" / "index.js").write_text("axios.get('mod/api.php')\nfetch('/app/mod/legacy.php')\nfetch('mod/missing.php')")
            (root / "mod" / "api.php").write_text("<?php require_once __DIR__ . '/repo.php'; ?>")
            (root / "mod" / "repo.php").write_text('<?php $q = "SELECT m.id FROM muestras m JOIN clientes c ON m.cliente_id = c.id"; ?>')
            (root / "mod" / "legacy.php").write_text('<?php $q = "UPDATE pagos SET x=?"; ?>')
            scan(root)
            result = {e["endpoint"]: e for e in endpoints(root / ".castor")["endpoints"]}
            api = result["mod/api.php"]
            self.assertEqual(api["callers"], [{"file": "mod/index.js", "line": 1, "via": "axios", "action": None}])
            self.assertEqual(api["tables"]["muestras"], {"ops": ["READ"], "from": ["mod/repo.php"]})
            self.assertEqual(api["via_includes"], ["mod/repo.php"])
            # deployment prefix /app/ is stripped by unique-suffix resolution
            self.assertEqual(result["mod/legacy.php"]["tables"]["pagos"]["ops"], ["WRITE"])
            warnings = json.loads((root / ".castor" / "graph.json").read_text())["warnings"]
            self.assertTrue(any("mod/missing.php" in w["reason"] for w in warnings))


class DispatchTests(unittest.TestCase):
    SERVER = """<?php
if (isset($_POST["action"])) {
  switch ($_POST["action"]) {
    case "lista": lista(); break;
    case "guarda":
      $q = "INSERT INTO pagos (id) VALUES (?)";
      break;
  }
}
function lista() { $s = "SELECT * FROM muestras"; helper(); }
function helper() { $t = "SELECT * FROM clientes"; }
function unrelated() { switch ($tipo) { case 'x': $u = "DELETE FROM logs"; break; } }
"""

    def test_actions_split_endpoint_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "api.php").write_text(self.SERVER)
            (root / "app.js").write_text("$.ajax({\n  url: 'api.php',\n  data: {action: 'lista'}\n});\nfetch('api.php?action=guarda')")
            scan(root)
            ep = endpoints(root / ".castor")["endpoints"][0]
            acts = {a["action"]: a for a in ep["actions"]}
            self.assertEqual(set(acts), {"lista", "guarda"})  # switch on $tipo inside a function is not dispatch
            self.assertEqual(set(acts["lista"]["tables"]), {"muestras", "clientes"})  # follows helper()
            self.assertEqual(acts["guarda"]["tables"], {"pagos": {"ops": ["WRITE"], "from": ["api.php:6"]}})
            self.assertEqual([c["line"] for c in acts["lista"]["callers"]], [2])
            self.assertEqual([c["line"] for c in acts["guarda"]["callers"]], [5])



class RelationsMapTests(unittest.TestCase):
    def test_table_pairs_aggregate_columns_and_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "a.php").write_text('<?php $q = "SELECT * FROM muestras m JOIN clientes c ON m.cliente_id = c.id"; ?>')
            (root / "b.php").write_text('<?php $q = "SELECT * FROM db.clientes c JOIN muestras m ON c.id = m.cliente_id"; ?>')
            (root / "s.sql").write_text("CREATE TABLE muestras (id INT, cliente_id INT, FOREIGN KEY (cliente_id) REFERENCES clientes(id));")
            scan(root)
            data = relations_map(root / ".castor")
            self.assertEqual(len(data["links"]), 1)  # db.clientes merged into clientes, both directions merged
            link = data["links"][0]
            self.assertEqual((link["a"], link["b"], link["kind"]), ("clientes", "muestras", "DECLARED"))
            self.assertEqual(link["n"], 3)
            self.assertEqual(link["files"], 3)
            self.assertEqual([(p["a"], p["b"]) for p in link["pairs"]], [("id", "cliente_id")])
            page = export_relations_html(root / ".castor").read_text()
            self.assertTrue(page.startswith("<!doctype html>"))
            self.assertNotIn("__CASTOR_DATA__", page)


if __name__ == "__main__":
    unittest.main()
