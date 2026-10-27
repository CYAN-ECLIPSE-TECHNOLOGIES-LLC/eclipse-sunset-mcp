import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import sunset  # noqa: E402
import server  # noqa: E402

ROOT = os.path.join(os.path.dirname(__file__), "..")
FIX = os.path.join(ROOT, "fixtures")


def load(name):
    with open(os.path.join(FIX, name), encoding="utf-8") as f:
        return json.load(f)


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old = os.environ.get("SUNSET_DATA_DIR")
        os.environ["SUNSET_DATA_DIR"] = self.tmp.name

    def tearDown(self):
        if self.old is None:
            os.environ.pop("SUNSET_DATA_DIR", None)
        else:
            os.environ["SUNSET_DATA_DIR"] = self.old
        self.tmp.cleanup()

    def ingest_fixtures(self):
        r1 = sunset.ingest_snapshot({"snapshot": load("weather-v1.json")})
        r2 = sunset.ingest_snapshot({"snapshot": load("weather-v2.json")})
        return r1, r2


class TestIngestChain(Base):
    def test_ingest_and_chain(self):
        r1, r2 = self.ingest_fixtures()
        self.assertEqual(r1["position"], 1)
        self.assertEqual(r2["position"], 2)
        self.assertEqual(r1["prev_hash"], "0" * 64)
        self.assertEqual(r2["prev_hash"], r1["chain_hash"])
        self.assertNotEqual(r1["snapshot_hash"], r2["snapshot_hash"])
        st = sunset.chain_status({})
        self.assertTrue(st["valid"])
        self.assertEqual(st["length"], 2)
        self.assertEqual(st["head_hash"], r2["chain_hash"])

    def test_invalid_snapshot_rejected(self):
        with self.assertRaises(sunset.ToolError):
            sunset.ingest_snapshot({"snapshot": {"server_id": "x"}})
        with self.assertRaises(sunset.ToolError):
            sunset.ingest_snapshot({"snapshot": {
                "server_id": "x", "version": "1",
                "tools": [{"name": 5}]}})

    def test_tamper_detection(self):
        self.ingest_fixtures()
        path = sunset.chain_path()
        with open(path, encoding="utf-8") as f:
            lines = f.readlines()
        rec = json.loads(lines[0])
        rec["snapshot"]["version"] = "9.9.9"
        lines[0] = json.dumps(rec, sort_keys=True) + "\n"
        with open(path, "w", encoding="utf-8") as f:
            f.writelines(lines)
        st = sunset.chain_status({})
        self.assertFalse(st["valid"])
        self.assertEqual(st["first_bad_position"], 1)


class TestDetect(Base):
    def test_sunset_detection_on_fixtures(self):
        self.ingest_fixtures()
        out = sunset.detect_sunsets({"server_id": "example.weather-server"})
        self.assertEqual([x["tool"] for x in out["tools_removed"]],
                         ["legacy_lookup"])
        self.assertEqual(
            [x["tool"] for x in out["tools_newly_deprecated"]],
            ["get_alerts"])
        self.assertEqual(out["version_change"]["from_version"], "1.0.0")
        self.assertEqual(out["version_change"]["to_version"], "2.0.0")
        breaking = out["schema_breaking_changes"]
        self.assertEqual(len(breaking), 1)
        self.assertEqual(breaking[0]["tool"], "get_forecast")
        self.assertEqual(breaking[0]["kind"], "required_added")
        self.assertEqual(breaking[0]["property"], "units")
        # every finding cites both hashes
        for finding in (out["tools_removed"] + out["tools_newly_deprecated"]
                        + breaking):
            self.assertEqual(finding["from_snapshot_hash"],
                             out["from"]["snapshot_hash"])
            self.assertEqual(finding["to_snapshot_hash"],
                             out["to"]["snapshot_hash"])

    def test_detect_requires_pair(self):
        sunset.ingest_snapshot({"snapshot": load("weather-v1.json")})
        with self.assertRaises(sunset.ToolError):
            sunset.detect_sunsets({"server_id": "example.weather-server"})


