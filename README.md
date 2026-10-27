# Eclipse Sunset

MCP deprecation radar — detects deprecated/removed tools and versions
from witnessed registry snapshots and generates a migration diff for an
agent's config.

**Scope label: LOCAL / fixture.** v0.1 ingests local registry snapshot
JSON files only. It does not crawl live registries. Live crawling is a
later phase.

**Status: v0.1.1 — CERTIFIED (local, fixture)** (Verity re-bench,
2026-10-26: probe 5 chain-attack suite 4/4 + strict extras 9/9, full
prior suite 44/44; D1 closed). Spec: `SPEC.md`.

## Novel mechanism

Sunset notices are witnessed against registry history, so a
"deprecated" claim is provable — and the migration diff is generated
from the witnessed before/after schemas, not scraped docs.

Each ingested snapshot is SHA-256 hashed over its canonical JSON and
hash-chained in ingest order (`chain_hash = sha256(prev_hash +
snapshot_hash)`). Findings cite both snapshot hashes of the witnessed
pair. A claim with no witnessed pair behind it returns `UNPROVEN`.

## Tools (exactly 5)

| Tool | What it does |
|---|---|
| `ingest_snapshot` | Validate a snapshot (`server_id`, `version`, `tools[]` with `name`/`inputSchema`/`deprecated`), hash it, chain-append it; returns snapshot id + chain position. |
| `detect_sunsets` | Between two witnessed snapshots of the same server: tools removed, tools newly deprecated, version changes, schema-breaking changes — each finding cites both snapshot hashes. |
| `migration_diff` | Given a server + an agent config listing tools used, produce the diff: which used tools are sunset in the newer witnessed snapshot and what changed in their schemas. |
| `verify_sunset_claim` | Claim "tool X deprecated/removed" → `PROVEN` only if a witnessed snapshot pair supports it, else `UNPROVEN`. |
| `chain_status` | Verify hash-chain integrity (recomputes every hash + link; tamper → `valid: false`). |

## Fixtures

`fixtures/weather-v1.json` and `fixtures/weather-v2.json`: the same
fixture server at v1.0.0 / v2.0.0 — one tool removed (`legacy_lookup`),
one deprecated (`get_alerts`), one schema-breaking change
(`get_forecast` gains required `units`), one unchanged
(`convert_units`). `fixtures/agent-config.json` is a sample agent
config for `migration_diff`.

## Pricing

FREE + funnel role — free radar feeds paid listing-hygiene and
re-bench work. No payment anything in this server.

## Run

```
python3 server.py            # MCP over stdio JSON-RPC
python3 -m unittest discover -s tests -v
```

State (the witnessed chain ledger) lives in `data/` or the directory
named by `SUNSET_DATA_DIR`.

Python 3, standard library only.

MIT License · Copyright © 2026 Cyan Eclipse Technologies LLC · cetech.ai
