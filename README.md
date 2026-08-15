# 📋 Data Contract Validator

A LangGraph RAG agent that validates Iceberg schemas, dbt model definitions, and SQL DDL against YAML data contracts stored in a Qdrant vector database.

**Stack:** FastAPI · LangGraph · Claude (Anthropic) · Qdrant · React/Vite

---

## How It Works

Paste a schema. The agent runs a 6-node graph:

```
parse_schema → retrieve_contracts → match_contract → validate_schema → validate_rules → generate_report
```

1. **parse_schema** — normalizes Iceberg JSON / dbt YAML / SQL DDL into a common column format
2. **retrieve_contracts** — semantic search in Qdrant finds candidate contracts
3. **match_contract** — Claude picks the best-fit contract for the incoming table
4. **validate_schema** — structural checks: missing columns, type mismatches, nullability violations
5. **validate_rules** — semantic checks: LLM evaluates each contract rule against the schema
6. **generate_report** — final report with PASS / WARN / FAIL status and all violations

Violations are classified as **ERROR** (blocks deployment) or **WARNING** (flagged for review).

---

## Project Structure

```
data-contract-validator/
├── backend/
│   ├── config/settings.py         # All parameters, env-driven
│   ├── graph/agent.py             # LangGraph 6-node state machine
│   ├── services/
│   │   ├── llm.py                 # Claude wrapper
│   │   ├── vectorstore.py         # Qdrant ingest + retrieval
│   │   ├── contract_loader.py     # YAML contract parser
│   │   └── schema_parser.py       # Iceberg / dbt / SQL normalizer
│   ├── api/routes.py              # FastAPI endpoints
│   └── main.py                    # Uvicorn entrypoint
├── frontend/
│   ├── src/
│   │   ├── App.jsx                # Main UI
│   │   └── api/client.js          # FastAPI client
│   └── vite.config.js
├── contracts/sample/
│   ├── fact_orders_contract.yml
│   ├── user_events_contract.yml
│   └── dim_customers_contract.yml
├── schemas/sample/               # Test schemas with violations
│   ├── fact_orders_iceberg_with_violations.json
│   ├── fact_user_events_dbt_with_violations.yml
│   └── dim_customers_ddl_with_violations.sql
├── docker-compose.yml
├── Dockerfile.backend
├── requirements.txt
└── .env.example
```

---

## Quickstart — Local

### 1. Configure

```bash
cp .env.example .env
# Set ANTHROPIC_API_KEY in .env
```

### 2. Start Qdrant

```bash
docker compose up qdrant -d
```

### 3. Backend

Requires **Python 3.11 or 3.12** (3.14 is not supported by pinned dependencies such as `pydantic`).

```bash
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m backend.main
# → http://localhost:8000
# → http://localhost:8000/docs  (Swagger)
```

### 4. Ingest sample contracts

```bash
curl -X POST http://localhost:8000/api/ingest \
  -H "Content-Type: application/json" \
  -d '{"contracts_dir": "./contracts/sample"}'
```

Or use the **Contracts tab → ingest contracts/sample** button in the UI.

### 5. Frontend

```bash
cd frontend
npm install && npm run dev
# → http://localhost:5173
```

---

## Quickstart — Docker

```bash
cp .env.example .env   # set ANTHROPIC_API_KEY
docker compose up --build
cd frontend && npm install && npm run dev
# → http://localhost:5173
```

---

## API Reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/validate` | Run validation agent on a schema |
| `POST` | `/api/ingest` | Ingest YAML contracts into Qdrant |
| `GET` | `/api/contracts` | List all contracts in the directory |
| `GET` | `/api/collection` | Qdrant collection status |
| `GET` | `/api/settings` | Active config (no secrets) |
| `GET` | `/api/health` | Health check |

### Validate — Iceberg

```bash
curl -X POST http://localhost:8000/api/validate \
  -H "Content-Type: application/json" \
  -d '{
    "raw_schema": "{\"identifier\": \"warehouse.fact_orders\", \"fields\": [{\"name\": \"order_id\", \"type\": \"bigint\", \"optional\": false}]}",
    "schema_type": "iceberg"
  }'
```

### Validate — dbt

```bash
curl -X POST http://localhost:8000/api/validate \
  -H "Content-Type: application/json" \
  -d '{
    "raw_schema": "models:\n  - name: fact_orders\n    columns:\n      - name: order_id\n        data_type: bigint",
    "schema_type": "dbt"
  }'
```

### Validate — SQL DDL

```bash
curl -X POST http://localhost:8000/api/validate \
  -H "Content-Type: application/json" \
  -d '{
    "raw_schema": "CREATE TABLE warehouse.fact_orders (order_id BIGINT NOT NULL, customer_id BIGINT);",
    "schema_type": "sql"
  }'
```

---

## Writing Data Contracts

Drop YAML files into `./contracts/` and re-ingest. Schema:

```yaml
name: my_table_contract
version: "1.0"
table: warehouse.my_table          # must match table name in schemas
owner: team@company.com
description: What this table contains and who uses it.

sla:
  freshness_hours: 1
  availability_pct: 99.9

schema:
  - name: id
    type: bigint
    nullable: false
    description: Primary key
    tests: [unique, not_null]

  - name: email
    type: varchar
    nullable: false
    pii: true                       # marks column as PII
    description: Customer email

rules:
  - severity: ERROR
    description: id must be unique and never null
  - severity: WARNING
    description: email should follow RFC 5321 format
```

**Severity levels:**
- `ERROR` — hard violation, schema should not be deployed
- `WARNING` — soft violation, flagged for review

---

## Configuration

All parameters in `.env`:

| Variable | Default | Description |
|----------|---------|-------------|
| `ANTHROPIC_API_KEY` | required | Claude API key |
| `LLM_MODEL` | `claude-3-5-sonnet-20241022` | Model |
| `LLM_TEMPERATURE` | `0.1` | Low = deterministic validation |
| `QDRANT_HOST` | `localhost` | Use `qdrant` inside docker-compose |
| `COLLECTION_NAME` | `data_contracts` | Qdrant collection |
| `RETRIEVAL_TOP_K` | `5` | Contracts retrieved per query |
| `CONTRACTS_DIR` | `./contracts` | Default ingest directory |

---

## Troubleshooting

**`No contract matched`** — run ingest first, check `/api/contracts` to confirm contracts are loaded.

**Schema parse error** — paste the raw content of one of the sample files in `schemas/sample/` to confirm the format.

**Backend unreachable in UI** — confirm backend is on port 8000 and CORS includes `http://localhost:5173`.

**`ModuleNotFoundError`** — run from project root: `python -m backend.main`.
