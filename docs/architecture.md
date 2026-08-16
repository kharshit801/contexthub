# Architecture

## System Overview

ContextHub is composed of 5 layers:

```
┌──────────────────────────────────────────────────────────────┐
│                        Interface Layer                         │
│              CLI (Rich) │ FastAPI │ Evaluation Runner          │
├──────────────────────────────────────────────────────────────┤
│                         Agent Layer                            │
│         BaselineAgent (schema-only) │ ContextHubAgent (full)  │
│                      LangGraph state machine                   │
├──────────────────────────────────────────────────────────────┤
│                         Tool Layer (MCP)                       │
│  search_assets │ get_definition │ get_trust_signal │ get_schema│
│  get_lineage │ execute_sql │ list_metrics                     │
├──────────────────────────────────────────────────────────────┤
│                        Context Layer                           │
│   ContextService → Assets, Definitions, Trust, Schema, Lineage│
├──────────────────────────────────────────────────────────────┤
│                        Data Layer                              │
│          PostgreSQL: business.* (data) + context.* (metadata) │
└──────────────────────────────────────────────────────────────┘
```

## Data Flow

### ContextHub Agent Request

```
User Question
    │
    ▼
[LangGraph Entry] ─── SystemMessage(CONTEXTHUB_PROMPT)
    │
    ▼
[Agent Node] ─── LLM decides: call tools or respond
    │
    ├──▶ [Tool Node] ─── Execute tool, log result
    │         │
    │         └──▶ [Agent Node] ─── Process result, decide next
    │                   │
    │                   ├──▶ [Tool Node] (loop)
    │                   │
    │                   └──▶ [END] ─── Final answer
    │
    └──▶ [END] ─── Direct answer (rare)
```

### Baseline Agent Request

```
User Question
    │
    ▼
[LangGraph Entry] ─── SystemMessage(BASELINE_PROMPT)
    │
    ▼
[Agent Node] ─── LLM generates SQL directly
    │
    ├──▶ [Tool Node] ─── execute_sql only
    │         │
    │         └──▶ [Agent Node] ─── Format result
    │                   │
    │                   └──▶ [END]
    │
    └──▶ [END]
```

## Database Schema

### Business Schema (business.*)

```sql
business.customers (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255),
    email VARCHAR(255) UNIQUE,
    company VARCHAR(255),
    segment ENUM(enterprise, mid_market, smb, startup),
    is_active BOOLEAN,
    created_at TIMESTAMP,
    last_order_date DATE
)

business.orders (
    id SERIAL PRIMARY KEY,
    customer_id INTEGER → customers.id,
    product_id INTEGER → products.id,
    order_date DATE,
    status ENUM(pending, confirmed, completed, cancelled, refunded),
    total_amount NUMERIC(12,2),  -- Raw price (NOT revenue)
    discount_amount NUMERIC(12,2),
    tax_amount NUMERIC(12,2),
    refund_amount NUMERIC(12,2),
    net_amount NUMERIC(12,2)     -- CERTIFIED revenue column
)

business.products (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255),
    category VARCHAR(100),
    base_price NUMERIC(12,2),
    is_active BOOLEAN,
    created_at TIMESTAMP
)

business.payments (
    id SERIAL PRIMARY KEY,
    order_id INTEGER → orders.id,
    amount NUMERIC(12,2),
    method ENUM(credit_card, debit_card, upi, net_banking, wallet),
    status ENUM(pending, completed, failed, refunded),
    paid_at TIMESTAMP,
    created_at TIMESTAMP
)
```

### Context Schema (context.*)

```sql
context.assets (id, name, asset_type, description, owner, schema_name, table_name, column_name)
context.business_definitions (id, metric_name, display_name, definition, calculation, source_table, source_column, filter_condition, owner, status)
context.trust_signals (id, asset_name, trust_level, reason, certified_by, last_validated)
context.schema_info (id, table_name, column_name, data_type, is_nullable, is_primary_key, description, business_context)
context.lineage (id, source_asset, target_asset, relationship_type, description)
```

## Security Model

```
┌─────────────┐     ┌──────────────────┐     ┌──────────────────┐
│   Agent     │────▶│  SQL Validator    │────▶│ Read-Only User   │
│             │     │                  │     │ (contexthub_     │
│ (generates  │     │ • Must start     │     │   readonly)      │
│  SQL)       │     │   with SELECT    │     │                  │
│             │     │ • No DROP/DELETE  │     │ • SELECT only    │
│             │     │ • No UPDATE      │     │ • Cannot mutate  │
│             │     │ • Auto LIMIT 100 │     │                  │
└─────────────┘     └──────────────────┘     └──────────────────┘
                           ▲
                           │ Rejected if unsafe
                           │
                    Returns error message
```

## LLM Provider Architecture

```
┌────────────────────────────────────────┐
│           get_llm() Factory            │
├────────────────────────────────────────┤
│                                        │
│  LLM_PROVIDER=gemini                   │
│    → ChatGoogleGenerativeAI            │
│    → gemini-2.0-flash (free tier)      │
│                                        │
│  LLM_PROVIDER=groq                     │
│    → ChatGroq                          │
│    → llama-3.1-70b-versatile (free)    │
│                                        │
│  LLM_PROVIDER=ollama                   │
│    → ChatOllama                        │
│    → Any local model (no API key)      │
│                                        │
└────────────────────────────────────────┘
```

## Evaluation Pipeline

```
evaluation/dataset.json (25 questions)
         │
         ▼
┌──────────────────┐
│ evaluation/runner │
│                  │
│ For each question:│
│   1. Run Baseline │──▶ Score on 5 dimensions
│   2. Run ContextHub──▶ Score on 5 dimensions
│   3. Rate limit   │
│                  │
└────────┬─────────┘
         │
         ▼
evaluation/results/eval_YYYYMMDD.json
         │
         ▼
┌──────────────────┐
│ evaluation/report │──▶ Markdown comparison report
└──────────────────┘
```

## Why These Choices?

| Component | Alternative Considered | Why Current Choice |
|-----------|----------------------|-------------------|
| LangGraph | Custom while loop | Structured state management; better observability |
| PostgreSQL context | Vector store | Context is structured with known fields; exact lookup > fuzzy search |
| MCP tools | Direct function calls | Standardized protocol; demonstrates understanding of emerging standards |
| Pydantic models | Raw dicts | Type safety; validation; documentation |
| Single DB | Separate context DB | Simplicity; one docker compose service |
| Free LLMs | OpenAI GPT-4 | Accessibility; no cost barrier to run |
| 25 questions | 100+ questions | Manageable eval time with free-tier rate limits |
