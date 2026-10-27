#!/usr/bin/env python3
# Eclipse Sunset MCP server (spec: SPEC.md).
# Copyright 2026 Cyan Eclipse Technologies LLC - cetech.ai
"""Five tools, closed surface, LOCAL/fixture scope:

  ingest_snapshot     validate + hash + hash-chain-append a snapshot
  detect_sunsets      witnessed-pair sunset findings, hash-cited
  migration_diff      diff for an agent config, from witnessed schemas
  verify_sunset_claim PROVEN only with a witnessed pair, else UNPROVEN
  chain_status        hash-chain integrity check

State dir: env SUNSET_DATA_DIR, else ./data.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import sunset  # noqa: E402

SERVER_NAME = "io.github.CYAN-ECLIPSE-TECHNOLOGIES-LLC/eclipse-sunset-mcp"
SERVER_VERSION = sunset.TOOL_VERSION

_STR = {"type": "string"}
_OBJ = {"type": "object"}


def _obj(props, required):
    return {"type": "object", "properties": props,
            "required": required, "additionalProperties": False}


TOOLS = {
    "ingest_snapshot": {
        "fn": sunset.ingest_snapshot,
        "schema": _obj({"snapshot": _OBJ}, ["snapshot"]),
        "description": "Ingest a registry snapshot JSON (server_id, "
                       "version, tools[] with name/inputSchema/"
                       "deprecated). Validates, SHA-256 hashes it, and "
                       "appends it to the witnessed hash chain. Returns "
                       "snapshot id and chain position."},
    "detect_sunsets": {
        "fn": sunset.detect_sunsets,
        "schema": _obj({"server_id": _STR, "from_id": _STR,
                        "to_id": _STR}, ["server_id"]),
        "description": "Detect sunsets between two witnessed snapshots "
                       "of the same server: tools removed, tools newly "
                       "deprecated, version changes, schema-breaking "
                       "changes. Each finding cites both snapshot "
                       "hashes."},
    "migration_diff": {
        "fn": sunset.migration_diff,
        "schema": _obj({"server_id": _STR,
                        "tools_used": {"type": "array",
                                       "items": _STR},
                        "config": _OBJ, "from_id": _STR, "to_id": _STR},
                       ["server_id"]),
        "description": "Migration diff for an agent config: which used "
                       "tools are sunset in the newer witnessed "
                       "snapshot and what changed in their schemas. "
                       "Generated from witnessed before/after schemas, "
                       "not scraped docs."},
    "verify_sunset_claim": {
        "fn": sunset.verify_sunset_claim,
        "schema": _obj({"server_id": _STR, "tool_name": _STR,
                        "claim": _STR}, ["server_id", "tool_name",
                                          "claim"]),
        "description": "Verify a claim that a tool was deprecated or "
                       "removed. PROVEN only if a witnessed snapshot "
                       "pair supports it; otherwise UNPROVEN."},
    "chain_status": {
        "fn": sunset.chain_status,
        "schema": _obj({}, []),
        "description": "Verify the witnessed snapshot hash chain: "
                       "recomputes every snapshot hash and chain link."},
}


def dispatch(name, args):
    if name not in TOOLS:
        return {"refusal": "NO_SUCH_TOOL",
                "detail": "%r is not a tool here." % (name,)}
    if not isinstance(args, dict):
        raise sunset.ToolError("arguments must be an object")
    return TOOLS[name]["fn"](args)


def handle(req):
    method = req.get("method")
    rid = req.get("id")
    if method == "initialize":
        return {"jsonrpc": "2.0", "id": rid, "result": {
            "protocolVersion": "2024-11-05",
            "capabilities": {"tools": {}},
            "serverInfo": {"name": SERVER_NAME,
                           "version": SERVER_VERSION}}}
    if method == "notifications/initialized":
        return None
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": rid, "result": {"tools": [
            {"name": n, "description": t["description"],
             "inputSchema": t["schema"]}
            for n, t in TOOLS.items()]}}
    if method == "tools/call":
        params = req.get("params", {})
        try:
            result = dispatch(params.get("name"),
                              params.get("arguments", {}))
            is_err = isinstance(result, dict) and "refusal" in result
            return {"jsonrpc": "2.0", "id": rid, "result": {
                "isError": is_err,
                "content": [{"type": "text",
                             "text": json.dumps(result,
                                                sort_keys=True)}]}}
        except sunset.ToolError as e:
            return {"jsonrpc": "2.0", "id": rid, "result": {
                "isError": True,
                "content": [{"type": "text", "text": json.dumps(
                    {"error": str(e)}, sort_keys=True)}]}}
    return {"jsonrpc": "2.0", "id": rid,
            "error": {"code": -32601,
                      "message": "method not found: %s" % method}}


def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError:
            continue
        resp = handle(req)
        if resp is not None:
            sys.stdout.write(json.dumps(resp) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
