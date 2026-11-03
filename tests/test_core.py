import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from castor.core import analyze, scan, subgraph, sql_tokens, export_html


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


if __name__ == "__main__":
    unittest.main()