class TestMigrationDiff(Base):
    def test_migration_diff_content(self):
        self.ingest_fixtures()
        cfg = load("agent-config.json")
        out = sunset.migration_diff(
            {"server_id": cfg["server_id"], "tools_used": cfg["tools_used"]})
        by = {e["tool"]: e for e in out["diff"]}
        self.assertEqual(by["legacy_lookup"]["status"], "removed")
        self.assertEqual(by["get_alerts"]["status"], "deprecated")
        self.assertEqual(by["get_forecast"]["status"], "schema_breaking")
        self.assertEqual(by["get_forecast"]["schema_changes"][0]["property"],
                         "units")
        self.assertEqual(by["convert_units"]["status"], "unchanged")
        self.assertEqual(out["summary"]["affected"], 3)
        self.assertEqual(out["generated_from"],
                         "witnessed before/after schemas")

    def test_migration_diff_via_config(self):
        self.ingest_fixtures()
        out = sunset.migration_diff(
            {"server_id": "example.weather-server",
             "config": {"tools": ["legacy_lookup"]}})
        self.assertEqual(out["diff"][0]["status"], "removed")


class TestClaims(Base):
    def test_witnessed_claims_proven(self):
        self.ingest_fixtures()
        d = sunset.verify_sunset_claim(
            {"server_id": "example.weather-server",
             "tool_name": "get_alerts", "claim": "deprecated"})
        self.assertEqual(d["result"], "PROVEN")
        self.assertIn("from_snapshot_hash", d)
        r = sunset.verify_sunset_claim(
            {"server_id": "example.weather-server",
             "tool_name": "legacy_lookup", "claim": "removed"})
        self.assertEqual(r["result"], "PROVEN")

    def test_unwitnessed_claim_unproven(self):
        self.ingest_fixtures()
        # tool never witnessed
        u = sunset.verify_sunset_claim(
            {"server_id": "example.weather-server",
             "tool_name": "never_existed", "claim": "removed"})
        self.assertEqual(u["result"], "UNPROVEN")
        # tool witnessed but unchanged
        u2 = sunset.verify_sunset_claim(
            {"server_id": "example.weather-server",
             "tool_name": "convert_units", "claim": "deprecated"})
        self.assertEqual(u2["result"], "UNPROVEN")
        # wrong claim type for a witnessed change
        u3 = sunset.verify_sunset_claim(
            {"server_id": "example.weather-server",
             "tool_name": "get_alerts", "claim": "removed"})
        self.assertEqual(u3["result"], "UNPROVEN")
        # no snapshots at all for server
        u4 = sunset.verify_sunset_claim(
            {"server_id": "unknown.server", "tool_name": "x",
             "claim": "removed"})
        self.assertEqual(u4["result"], "UNPROVEN")


class TestServerSurface(Base):
    def test_tools_list_exactly_five(self):
        resp = server.handle({"method": "tools/list", "id": 1})
        names = [t["name"] for t in resp["result"]["tools"]]
        self.assertEqual(names, ["ingest_snapshot", "detect_sunsets",
                                 "migration_diff", "verify_sunset_claim",
                                 "chain_status"])

    def test_unknown_tool_refused_by_name(self):
        resp = server.handle({"method": "tools/call", "id": 2, "params": {
            "name": "crawl_registry", "arguments": {}}})
        body = json.loads(resp["result"]["content"][0]["text"])
        self.assertEqual(body["refusal"], "NO_SUCH_TOOL")
        self.assertTrue(resp["result"]["isError"])

    def test_initialize(self):
        resp = server.handle({"method": "initialize", "id": 3,
                              "params": {}})
        self.assertEqual(
            resp["result"]["serverInfo"]["name"],
            "io.github.CYAN-ECLIPSE-TECHNOLOGIES-LLC/eclipse-sunset-mcp")


if __name__ == "__main__":
    unittest.main()
