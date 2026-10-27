#!/usr/bin/env python3
# Eclipse Sunset core logic. Copyright 2026 Cyan Eclipse Technologies LLC.
"""Witnessed MCP sunset detection.

Snapshots are canonicalised + SHA-256 hashed and hash-chained in ingest
order in a local ledger (data/chain.jsonl). Sunset findings and
migration diffs are computed ONLY from witnessed snapshot pairs; a
claim with no witnessed pair behind it is UNPROVEN.
"""
import hashlib
import json
import os

GENESIS = "0" * 64
PRODUCT = "eclipse-sunset"
TOOL_VERSION = "0.1.0"


class ToolError(Exception):
    pass


def data_dir():
    return os.environ.get(
        "SUNSET_DATA_DIR",
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "data"))


def chain_path():
    return os.path.join(data_dir(), "chain.jsonl")


def canonical(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False)


def sha256_text(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def snapshot_hash(snapshot):
    return sha256_text(canonical(snapshot))


# ---------- validation ----------

def validate_snapshot(snap):
    if not isinstance(snap, dict):
        raise ToolError("snapshot must be an object")
    if not isinstance(snap.get("server_id"), str) or not snap["server_id"]:
        raise ToolError("snapshot.server_id must be a non-empty string")
    if not isinstance(snap.get("version"), str) or not snap["version"]:
        raise ToolError("snapshot.version must be a non-empty string")
    tools = snap.get("tools")
    if not isinstance(tools, list):
        raise ToolError("snapshot.tools must be a list")
    for t in tools:
        if not isinstance(t, dict) or not isinstance(t.get("name"), str) \
                or not t["name"]:
            raise ToolError("each tool must have a non-empty name")
        if "inputSchema" in t and not isinstance(t["inputSchema"], dict):
            raise ToolError("tool.inputSchema must be an object")
        if "deprecated" in t and not isinstance(t["deprecated"], bool):
            raise ToolError("tool.deprecated must be a boolean")
    return snap


# ---------- ledger ----------

def load_chain():
    path = chain_path()
    if not os.path.exists(path):
        return []
    records = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def _append(record):
    os.makedirs(data_dir(), exist_ok=True)
    with open(chain_path(), "a", encoding="utf-8") as f:
        f.write(json.dumps(record, sort_keys=True) + "\n")


def ingest_snapshot(args):
    snap = args.get("snapshot")
    validate_snapshot(snap)
    chain = load_chain()
    prev_hash = chain[-1]["chain_hash"] if chain else GENESIS
    s_hash = snapshot_hash(snap)
    c_hash = sha256_text(prev_hash + s_hash)
    record = {
        "position": len(chain) + 1,
        "snapshot_id": c_hash[:16],
        "snapshot_hash": s_hash,
        "prev_hash": prev_hash,
        "chain_hash": c_hash,
        "snapshot": snap,
    }
    _append(record)
    return {
        "product": PRODUCT, "tool_version": TOOL_VERSION,
        "scope": "LOCAL/fixture",
        "snapshot_id": record["snapshot_id"],
        "snapshot_hash": s_hash, "chain_hash": c_hash,
        "prev_hash": prev_hash, "position": record["position"],
        "server_id": snap["server_id"], "version": snap["version"],
    }


def verify_chain_records(chain):
    prev = GENESIS
    for i, rec in enumerate(chain):
        pos = i + 1
        if rec.get("position") != pos:
            return False, pos
        if rec.get("prev_hash") != prev:
            return False, pos
        s_hash = snapshot_hash(rec.get("snapshot") or {})
        if rec.get("snapshot_hash") != s_hash:
            return False, pos
        c_hash = sha256_text(prev + s_hash)
        if rec.get("chain_hash") != c_hash:
            return False, pos
        if rec.get("snapshot_id") != c_hash[:16]:
            return False, pos
        prev = c_hash
    return True, None


def chain_status(args=None):
    chain = load_chain()
    valid, bad = verify_chain_records(chain)
    out = {
        "product": PRODUCT, "tool_version": TOOL_VERSION,
        "scope": "LOCAL/fixture",
        "valid": valid, "length": len(chain), "checked": len(chain),
        "head_hash": chain[-1]["chain_hash"] if chain else GENESIS,
    }
    if not valid:
        out["first_bad_position"] = bad
    return out


# ---------- snapshot selection ----------

def _resolve(chain, server_id, ref, default_first):
    cands = [r for r in chain if r["snapshot"].get("server_id") == server_id]
    if not cands:
        raise ToolError("NO_WITNESSED_SNAPSHOTS for server %r" % server_id)
    if ref is None:
        return cands[0] if default_first else cands[-1]
    for r in cands:
        if ref in (r["snapshot_id"], r["chain_hash"], r["snapshot_hash"]):
            return r
    raise ToolError("snapshot ref not witnessed for this server: %r" % ref)


def _pair(args):
    server_id = args.get("server_id")
    if not isinstance(server_id, str) or not server_id:
        raise ToolError("server_id is required")
    chain = load_chain()
    a = _resolve(chain, server_id, args.get("from_id"), True)
    b = _resolve(chain, server_id, args.get("to_id"), False)
    if a["position"] >= b["position"]:
        raise ToolError(
            "need two distinct witnessed snapshots in ingest order "
            "(from must precede to)")
    return a, b


def _tool_map(snap):
    return {t["name"]: t for t in snap["tools"]}


def _is_dep(tool):
    return bool(tool.get("deprecated", False))


def schema_breaking_changes(name, old, new):
    """Deterministic breaking-change list between two inputSchemas."""
    changes = []
    old_s = old.get("inputSchema") or {}
    new_s = new.get("inputSchema") or {}
    old_props = old_s.get("properties") or {}
    new_props = new_s.get("properties") or {}
    for prop in sorted(set(old_props) - set(new_props)):
        changes.append({"tool": name, "kind": "property_removed",
                        "property": prop})
    for prop in sorted(set(old_props) & set(new_props)):
        ot = (old_props[prop] or {}).get("type")
        nt = (new_props[prop] or {}).get("type")
        if ot != nt:
            changes.append({"tool": name, "kind": "property_type_changed",
                            "property": prop, "from_type": ot,
                            "to_type": nt})
    old_req = set(old_s.get("required") or [])
    new_req = set(new_s.get("required") or [])
    for prop in sorted(new_req - old_req):
        changes.append({"tool": name, "kind": "required_added",
                        "property": prop})
    return changes


def _pair_ref(rec):
    return {"snapshot_id": rec["snapshot_id"],
            "snapshot_hash": rec["snapshot_hash"],
            "chain_hash": rec["chain_hash"],
            "position": rec["position"],
            "version": rec["snapshot"]["version"]}


# ---------- tools ----------

def detect_sunsets(args):
    a, b = _pair(args)
    sa, sb = a["snapshot"], b["snapshot"]
    ma, mb = _tool_map(sa), _tool_map(sb)
    cite = {"from_snapshot_hash": a["snapshot_hash"],
            "to_snapshot_hash": b["snapshot_hash"]}
    removed = [{"tool": n, **cite} for n in sorted(set(ma) - set(mb))]
    deprecated = [{"tool": n, **cite}
                  for n in sorted(set(ma) & set(mb))
                  if not _is_dep(ma[n]) and _is_dep(mb[n])]
    breaking = []
    for n in sorted(set(ma) & set(mb)):
        for ch in schema_breaking_changes(n, ma[n], mb[n]):
            breaking.append({**ch, **cite})
    return {
        "product": PRODUCT, "tool_version": TOOL_VERSION,
        "scope": "LOCAL/fixture",
        "server_id": sa["server_id"],
        "from": _pair_ref(a), "to": _pair_ref(b),
        "version_change": ({"from_version": sa["version"],
                            "to_version": sb["version"], **cite}
                           if sa["version"] != sb["version"] else None),
        "tools_removed": removed,
        "tools_newly_deprecated": deprecated,
        "schema_breaking_changes": breaking,
        "summary": {"removed": len(removed),
                    "newly_deprecated": len(deprecated),
                    "schema_breaking": len(breaking),
                    "version_changed": sa["version"] != sb["version"]},
    }


def migration_diff(args):
    a, b = _pair(args)
    sa, sb = a["snapshot"], b["snapshot"]
    ma, mb = _tool_map(sa), _tool_map(sb)
    used = args.get("tools_used")
    if used is None and isinstance(args.get("config"), dict):
        cfg = args["config"]
        used = cfg.get("tools_used") or cfg.get("tools")
    if not isinstance(used, list) or not all(
            isinstance(x, str) for x in used):
        raise ToolError("tools_used (list of tool names) is required, "
                        "directly or via config")
    entries = []
    for name in used:
        if name not in ma and name not in mb:
            entries.append({"tool": name,
                            "status": "not_in_witnessed_snapshots"})
        elif name not in mb:
            entries.append({"tool": name, "status": "removed",
                            "action": "remove usage; present in "
                                      "witnessed v%s, absent in v%s"
                                      % (sa["version"], sb["version"])})
        elif name not in ma:
            entries.append({"tool": name, "status": "added_in_newer",
                            "action": "no migration needed"})
        else:
            changes = schema_breaking_changes(name, ma[name], mb[name])
            if _is_dep(mb[name]) and not _is_dep(ma[name]):
                entries.append({"tool": name, "status": "deprecated",
                                "schema_changes": changes,
                                "action": "plan migration off this tool"})
            elif changes:
                entries.append({"tool": name,
                                "status": "schema_breaking",
                                "schema_changes": changes,
                                "action": "update calls to the witnessed "
                                          "newer schema"})
            elif _is_dep(mb[name]):
                entries.append({"tool": name,
                                "status": "already_deprecated",
                                "action": "plan migration off this tool"})
            else:
                entries.append({"tool": name, "status": "unchanged",
                                "action": "none"})
    return {
        "product": PRODUCT, "tool_version": TOOL_VERSION,
        "scope": "LOCAL/fixture",
        "server_id": sa["server_id"],
        "from": _pair_ref(a), "to": _pair_ref(b),
        "generated_from": "witnessed before/after schemas",
        "diff": entries,
        "summary": {
            "used": len(entries),
            "affected": sum(1 for e in entries if e["status"] in
                            ("removed", "deprecated", "schema_breaking"))},
    }


def verify_sunset_claim(args):
    server_id = args.get("server_id")
    tool = args.get("tool_name")
    claim = args.get("claim")
    if claim is None and isinstance(args.get("claim_type"), str):
        claim = args["claim_type"]
    if not isinstance(server_id, str) or not server_id:
        raise ToolError("server_id is required")
    if not isinstance(tool, str) or not tool:
        raise ToolError("tool_name is required")
    if claim not in ("deprecated", "removed"):
        raise ToolError("claim must be 'deprecated' or 'removed'")
    chain = load_chain()
    cands = [r for r in chain
             if r["snapshot"].get("server_id") == server_id]
    base = {"product": PRODUCT, "tool_version": TOOL_VERSION,
            "scope": "LOCAL/fixture", "server_id": server_id,
            "tool_name": tool, "claim": claim}
    if len(cands) < 2:
        return {**base, "result": "UNPROVEN",
                "reason": "fewer than two witnessed snapshots for "
                          "this server"}
    for i in range(len(cands)):
        ma = _tool_map(cands[i]["snapshot"])
        if tool not in ma or _is_dep(ma[tool]):
            continue
        for j in range(i + 1, len(cands)):
            mb = _tool_map(cands[j]["snapshot"])
            hit = (tool not in mb) if claim == "removed" else \
                (tool in mb and _is_dep(mb[tool]))
            if hit:
                return {**base, "result": "PROVEN",
                        "from": _pair_ref(cands[i]),
                        "to": _pair_ref(cands[j]),
                        "from_snapshot_hash": cands[i]["snapshot_hash"],
                        "to_snapshot_hash": cands[j]["snapshot_hash"]}
    return {**base, "result": "UNPROVEN",
            "reason": "no witnessed snapshot pair supports this claim"}


TOOLS_IMPL = {
    "ingest_snapshot": ingest_snapshot,
    "detect_sunsets": detect_sunsets,
    "migration_diff": migration_diff,
    "verify_sunset_claim": verify_sunset_claim,
    "chain_status": chain_status,
}
