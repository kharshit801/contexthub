"""ContextHub agent - uses structured context to answer questions reliably.

This agent forces a deterministic workflow:
1. Search for relevant assets
2. Get the definition of the best metric
3. Check trust signal
4. Execute SQL based on the definition
5. Use LLM to format the final answer

This approach doesn't rely on the LLM to decide tool ordering.
"""

import json
import logging
import time
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from app.agent.llm import get_llm
from app.agent.prompts import CONTEXTHUB_SYSTEM_PROMPT
from app.mcp.tools import ContextTools

logger = logging.getLogger(__name__)

_tools = ContextTools()


class ContextHubAgent:
    """Context-aware agent with deterministic tool workflow.

    Forces: search → definition → trust → SQL → answer
    """

    def __init__(self):
        self.name = "contexthub"

    def ask(self, question: str) -> dict[str, Any]:
        """Ask the ContextHub agent a question.

        Executes a deterministic workflow:
        1. Search assets for the topic
        2. Get metric definition
        3. Check trust signal
        4. Execute SQL if a calculation is needed
        5. Format answer with LLM
        """
        start_time = time.time()
        tool_calls_log = []
        sources = []

        try:
            # Step 1: Search for relevant assets
            search_query = self._extract_topic(question)
            search_result = _tools.search_assets(search_query)
            tool_calls_log.append({"tool": "search_assets", "args": {"query": search_query}, "result_preview": json.dumps(search_result, default=str)[:500]})

            # Step 2: Find the best metric and get its definition
            metric_name = self._pick_best_metric(search_result)
            definition = None
            if metric_name:
                definition = _tools.get_definition(metric_name)
                tool_calls_log.append({"tool": "get_definition", "args": {"metric_name": metric_name}, "result_preview": json.dumps(definition, default=str)[:500]})

            # Step 3: Check trust signal
            trust = None
            if metric_name:
                trust = _tools.get_trust_signal(metric_name)
                tool_calls_log.append({"tool": "get_trust_signal", "args": {"asset_name": metric_name}, "result_preview": json.dumps(trust, default=str)[:500]})
                if trust and "trust_level" in trust:
                    sources.append({"type": "trust_signal", "asset": metric_name, "level": trust["trust_level"]})

            # Step 4: Execute SQL if this is a data question
            sql_result = None
            if definition and self._needs_sql(question):
                sql_query = self._build_sql(question, definition)
                if sql_query:
                    sql_result = _tools.execute_sql(sql_query)
                    tool_calls_log.append({"tool": "execute_sql", "args": {"query": sql_query}, "result_preview": json.dumps(sql_result, default=str)[:500]})

            # Step 5: Use LLM to format the final answer
            answer = self._format_answer(question, search_result, definition, trust, sql_result)

            elapsed = time.time() - start_time
            return {
                "agent": self.name,
                "question": question,
                "answer": answer,
                "tool_calls": tool_calls_log,
                "sources": sources,
                "latency_seconds": round(elapsed, 2),
                "num_tool_calls": len(tool_calls_log),
                "success": True,
                "error": None,
            }

        except Exception as e:
            elapsed = time.time() - start_time
            logger.error(f"[ContextHub] Error: {e}")
            return {
                "agent": self.name,
                "question": question,
                "answer": f"Error: {str(e)}",
                "tool_calls": tool_calls_log,
                "sources": sources,
                "latency_seconds": round(elapsed, 2),
                "num_tool_calls": len(tool_calls_log),
                "success": False,
                "error": str(e),
            }

    def _extract_topic(self, question: str) -> str:
        """Extract the search topic from the question."""
        # Simple keyword extraction
        keywords = ["revenue", "customer", "order", "product", "payment", "active", "refund", "aov", "mrr"]
        q_lower = question.lower()
        for kw in keywords:
            if kw in q_lower:
                return kw
        # Fallback: use first few meaningful words
        return question.split("?")[0].strip()[:50]

    def _pick_best_metric(self, search_result: dict) -> str | None:
        """Pick the best (certified) metric from search results."""
        results = search_result.get("results", [])
        # Prefer metrics over tables
        metrics = [r for r in results if r.get("type") == "metric"]
        if not metrics:
            return None

        # Prefer non-deprecated
        for m in metrics:
            desc = m.get("description", "").lower()
            if "deprecated" not in desc and "draft" not in desc:
                return m["name"]

        # Return first metric if all are deprecated
        return metrics[0]["name"]

    def _needs_sql(self, question: str) -> bool:
        """Determine if the question needs a SQL query (asks for data/numbers)."""
        data_words = ["what was", "how many", "how much", "calculate", "total", "count", "average", "sum", "revenue in", "customers in", "orders in"]
        q_lower = question.lower()
        return any(w in q_lower for w in data_words)

    def _build_sql(self, question: str, definition: dict) -> str | None:
        """Build SQL based on the metric definition and question context."""
        if not definition:
            return None

        source_table = definition.get("source_table", "")
        source_column = definition.get("source_column", "")
        filter_condition = definition.get("filter_condition", "")
        calculation = definition.get("calculation", "")

        if not source_table or not source_column:
            return None

        # Determine date filter from question
        date_filter = self._extract_date_filter(question)

        # Build the query based on metric type
        metric_name = definition.get("metric_name", "")

        if "count" in metric_name.lower() or "rate" in metric_name.lower():
            # Count-based metric
            if filter_condition:
                sql = f"SELECT COUNT(DISTINCT {source_column}) FROM {source_table} WHERE {filter_condition}"
            else:
                sql = f"SELECT COUNT(*) FROM {source_table}"
        elif "average" in metric_name.lower() or "avg" in calculation.lower():
            sql = f"SELECT AVG({source_column}) FROM {source_table}"
            if filter_condition:
                sql += f" WHERE {filter_condition}"
        else:
            # Sum-based metric (revenue, etc.)
            sql = f"SELECT SUM({source_column}) FROM {source_table}"
            if filter_condition:
                sql += f" WHERE {filter_condition}"

        # Add date filter
        if date_filter:
            if "WHERE" in sql:
                sql += f" AND {date_filter}"
            else:
                sql += f" WHERE {date_filter}"

        return sql

    def _extract_date_filter(self, question: str) -> str:
        """Extract date filter from question text."""
        import re
        q_lower = question.lower()

        # Match "July 2026", "jan 2025", etc.
        months = {"january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
                  "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
                  "jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6, "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12}

        for month_name, month_num in months.items():
            pattern = rf"{month_name}\s+(\d{{4}})"
            match = re.search(pattern, q_lower)
            if match:
                year = match.group(1)
                return f"order_date >= '{year}-{month_num:02d}-01' AND order_date < '{year}-{month_num + 1 if month_num < 12 else 1:02d}-01'"

        # Match just year
        year_match = re.search(r"in (\d{4})", q_lower)
        if year_match:
            year = year_match.group(1)
            return f"order_date >= '{year}-01-01' AND order_date < '{int(year)+1}-01-01'"

        return ""

    def _format_answer(self, question: str, search_result: dict, definition: dict | None, trust: dict | None, sql_result: dict | None) -> str:
        """Use LLM to format a clean final answer from all collected context."""
        # Build context for the LLM
        context_parts = []

        if definition:
            context_parts.append(f"Metric: {definition.get('metric_name')} ({definition.get('status', 'unknown')})")
            context_parts.append(f"Definition: {definition.get('definition', '')}")
            context_parts.append(f"Source: {definition.get('source_table')}.{definition.get('source_column')}")

        if trust:
            context_parts.append(f"Trust Level: {trust.get('trust_level', 'unknown')}")
            context_parts.append(f"Certified by: {trust.get('certified_by', 'N/A')}")

        if sql_result and "rows" in sql_result:
            context_parts.append(f"SQL Result: {json.dumps(sql_result['rows'], default=str)}")
            context_parts.append(f"Query: {sql_result.get('query', '')}")

        if not context_parts:
            # No metric found - list what was found
            assets = search_result.get("results", [])
            if assets:
                context_parts.append("Available assets found:")
                for a in assets[:5]:
                    status = "DEPRECATED" if "deprecated" in a.get("description", "").lower() else "certified" if "certified" in a.get("description", "").lower() else ""
                    context_parts.append(f"  - {a['name']} ({a['type']}) {status}: {a.get('description', '')[:100]}")

        context_str = "\n".join(context_parts)

        # Use LLM to produce a clean answer
        llm = get_llm(temperature=0.0)
        prompt = f"""Based on this context, provide a SHORT and clear answer to the user's question.

Question: {question}

Context:
{context_str}

Rules:
- If SQL result has a number, state it clearly (format large numbers with commas)
- Mention the metric used and its certification status
- If a metric is deprecated, warn the user
- Keep answer to 3-5 sentences maximum
- Do NOT use tool calls or JSON in your response"""

        try:
            response = llm.invoke([
                SystemMessage(content="You are a concise data analyst. Give short, factual answers with numbers."),
                HumanMessage(content=prompt),
            ])
            return response.content if isinstance(response.content, str) else str(response.content)
        except Exception as e:
            # Fallback: format without LLM
            if sql_result and "rows" in sql_result and sql_result["rows"]:
                value = list(sql_result["rows"][0].values())[0]
                metric = definition.get("metric_name", "unknown") if definition else "unknown"
                status = trust.get("trust_level", "unknown") if trust else "unknown"
                return f"Result: {value:,.2f}\n\nMetric: {metric} (status: {status})\nSource: {definition.get('source_table', '')}.{definition.get('source_column', '')}"
            return f"Context found but could not generate answer: {context_str[:200]}"
