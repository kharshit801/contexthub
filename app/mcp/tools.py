"""MCP tool implementations for ContextHub.

These tools provide the AI agent with access to:
1. Business context (definitions, metadata, trust signals, lineage)
2. Schema information (enriched column descriptions)
3. Read-only SQL execution against the business database

Security: Only SELECT queries are allowed. All destructive SQL is rejected.
"""

import re
import time
from typing import Any

from sqlalchemy import text

from app.context.service import ContextService
from app.db.connection import get_engine


# SQL safety patterns
DANGEROUS_SQL_PATTERNS = [
    r"\bDROP\b",
    r"\bDELETE\b",
    r"\bUPDATE\b",
    r"\bINSERT\b",
    r"\bALTER\b",
    r"\bTRUNCATE\b",
    r"\bCREATE\b",
    r"\bGRANT\b",
    r"\bREVOKE\b",
    r"\bEXEC\b",
    r"\bEXECUTE\b",
    r"--",
    r";.*;\s*$",  # Multiple statements
]


def validate_sql(query: str) -> tuple[bool, str]:
    """Validate that SQL is a safe read-only query.

    Returns:
        (is_safe, error_message)
    """
    normalized = query.strip().upper()

    # Must start with SELECT or WITH (CTEs)
    if not (normalized.startswith("SELECT") or normalized.startswith("WITH")):
        return False, "Only SELECT queries are allowed. Query must start with SELECT or WITH."

    # Check for dangerous patterns
    for pattern in DANGEROUS_SQL_PATTERNS:
        if re.search(pattern, normalized, re.IGNORECASE):
            return False, f"Query contains forbidden pattern: {pattern}. Only read-only SELECT queries are allowed."

    return True, ""


class ContextTools:
    """Tool implementations that the MCP server and LangGraph agent use."""

    def __init__(self):
        self._context_service: ContextService | None = None

    @property
    def context_service(self) -> ContextService:
        if self._context_service is None:
            self._context_service = ContextService()
        return self._context_service

    def search_assets(self, query: str) -> dict[str, Any]:
        """Search for data assets (tables, columns, metrics) by name or description.

        Use this tool FIRST to discover what assets are relevant to the user's question.

        Args:
            query: Search term (e.g., "revenue", "customer", "orders")

        Returns:
            List of matching assets with their metadata.
        """
        start = time.time()
        results = self.context_service.search_assets(query)
        elapsed = time.time() - start

        return {
            "results": results,
            "count": len(results),
            "query": query,
            "elapsed_ms": round(elapsed * 1000, 2),
        }

    def get_definition(self, metric_name: str) -> dict[str, Any]:
        """Get the certified business definition for a metric.

        Use this to understand exactly what a metric means, how it's calculated,
        which column/table to use, and what filters to apply.

        Args:
            metric_name: Name of the metric (e.g., "net_revenue", "active_customer_count")

        Returns:
            Business definition including calculation, source, status, and notes.
        """
        start = time.time()
        result = self.context_service.get_definition(metric_name)
        elapsed = time.time() - start

        if result is None:
            return {
                "error": f"No definition found for '{metric_name}'",
                "suggestion": "Try search_assets() to find available metrics.",
                "elapsed_ms": round(elapsed * 1000, 2),
            }

        result["elapsed_ms"] = round(elapsed * 1000, 2)
        return result

    def get_trust_signal(self, asset_name: str) -> dict[str, Any]:
        """Check the trust/certification status of a data asset or metric.

        ALWAYS check trust signals before using a metric. Prefer certified metrics
        over deprecated or experimental ones.

        Args:
            asset_name: Name of the asset or metric to check

        Returns:
            Trust level (certified/deprecated/experimental/stale), reason, and validator.
        """
        start = time.time()
        result = self.context_service.get_trust_signal(asset_name)
        elapsed = time.time() - start

        if result is None:
            return {
                "error": f"No trust signal found for '{asset_name}'",
                "suggestion": "Asset may not have been reviewed. Exercise caution.",
                "elapsed_ms": round(elapsed * 1000, 2),
            }

        result["elapsed_ms"] = round(elapsed * 1000, 2)
        return result

    def get_schema(self, table_name: str) -> dict[str, Any]:
        """Get detailed schema information for a table, including business context for each column.

        Use this to understand what columns are available and their business meaning
        BEFORE writing SQL.

        Args:
            table_name: Name of the table (e.g., "orders", "customers")

        Returns:
            List of columns with types, descriptions, and business context.
        """
        start = time.time()
        results = self.context_service.get_schema(table_name)
        elapsed = time.time() - start

        if not results:
            return {
                "error": f"No schema information found for table '{table_name}'",
                "suggestion": "Available tables: customers, orders, products, payments",
                "elapsed_ms": round(elapsed * 1000, 2),
            }

        return {
            "table": table_name,
            "columns": results,
            "column_count": len(results),
            "elapsed_ms": round(elapsed * 1000, 2),
        }

    def get_lineage(self, asset_name: str) -> dict[str, Any]:
        """Get data lineage showing how assets relate to each other.

        Use this to understand table relationships and metric dependencies.

        Args:
            asset_name: Name of the asset (table or metric)

        Returns:
            Upstream and downstream relationships.
        """
        start = time.time()
        results = self.context_service.get_lineage(asset_name)
        elapsed = time.time() - start

        return {
            "asset": asset_name,
            "relationships": results,
            "count": len(results),
            "elapsed_ms": round(elapsed * 1000, 2),
        }

    def execute_sql(self, query: str) -> dict[str, Any]:
        """Execute a read-only SQL query against the business database.

        IMPORTANT:
        - Only SELECT queries are allowed
        - Use schema prefix: business.orders, business.customers, etc.
        - Apply appropriate WHERE clauses based on business definitions
        - Limit results to prevent overwhelming output

        Args:
            query: SQL SELECT query to execute

        Returns:
            Query results with column names and row data.
        """
        start = time.time()

        # Validate SQL safety
        is_safe, error_msg = validate_sql(query)
        if not is_safe:
            return {
                "error": error_msg,
                "query": query,
                "elapsed_ms": round((time.time() - start) * 1000, 2),
            }

        # Add LIMIT if not present to prevent huge result sets
        normalized = query.strip().upper()
        if "LIMIT" not in normalized:
            query = query.rstrip(";") + " LIMIT 100"

        try:
            engine = get_engine(readonly=True)
            with engine.connect() as conn:
                result = conn.execute(text(query))
                columns = list(result.keys())
                rows = [dict(zip(columns, row)) for row in result.fetchall()]
                elapsed = time.time() - start

                return {
                    "columns": columns,
                    "rows": rows,
                    "row_count": len(rows),
                    "query": query,
                    "elapsed_ms": round(elapsed * 1000, 2),
                }

        except Exception as e:
            elapsed = time.time() - start
            return {
                "error": f"SQL execution error: {str(e)}",
                "query": query,
                "elapsed_ms": round(elapsed * 1000, 2),
            }

    def list_metrics(self) -> dict[str, Any]:
        """List all available business metric definitions with their status.

        Use this to see what metrics are available and their certification status.

        Returns:
            All defined business metrics with status and source info.
        """
        start = time.time()
        results = self.context_service.get_all_definitions()
        elapsed = time.time() - start

        return {
            "metrics": results,
            "count": len(results),
            "elapsed_ms": round(elapsed * 1000, 2),
        }
