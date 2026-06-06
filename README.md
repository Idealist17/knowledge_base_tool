# Audit Knowledge Base Tool

This is a Python command-line tool for building a reusable smart-contract audit knowledge graph from local source code and audit notes. It extracts protocol semantics, vulnerability findings, and relationships between them, stores the result in SQLite, and can export the graph to DOT or an interactive HTML view.

```text
Source code + audit material
  -> category JSON calls
  -> agentic semantic/finding extraction via tool calls
  -> normalization + retry
  -> merge -> linking -> SQLite KG -> DOT/HTML export
```

The project is designed to be easy to run locally, simple to inspect, and structured around a clear data flow.

## Features

- Load explicit local projects with optional audit reports.
- Load C4-style fixture directories with `contracts/`, `reports/`, or `audits/` folders.
- Classify projects by DeFi category.
- Extract project-level semantics from Solidity source chunks with agentic `report_semantic` / `finish` tool calls.
- Extract audit findings with agentic `report_finding` / `finish` tool calls and map them to a vulnerability taxonomy.
- Retry failed semantic/finding extraction chunks once with a fresh agent buffer before failing the chunk.
- Deduplicate and merge similar semantics/findings into canonical graph nodes, including same-title findings with different root causes.
- Link findings back to related protocol behavior.
- Persist the knowledge graph in SQLite.
- Export graph snapshots as DOT or browser-friendly HTML.
- Run tests with a mocked LLM client, so CI does not require an API key.

## Install

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
```

Edit `.env` to use your own LLM endpoint:

```bash
OPENAI_API_KEY=your-api-key
OPENAI_MODEL=your-model-name
OPENAI_BASE_URL=https://your-openai-compatible-endpoint.example.com/v1
```

`OPENAI_BASE_URL` is optional for the default OpenAI endpoint. For a relay or local gateway, the endpoint must support `POST /chat/completions`, JSON response mode, and Chat Completions tool/function calls. Semantics and findings are submitted through tools; categories, merges, and links still use JSON responses.

## Quick start

```bash
learnkg init-db --db sqlite:///kg.sqlite3

learnkg learn-c4 \
  --db sqlite:///kg.sqlite3 \
  --c4-dir tests/fixtures/c4 \
  --limit 2 \
  --link

learnkg list-projects --db sqlite:///kg.sqlite3
learnkg search-semantics --db sqlite:///kg.sqlite3 --keyword vault
learnkg export-dot --db sqlite:///kg.sqlite3 --out kg.dot
learnkg export-html --db sqlite:///kg.sqlite3 --out kg.html
```

Open `kg.html` in a browser to inspect the generated graph.

## Loading explicit projects

Use `learn-projects` when you already know the source directory and, optionally, the audit report path:

```bash
learnkg learn-projects \
  --db sqlite:///kg.sqlite3 \
  --project "vault:/path/to/vault[:platform_id]" \
  --report vault:/path/to/vault/audit.md \
  --link
```

If a project has no report, the pipeline only extracts source-code semantics.

## Loading C4-style datasets

`learn-c4` expects a dataset root with `contracts/` plus `reports/` or `audits/`. Common supported layouts include:

```text
contracts/420/
contracts/c4-420/
contracts/2023-xx-project-name/
reports/420.md
reports/c4-420.md
audits/420.md
audits/420/
```

Useful filters:

```bash
learnkg learn-c4 --db sqlite:///kg.sqlite3 --c4-dir /path/to/data --limit 5
learnkg learn-c4 --db sqlite:///kg.sqlite3 --c4-dir /path/to/data --c4-ids 101,102,103
learnkg learn-c4 --db sqlite:///kg.sqlite3 --c4-dir /path/to/data --skip-ids 101
```


## Crawling Code4rena data

The repository includes a standard-library-only crawler that downloads Code4rena report pages and matching GitHub source repositories into the same directory layout consumed by `learn-c4`:

```bash
python scripts/crawl_c4.py --years 2024 --out datasets/c4-2024 --concurrency 4

learnkg learn-c4 \
  --db sqlite:///kg.sqlite3 \
  --c4-dir datasets/c4-2024 \
  --limit 5 \
  --link
```

The crawler writes:

```text
datasets/c4-2024/
  audits/<id>.json
  reports/<id>.md
  contracts/<id>/
  manifest.json
  failures.jsonl
```

`contracts/`, `reports/`, and `audits/` are the inputs required by `learn-c4`, so the crawled directory can be used directly as `--c4-dir`. If GitHub rate limits become a problem, set `GITHUB_TOKEN` env variable before running the crawler.

## Pipeline stages

1. Load source files and report material.
2. Chunk long inputs by token budget.
3. Classify the project into DeFi categories with JSON-mode model output.
4. Extract source-code semantics with `report_semantic` tool calls and close each chunk with `finish`.
5. Extract audit findings with `report_finding` tool calls and close each report chunk with `finish`.
6. Retry a failed semantic/finding chunk once with a fresh buffer; failed attempts never write partial extracted items.
7. Normalize tool arguments into typed Pydantic models and deduplicate within the project.
8. Merge duplicate or near-duplicate graph nodes.
9. Link findings back to same-project semantics, then write projects, categories, semantic nodes, findings, and links into SQLite.
10. Optionally run global canonical semantic-to-finding linking and export DOT/HTML graph views.

## Agentic extraction behavior

Semantic and finding extraction are tool-call workflows rather than free-form JSON output:

- `report_semantic` records one project-agnostic behavior with `name`, `category`, `definition`, `description`, and source `functions` using Python field names `contract_path` and `function_name`.
- `report_finding` records one vulnerability mechanism with `title`, `severity`, `category`, `subcategory`, `root_cause`, `description`, `patterns`, and `exploits`.
- `finish` is required once per chunk. If a model emits invalid tool arguments, the chunk is retried once from scratch with a new buffer. Partial results from failed attempts are discarded.
- Finding extraction supports atomic decomposition: one original report title may produce multiple findings when the root causes are independently exploitable. Deduplication therefore uses title plus root cause, not title alone.

## SQLite graph model

The schema is still under construction but it is optimized for readability:

- `project`, `project_platform`, `category`, `project_category`
- `semantic_node`, `semantic_function`, `project_semantic`, `semantic_merge`, `pending_semantic`
- `audit_finding`, `finding_category`, `audit_finding_category`, `project_finding`, `finding_merge`
- `semantic_finding_link`, `finding_link_status`

`semantic_node` and `audit_finding` keep both raw provenance rows and canonical rows. Merge tables preserve where a raw item was consolidated, which makes the exported graph useful for explaining both project-specific evidence and cross-project patterns.

## Development

```bash
.venv/bin/pytest -q
```

The test suite uses `MockLLMClient` for deterministic extraction, merge, and linking behavior. Agentic extraction tests model tool-call scripts such as:

```python
[
    {"tool": "report_finding", "args": {"title": "...", "severity": "High", "category": "...", "subcategory": "...", "root_cause": "...", "description": "...", "patterns": "...", "exploits": "..."}},
    {"tool": "finish", "args": {"summary": "done"}},
]
```

## Notes

This is a local-first tool. SQLite is the supported storage backend, and the source loader currently focuses on Solidity-oriented project trees plus Markdown audit material. The code is structured so additional loaders, exporters, or storage adapters can be added without changing the pipeline entry points.
