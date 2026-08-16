# ContextHub

**A structured context layer that makes AI agents more reliable over enterprise data.**

ContextHub is an engineering experiment testing whether giving an AI agent structured business context — definitions, trust signals, metadata, and lineage — improves its ability to correctly answer questions about enterprise databases, compared to a baseline agent with only schema access.

---

## Problem

Enterprise databases contain data, but not business meaning. A schema tells an LLM that `orders.total_amount` and `orders.net_amount` exist. It does not tell the LLM:

- Which one the company considers "revenue"
- Which is certified vs deprecated
- Who owns the metric
- What filters must be applied (e.g., only completed orders)
- Why one should be preferred over another

**Without this context, AI agents over enterprise data fail silently** — they produce confident answers using wrong metrics, deprecated columns, or incorrect filters. The failure mode is not a crash; it's a plausible-sounding wrong answer.

---

## Hypothesis

> Does giving an AI agent a structured context layer containing business definitions, metadata, trust signals, and lineage make it measurably more reliable at selecting correct metrics, generating correct SQL, and producing grounded answers?

---

## Architecture

```
                         User Question
                              │
                              ▼
                       ┌─────────────┐
                       │  AI Agent   │
                       │ (LangGraph) │
                       └──────┬──────┘
                              │
                         MCP Tools
                              │
                              ▼
                  ┌───────────────────────┐
                  │    Context Layer      │
                  │                       │
                  │  • Metadata           │
                  │  • Business Defs      │
                  │  • Trust Signals      │
                  │  • Schema Info        │
                  │  • Lineage            │
                  └───────────┬───────────┘
                              │
                              ▼
                       ┌─────────────┐
                       │ PostgreSQL  │
                       │ (business   │
                       │   data)     │
                       └──────┬──────┘
                              │
                              ▼
                         SQL Result
                              │
                              ▼
                      Grounded Answer
```

**Key principle:** The agent does not blindly query the database. It first consults the context layer to understand business meaning, then generates SQL based on certified definitions.

---

## How It Works

### Agent Workflow (ContextHub)

```
1. User: "What was our revenue last month?"
2. Agent → search_assets("revenue")
   → Finds: net_revenue (certified), gross_revenue (deprecated)
3. Agent → get_definition("net_revenue")
   → Returns: SUM(orders.net_amount) WHERE status = 'completed'
4. Agent → get_trust_signal("net_revenue")
   → Returns: certified, approved by CFO
5. Agent → get_schema("orders")
   → Returns: columns with business context
6. Agent → execute_sql("SELECT SUM(net_amount) FROM business.orders WHERE ...")
   → Returns: ₹48,21,320
7. Agent → Grounded answer with sources and certification status
```

### Baseline Agent (Control Group)

The baseline agent has the same schema info but **no access** to business definitions, trust signals, or context tools. It can only execute SQL based on raw column names.

---

## Context Layer

The context layer is stored as structured PostgreSQL tables (not a giant prompt or vector store):

| Component | Purpose | Example |
|-----------|---------|---------|
| **Metadata** | Asset ownership, type, description | `net_revenue` owned by Finance Team |
| **Business Definitions** | Exact metric calculations with filters | `net_revenue = SUM(net_amount) WHERE status='completed'` |
| **Trust Signals** | Certification status | `net_revenue: certified`, `gross_revenue: deprecated` |
| **Schema Info** | Enriched column descriptions with business context | `total_amount: WARNING - not revenue` |
| **Lineage** | Relationships between assets | `orders.net_amount → net_revenue metric` |

### Why Structured Storage?

Each piece of context is a queryable record with typed fields — not embedded in a prompt or retrieved via semantic search. This means:

- The agent can look up exactly what it needs (no irrelevant context flooding)
- Trust signals are first-class data, not footnotes
- Context is maintainable: update one definition, and the agent immediately uses the new version

---

## MCP Server

