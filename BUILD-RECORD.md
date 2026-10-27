# BUILD RECORD — v0.1 (2026-10-26)

**Status: BUILT, pre-bench. STOP — Verity benches next; no self-certification.**
Scope label: **LOCAL / fixture**

## What was built

Five tools, closed surface, Python 3 stdlib only, MCP over stdio
JSON-RPC (`initialize`, `tools/list`, `tools/call`):

- `ingest_snapshot` — validates snapshot JSON, SHA-256 over canonical
  JSON, hash-chain append (`chain_hash = sha256(prev_hash +
  snapshot_hash)`, genesis prev = 64 zeroes) to `data/chain.jsonl`;
  returns snapshot_id (chain_hash[:16]) + 1-based chain position.
- `detect_sunsets` — witnessed-pair findings: tools removed, tools
  newly deprecated, version change, schema-breaking changes (property
  removed / property type changed / required added). Every finding
  cites both snapshot hashes.
- `migration_diff` — per used tool: removed / deprecated /
  schema_breaking (with witnessed schema-change detail) / unchanged /
  not_in_witnessed_snapshots; generated from witnessed before/after
  schemas only.
- `verify_sunset_claim` — `PROVEN` only with a witnessed pair
  (present + not deprecated earlier, deprecated/removed later);
  all other cases `UNPROVEN` with reason.
- `chain_status` — recomputes every snapshot hash + chain link;
  tamper → `valid:false` + `first_bad_position`.

Fixtures: `fixtures/weather-v1.json` (v1.0.0) + `weather-v2.json`
(v2.0.0), same server `example.weather-server` — `legacy_lookup`
removed, `get_alerts` deprecated, `get_forecast` schema-breaking
(new required `units`), `convert_units` unchanged; plus
`fixtures/agent-config.json`.

## Verification at build

- Suite: 12/12 (`python3 -m unittest discover -s tests`) — ingest+chain,
  invalid-snapshot rejection, tamper detection, sunset detection on
  fixtures (incl. hash citation on every finding), migration diff
  content (direct + via config), witnessed claims PROVEN, unwitnessed
  claims UNPROVEN (never-seen tool, unchanged tool, wrong claim type,
  unknown server), tools/list exactly 5, unknown tool NO_SUCH_TOOL,
  initialize server name.
- Smoke over stdio: SMOKE_OK — initialize, 5 tools, ingest v1+v2
  (positions 1/2, chain-linked), detect summary
  {removed:1, newly_deprecated:1, schema_breaking:1, version_changed:true},
  unwitnessed claim → UNPROVEN.
- Secret sweep before first commit: no matches (grep for token/key/
  secret/password/private-key patterns over the tree).
- Spec copy: `SPEC.md` copied byte-identical to
  `~/workspace/cyan-eclipse/argus-batch-20261026/specs/eclipse-sunset-mcp-SPEC.md`
  (diff verified).

## Notes for Verity

- Default pair selection in detect/migration: earliest → latest
  witnessed snapshot for the server; explicit `from_id`/`to_id` accept
  snapshot_id, chain_hash, or snapshot_hash.
- No network code exists in the package (no crawl/fetch path to test —
  absence is structural, stdlib imports are hashlib/json/os/sys only).
- Pricing: FREE + funnel (spec §6); no price figures, payment fields,
  or checkout anywhere.
