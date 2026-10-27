# Eclipse Sunset — SPEC v0.1

- Date: 2026-10-26 · Status: BUILT v0.1, pre-bench (builder does not certify)
- Source: Argus suggestions 2026-10-26 #10 (owner adopted)
- Repo: eclipse-sunset-mcp · Server name: io.github.CYAN-ECLIPSE-TECHNOLOGIES-LLC/eclipse-sunset-mcp
- Scope label: **LOCAL / fixture** — see §2

## 1. Product definition

MCP deprecation radar: detects deprecated / removed tools and versions
across registries and generates a migration diff for an agent's config.

Buyer: agent operators and server vendors. Funnel role: free radar feeds
paid Crosslist / listing-hygiene and re-bench work.

## 2. Scope (legally-clear, truthfully labelled)

- v0.1 ingests registry snapshot **files** (local JSON) as witnessed
  snapshots. It does NOT crawl any live registry, fetch any URL, or scrape
  any documentation. Live registry crawling is a later phase, not v0.1.
- Every claim this server returns is bounded by its witnessed snapshot
  store (hash-chained local ledger under `data/`).
- A sunset claim with no witnessed snapshot pair behind it returns
  `UNPROVEN` — never a guess, never a doc-scrape inference.
- No payment anything. No accounts, keys, credentials, or checkout.

Snapshot format (the ingested object):

```json
{
  "server_id": "example.weather-server",
  "version": "1.0.0",
  "captured_at": "2026-01-01T00:00:00Z",
  "tools": [
    {"name": "get_forecast",
     "inputSchema": {"type": "object",
                     "properties": {"location": {"type": "string"}},
                     "required": ["location"]},
     "deprecated": false}
  ]
}
```

Required: `server_id` (non-empty string), `version` (non-empty string),
`tools` (list; each item has a non-empty `name`, optional `inputSchema`
object default `{}`, optional `deprecated` bool default `false`).

## 3. NOVEL MECHANISM (the thing the bench tests)

**Sunset notices are witnessed against registry history, so a
"deprecated" claim is provable — and the migration diff is generated
from the witnessed before/after schemas, not scraped docs.**

Mechanics that implement it:

1. Each ingested snapshot is canonicalised (sorted-key JSON) and
   SHA-256 hashed (`snapshot_hash`).
2. Snapshots are hash-chained in ingest order: each ledger record
   carries `prev_hash` and `chain_hash = sha256(prev_hash + snapshot_hash)`.
   Genesis `prev_hash` is 64 zeroes. Tampering with any stored snapshot
   breaks recomputation and the chain — detectable via `chain_status`.
3. Sunset findings cite **both** snapshot hashes of the witnessed pair
   that supports them. No pair, no finding.
4. `verify_sunset_claim` returns `PROVEN` only when a witnessed pair
   (earlier snapshot where the tool was present and not deprecated,
   later snapshot of the same server where it is deprecated or removed)
   exists in the chain. All other cases return `UNPROVEN`.
5. `migration_diff` is computed by diffing the two witnessed schemas
   for the tools an agent actually uses — not from release notes,
   changelogs, or documentation text (none are ever read).

## 4. Tools (v0.1, closed surface — exactly 5)

| Tool | Args | Returns |
|---|---|---|
| `ingest_snapshot` | `snapshot` (object as §2) | `{snapshot_id, snapshot_hash, chain_hash, prev_hash, position, server_id, version}` — validates, hashes, chain-appends |
| `detect_sunsets` | `server_id`, optional `from_id`, `to_id` (snapshot_id / chain_hash / snapshot_hash; default = earliest→latest witnessed pair for that server) | Findings: `tools_removed`, `tools_newly_deprecated`, `version_change`, `schema_breaking_changes`; each finding cites both snapshot hashes |
| `migration_diff` | `server_id`, `tools_used` (list of names) or `config` (`{tools_used:[...]}` / `{tools:[...]}`), optional `from_id`/`to_id` | Per used tool: `removed` / `deprecated` / `schema_breaking` / `unchanged` / `not_in_witnessed_snapshots`, with schema-change detail for breaking tools |
| `verify_sunset_claim` | `server_id`, `tool_name`, `claim` (`deprecated` \| `removed`) | `PROVEN` + citing pair hashes, or `UNPROVEN` + reason |
| `chain_status` | (none) | `{valid, length, head_hash, checked}` — recomputes every snapshot hash and chain link; tamper → `valid:false` with first bad position |

