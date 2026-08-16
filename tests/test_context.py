"""Tests for the context layer service.

These tests verify that the context layer correctly stores and retrieves
business definitions, trust signals, schema info, and lineage.

Run with: pytest tests/test_context.py -v
Note: Requires PostgreSQL running with seeded data.
"""

import pytest

from app.context.service import ContextService


@pytest.fixture
def context_service():
    """Create a context service instance."""
    service = ContextService()
    yield service
    service.close()


class TestSearchAssets:
    """Test asset search functionality."""

    def test_search_revenue_returns_results(self, context_service):
        """Searching for 'revenue' should find net_revenue and gross_revenue."""
        results = context_service.search_assets("revenue")
        assert len(results) >= 2
        names = [r["name"] for r in results]
        assert "net_revenue" in names
        assert "gross_revenue" in names

    def test_search_customer_returns_results(self, context_service):
        """Searching for 'customer' should find customer-related assets."""
        results = context_service.search_assets("customer")
        assert len(results) >= 1
        names = [r["name"] for r in results]
        assert "customers" in names

    def test_search_nonexistent_returns_empty(self, context_service):
        """Searching for something that doesn't exist returns empty list."""
        results = context_service.search_assets("xyznonexistent")
        assert results == []


class TestGetDefinition:
    """Test business definition retrieval."""

    def test_get_net_revenue_definition(self, context_service):
        """Should return the certified net_revenue definition."""
        defn = context_service.get_definition("net_revenue")
        assert defn is not None
        assert defn["metric_name"] == "net_revenue"
        assert defn["status"] == "certified"
        assert defn["source_column"] == "net_amount"
        assert defn["source_table"] == "business.orders"
        assert "completed" in defn["filter_condition"].lower()

    def test_get_gross_revenue_is_deprecated(self, context_service):
        """Gross revenue should be marked as deprecated."""
        defn = context_service.get_definition("gross_revenue")
        assert defn is not None
        assert defn["status"] == "deprecated"

    def test_get_active_customer_count(self, context_service):
        """Active customer count should require both is_active and recency."""
        defn = context_service.get_definition("active_customer_count")
        assert defn is not None
        assert defn["status"] == "certified"
        assert "is_active" in defn["filter_condition"]
        assert "90 days" in defn["filter_condition"] or "90" in defn["filter_condition"]

    def test_get_nonexistent_definition(self, context_service):
        """Should return None for undefined metrics."""
        defn = context_service.get_definition("nonexistent_metric")
        assert defn is None

    def test_fuzzy_search_revenue(self, context_service):
        """Should find definition with fuzzy matching."""
        defn = context_service.get_definition("revenue")
        assert defn is not None
        # Should find one of the revenue metrics


class TestGetTrustSignal:
    """Test trust signal retrieval."""

    def test_net_revenue_is_certified(self, context_service):
        """Net revenue should be certified."""
        signal = context_service.get_trust_signal("net_revenue")
        assert signal is not None
        assert signal["trust_level"] == "certified"
        assert signal["certified_by"] is not None

    def test_gross_revenue_is_deprecated(self, context_service):
        """Gross revenue should be deprecated."""
        signal = context_service.get_trust_signal("gross_revenue")
        assert signal is not None
        assert signal["trust_level"] == "deprecated"

    def test_mrr_is_stale(self, context_service):
        """MRR should be stale."""
        signal = context_service.get_trust_signal("monthly_recurring_revenue")
        assert signal is not None
        assert signal["trust_level"] == "stale"


class TestGetSchema:
    """Test schema information retrieval."""

    def test_get_orders_schema(self, context_service):
        """Should return all columns for orders table."""
        schema = context_service.get_schema("orders")
        assert len(schema) > 0
        columns = [s["column"] for s in schema]
        assert "net_amount" in columns
        assert "total_amount" in columns
        assert "status" in columns

    def test_schema_has_business_context(self, context_service):
        """Schema entries should have business context descriptions."""
        schema = context_service.get_schema("orders")
        net_amount_entry = next((s for s in schema if s["column"] == "net_amount"), None)
        assert net_amount_entry is not None
        assert net_amount_entry["business_context"] is not None
        assert "certified" in net_amount_entry["business_context"].lower() or "revenue" in net_amount_entry["business_context"].lower()

    def test_nonexistent_table_returns_empty(self, context_service):
        """Should return empty for non-existent table."""
        schema = context_service.get_schema("nonexistent_table")
        assert schema == []


class TestGetLineage:
    """Test lineage retrieval."""

    def test_orders_lineage(self, context_service):
        """Orders should have relationships to customers, products, payments."""
        lineage = context_service.get_lineage("orders")
        assert len(lineage) > 0
        # Should show relationships
        relationship_types = [l["relationship_type"] for l in lineage]
        assert "foreign_key" in relationship_types or "metric_source" in relationship_types

    def test_net_revenue_lineage(self, context_service):
        """Net revenue should trace back to orders.net_amount."""
        lineage = context_service.get_lineage("net_revenue")
        assert len(lineage) > 0
        sources = [l["source"] for l in lineage]
        assert any("net_amount" in s for s in sources)
