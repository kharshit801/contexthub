"""Tests for MCP tools.

Verifies tool implementations, SQL validation/safety, and tool responses.

Run with: pytest tests/test_mcp.py -v
Note: Requires PostgreSQL running with seeded data.
"""

import pytest

from app.mcp.tools import ContextTools, validate_sql


class TestSQLValidation:
    """Test SQL safety validation."""

    def test_select_allowed(self):
        """Simple SELECT queries should pass."""
        is_safe, msg = validate_sql("SELECT * FROM business.orders")
        assert is_safe is True

    def test_select_with_where_allowed(self):
        """SELECT with WHERE clause should pass."""
        is_safe, msg = validate_sql(
            "SELECT SUM(net_amount) FROM business.orders WHERE status = 'completed'"
        )
        assert is_safe is True

    def test_with_cte_allowed(self):
        """WITH (CTE) queries should pass."""
        is_safe, msg = validate_sql(
            "WITH monthly AS (SELECT * FROM business.orders) SELECT * FROM monthly"
        )
        assert is_safe is True

    def test_drop_rejected(self):
        """DROP statements should be rejected."""
        is_safe, msg = validate_sql("DROP TABLE business.orders")
        assert is_safe is False
        assert "forbidden" in msg.lower() or "SELECT" in msg

    def test_delete_rejected(self):
        """DELETE statements should be rejected."""
        is_safe, msg = validate_sql("DELETE FROM business.orders")
        assert is_safe is False

    def test_update_rejected(self):
        """UPDATE statements should be rejected."""
        is_safe, msg = validate_sql("UPDATE business.orders SET status = 'cancelled'")
        assert is_safe is False

    def test_insert_rejected(self):
        """INSERT statements should be rejected."""
        is_safe, msg = validate_sql("INSERT INTO business.orders VALUES (1, 2, 3)")
        assert is_safe is False

    def test_truncate_rejected(self):
        """TRUNCATE statements should be rejected."""
        is_safe, msg = validate_sql("TRUNCATE business.orders")
        assert is_safe is False

    def test_alter_rejected(self):
        """ALTER statements should be rejected."""
        is_safe, msg = validate_sql("ALTER TABLE business.orders ADD COLUMN x int")
        assert is_safe is False

    def test_select_with_drop_in_string_rejected(self):
        """SQL injection attempts should be caught."""
        # This is a conservative approach - even DROP in a comment is rejected
        is_safe, msg = validate_sql("SELECT * FROM business.orders -- DROP TABLE orders")
        assert is_safe is False


class TestContextTools:
    """Test the ContextTools class methods."""

    @pytest.fixture
    def tools(self):
        return ContextTools()

    def test_search_assets_returns_results(self, tools):
        """search_assets should return matching results."""
        result = tools.search_assets("revenue")
        assert "results" in result
        assert result["count"] >= 2
        assert "elapsed_ms" in result

    def test_get_definition_returns_metric(self, tools):
        """get_definition should return metric details."""
        result = tools.get_definition("net_revenue")
        assert "metric_name" in result
        assert result["metric_name"] == "net_revenue"
        assert result["status"] == "certified"

    def test_get_definition_not_found(self, tools):
        """get_definition should return error for unknown metric."""
        result = tools.get_definition("nonexistent")
        assert "error" in result

    def test_get_trust_signal_certified(self, tools):
        """get_trust_signal should return trust level."""
        result = tools.get_trust_signal("net_revenue")
        assert "trust_level" in result
        assert result["trust_level"] == "certified"

    def test_get_schema_returns_columns(self, tools):
        """get_schema should return table columns."""
        result = tools.get_schema("orders")
        assert "columns" in result
        assert result["column_count"] > 0

    def test_get_lineage_returns_relationships(self, tools):
        """get_lineage should return relationships."""
        result = tools.get_lineage("orders")
        assert "relationships" in result
        assert result["count"] > 0

    def test_execute_sql_valid_query(self, tools):
        """execute_sql should run valid SELECT queries."""
        result = tools.execute_sql("SELECT COUNT(*) as cnt FROM business.customers")
        assert "rows" in result
        assert result["row_count"] == 1
        assert result["rows"][0]["cnt"] > 0

    def test_execute_sql_rejects_drop(self, tools):
        """execute_sql should reject dangerous queries."""
        result = tools.execute_sql("DROP TABLE business.customers")
        assert "error" in result

    def test_execute_sql_adds_limit(self, tools):
        """execute_sql should add LIMIT if not present."""
        result = tools.execute_sql("SELECT * FROM business.customers")
        assert "LIMIT" in result.get("query", "")

    def test_list_metrics(self, tools):
        """list_metrics should return all metrics."""
        result = tools.list_metrics()
        assert "metrics" in result
        assert result["count"] >= 5