Unknown tool names return `NO_SUCH_TOOL`.

Schema-breaking definition (deterministic, v0.1): for a tool present in
both snapshots — a property removed from `inputSchema.properties`, a
property's `type` changed, or a property newly added to
`inputSchema.required`.

## 5. Fixtures

`fixtures/` ships the same fixture server at two versions:

- `weather-v1.json` — v1.0.0: `get_forecast`, `get_alerts`,
  `legacy_lookup`, `convert_units` (none deprecated)
- `weather-v2.json` — v2.0.0: `legacy_lookup` removed, `get_alerts`
  newly deprecated, `get_forecast` schema-breaking (new required
  `units`), `convert_units` unchanged

## 6. Pricing

FREE + funnel role. Free radar; feeds paid listing-hygiene + re-bench
work. No prices, payment fields, or checkout in this server.

## 7. Novelty check (N-check) vs incumbents

- Snyk / Socket: package (library) deprecation signals only; neither
  witnesses MCP tool sunsets, neither hash-chains registry snapshots,
  neither generates a migration diff from witnessed before/after MCP
  tool schemas.
- Eclipse Sunset's novel mechanism (§3) exists nowhere in those
  products: witnessed, hash-chained MCP snapshot pairs as the sole
  evidentiary basis for a sunset claim, with `UNPROVEN` as the default
  for anything unwitnessed.

## 8. Non-goals (v0.1)

No live crawling / fetching · no scraping docs or changelogs · no
payments · no accounts/keys · no listing edits · no certification or
verdicts (bench is a separate agent/process) · no network calls at all.

## 9. Implementation

Python 3 stdlib only. MCP over stdio JSON-RPC (`initialize`,
`tools/list`, `tools/call`). Core logic in `sunset.py`, transport in
`server.py`. State dir: env `SUNSET_DATA_DIR`, else `./data`
(gitignored). Tests: `python3 -m unittest discover -s tests`.

## Addendum — Bench Fix D1 (v0.1.1, 2026-10-26)

Added after Verity bench verdict CONDITIONAL (probe 5b/5c/5d FAIL,
defect D1, HIGH). The original text above is unchanged; this addendum
extends §3 point 2 and §4.

Root cause: in v0.1.0 only `chain_status` ran chain verification;
`verify_sunset_claim`, `detect_sunsets`, and `migration_diff` trusted
`load_chain()` records, so a tampered ledger (one flipped bool in a
stored snapshot) silently minted PROVEN claims and forged findings.

Fix — every consumer of stored chain data now verifies integrity
(`verify_chain_records`) before use:

- `verify_sunset_claim`: on an invalid chain returns `UNPROVEN` with
  `chain_invalid: true`, `first_bad_position`, and a `CHAIN_INVALID`
  reason — in this tool's existing result vocabulary, never PROVEN
  and never silently UNPROVEN.
- `detect_sunsets` / `migration_diff`: on an invalid chain refuse
  with a clean machine-readable error, `CHAIN_INVALID: …` (surfaced
  as the server's standard `{"error": …}` + `isError` response); no
  findings or diff entries are emitted from a tampered ledger.
- `ingest_snapshot`: refuses with `CHAIN_INVALID` rather than extend
  a tampered chain (appending would launder the break).
- `chain_status`: unchanged — it is the verifier and reports
  `valid: false` + `first_bad_position` as before.

Regression coverage: `tests/test_sunset.py::TestChainInvalidGate`
replicates the bench tamper repro (bool flip in store record 2 →
5b/5c/5d behaviours, plus migration_diff and ingest gates).