Tools are exposed via the [Model Context Protocol](https://modelcontextprotocol.io/), providing a standardized interface between the agent and the context/data layer.

| Tool | Purpose |
|------|---------|
| `search_assets(query)` | Find relevant tables, columns, or metrics |
| `get_definition(metric_name)` | Get certified business definition with calculation |
| `get_trust_signal(asset_name)` | Check if asset is certified/deprecated/experimental |
| `get_schema(table_name)` | Get columns with business context descriptions |
| `get_lineage(asset_name)` | Understand upstream/downstream relationships |
| `execute_sql(query)` | Run read-only SQL (SELECT only, validated) |
| `list_metrics()` | List all available metric definitions |

**Why MCP?** It decouples the agent from the underlying implementation. The agent discovers capabilities through a standard protocol rather than hardcoding internal APIs. This makes the system extensible without changing agent code.

---

## Evaluation

### Setup

Two agents are evaluated on the same 25 benchmark questions:

- **Baseline**: schema + SQL execution only
- **ContextHub**: schema + SQL + full context layer via MCP tools

### Scoring Dimensions

| Dimension | What it measures |
|-----------|-----------------|
| **Metric Selection** | Did the agent pick the correct business metric? |
| **Source Selection** | Did it use the correct table/column? |
| **SQL Correctness** | Were the right filters applied? |
| **Groundedness** | Does the answer cite actual sources? |
| **Tool Success** | Did tool calls execute without errors? |

### Benchmark Categories

- **metric_selection** (10 questions): Ambiguous metrics where context determines the right choice
- **context_awareness** (7 questions): Questions about metadata, ownership, definitions
- **trust_signal** (3 questions): Questions testing deprecated/experimental awareness
- **lineage** (1 question): Relationship understanding
- **simple_query** (4 questions): Straightforward queries (control — both should pass)

### Running Evaluation

```bash
# Run full evaluation (both agents, all 25 questions)
python -m evaluation.runner

# Run only ContextHub agent
python -m evaluation.runner --agent contexthub

# Run subset for quick testing
python -m evaluation.runner --questions 5

# Generate markdown report from results
python -m evaluation.report
```

---

## Results

> **Note:** Actual evaluation results will be generated when you run the evaluation with a configured LLM. Results depend on the specific model used.

The evaluation is designed to demonstrate differences in these key scenarios:

### Expected Failure Case: Revenue Selection

**Question:** "What was our revenue last month?"

| Agent | Metric Selected | Why |
|-------|----------------|-----|
| Baseline | `total_amount` (wrong) | Sees "total" in column name, assumes it means revenue |
| ContextHub | `net_amount` (correct) | Looks up `net_revenue` definition → certified, maps to `net_amount` with `status='completed'` filter |

### Expected Failure Case: Active Customers

**Question:** "How many active customers do we have?"

| Agent | Logic | Issue |
|-------|-------|-------|
| Baseline | `WHERE is_active = true` | Misses the 90-day recency requirement |
| ContextHub | `WHERE is_active = true AND last_order_date >= ...` | Applies certified definition |

---

## Design Decisions

| Decision | Rationale |
|----------|-----------|
| **LangGraph over custom loop** | Provides structured state management and tool-calling patterns |
| **PostgreSQL for context** | Structured, queryable context. Not a vector store — metrics have known fields, not fuzzy semantics |
| **In-process MCP tools** | Simplicity for demo. The MCP server can run standalone for production use |
| **Free-tier LLMs** | Gemini 2.0 Flash (free), Groq (free), Ollama (local). No paid API required |
| **Read-only SQL** | SQL validation + read-only DB user. Agent cannot mutate data |
| **Single PostgreSQL instance** | Business data and context in one DB (different schemas). Minimizes infrastructure |
| **25 benchmark questions** | Enough to demonstrate patterns without requiring hours of API calls |
| **No vector search** | Context is structured with known fields. Exact lookup > semantic search for definitions |

---

## Running Locally

### Prerequisites

- Python 3.11+
- Docker (for PostgreSQL)
- One of: Gemini API key (free), Groq API key (free), or Ollama installed

### Setup

```bash
# 1. Clone and enter directory
cd contexthub

# 2. Start PostgreSQL
docker compose up -d

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure environment
cp .env.example .env
# Edit .env with your LLM API key (see options below)

# 5. Seed database (business data + context layer)
python seed.py

# 6. Run the CLI
python cli.py
```

### LLM Configuration

Choose one (all free):

**Google Gemini (recommended):**
```env
LLM_PROVIDER=gemini
GEMINI_API_KEY=your-key-from-https://aistudio.google.com/apikey
```

**Groq:**
```env
LLM_PROVIDER=groq
GROQ_API_KEY=your-key-from-https://console.groq.com/keys
```

**Ollama (fully local, no API key):**
```bash
ollama pull llama3.1
```
```env
LLM_PROVIDER=ollama
OLLAMA_MODEL=llama3.1
```

### Usage

```bash
# Interactive CLI
python cli.py

# Compare both agents side-by-side
python cli.py --compare

# Single question
python cli.py -q "What was our revenue in July?"

# API server
uvicorn app.main:app --reload
# Then: POST http://localhost:8000/ask {"question": "..."}

# Run tests
pytest tests/ -v

# Run evaluation
python -m evaluation.runner
```

---

## Project Structure

```
contexthub/
├── app/
│   ├── config.py              # Pydantic settings (LLM provider, DB URL)
│   ├── main.py                # FastAPI app (/ask, /health, /metrics)
│   ├── agent/
│   │   ├── baseline.py        # LangGraph agent: schema-only
│   │   ├── contexthub.py      # LangGraph agent: full context
│   │   ├── llm.py             # LLM factory (Gemini/Groq/Ollama)
│   │   └── prompts.py         # System prompts for both agents
│   ├── context/
│   │   ├── models.py          # SQLAlchemy: assets, definitions, trust, lineage
│   │   ├── seed.py            # Seeds business definitions and trust signals
│   │   └── service.py         # Context retrieval logic
│   ├── db/
│   │   ├── connection.py      # SQLAlchemy engine (read-only support)
│   │   ├── models.py          # Business data: customers, orders, products, payments
│   │   └── seed.py            # Generates ~11K records of realistic data
│   └── mcp/
│       ├── server.py          # MCP server (stdio transport)
│       └── tools.py           # Tool implementations + SQL validation
├── evaluation/
│   ├── dataset.json           # 25 benchmark questions with expected outputs
│   ├── runner.py              # Runs both agents, scores 5 dimensions
│   └── report.py              # Generates markdown comparison report
├── tests/
│   ├── test_context.py        # Context service tests (16 tests)
│   ├── test_mcp.py            # MCP tool + SQL safety tests (17 tests)
│   └── test_agent.py          # Agent interface + scoring tests (13 tests)
├── cli.py                     # Rich interactive CLI with tool traces
├── seed.py                    # Unified seed script
├── docker-compose.yml         # PostgreSQL 16
├── requirements.txt           # Pinned dependencies
└── .env.example               # Configuration template
```

---

## Security

- **Read-only SQL execution**: The agent can only run SELECT queries. DROP/DELETE/UPDATE/INSERT/ALTER are rejected by both code validation and a read-only database user.
- **SQL injection prevention**: Queries are validated against a pattern blocklist before execution.
- **No secrets in code**: All API keys loaded from environment variables.
- **Result limits**: All queries are limited to 100 rows to prevent data exfiltration.

---

## Limitations

- **Evaluation requires LLM API calls**: Real results need actual LLM inference. Free-tier rate limits mean evaluation takes ~2 minutes.
- **Single database schema**: The demo uses 4 tables. Real enterprise environments have hundreds of tables with more complex ambiguities.
- **No multi-turn conversation**: Each question is independent. A production system would maintain conversation context.
- **Context is manually curated**: In production, context would be pulled from data catalogs rather than hand-seeded.
- **No versioning**: Context definitions don't have version history or approval workflows.
- **Limited RAG**: No unstructured document retrieval — only structured context. This is intentional to keep the experiment focused.

---

## Future Work

- **Data catalog integration**: Replace the manual context layer with live data from an enterprise data catalog API
- **Confidence scoring**: Have the agent self-assess answer confidence based on context availability
- **Multi-turn context**: Maintain conversation state for follow-up questions
- **Context freshness alerts**: Warn when context was last validated >30 days ago
- **A/B evaluation at scale**: Run evaluation across different LLMs and compare
- **Automated context ingestion**: Parse dbt schema files or data catalog exports into the context layer

---

## Tech Stack

| Component | Technology | Why |
|-----------|-----------|-----|
| Agent framework | LangGraph | Structured state + tool calling patterns |
| LLM | Gemini 2.0 Flash / Groq / Ollama | Free-tier, good function calling |
| Tool protocol | MCP (Model Context Protocol) | Standardized agent-tool interface |
| Database | PostgreSQL 16 | Single DB for data + context |
| ORM | SQLAlchemy 2.0 | Type-safe models, schema management |
| API | FastAPI | Async, auto-docs, Pydantic validation |
| CLI | Rich + Click | Beautiful terminal output for demos |
| Testing | pytest | Standard Python testing |
| Config | pydantic-settings | Validated env config |

---

*Built during a hackathon as an engineering experiment in AI agent reliability.*
