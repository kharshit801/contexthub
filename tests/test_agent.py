"""Tests for the AI agents.

These tests verify agent construction and interface.
Full integration tests require an LLM API key.

Run with: pytest tests/test_agent.py -v
"""

import pytest

from app.agent.prompts import BASELINE_SYSTEM_PROMPT, CONTEXTHUB_SYSTEM_PROMPT


class TestPrompts:
    """Test that prompts are well-structured."""

    def test_baseline_prompt_has_schema(self):
        """Baseline prompt should include table schemas."""
        assert "business.customers" in BASELINE_SYSTEM_PROMPT
        assert "business.orders" in BASELINE_SYSTEM_PROMPT
        assert "business.products" in BASELINE_SYSTEM_PROMPT
        assert "business.payments" in BASELINE_SYSTEM_PROMPT

    def test_baseline_prompt_has_no_context_instructions(self):
        """Baseline prompt should NOT mention business definitions or trust signals."""
        assert "certified" not in BASELINE_SYSTEM_PROMPT.lower()
        assert "trust signal" not in BASELINE_SYSTEM_PROMPT.lower()
        assert "business definition" not in BASELINE_SYSTEM_PROMPT.lower()

    def test_contexthub_prompt_instructs_context_usage(self):
        """ContextHub prompt should instruct agent to use context tools first."""
        assert "search_assets" in CONTEXTHUB_SYSTEM_PROMPT
        assert "get_definition" in CONTEXTHUB_SYSTEM_PROMPT
        assert "get_trust_signal" in CONTEXTHUB_SYSTEM_PROMPT
        assert "certified" in CONTEXTHUB_SYSTEM_PROMPT.lower()
        assert "deprecated" in CONTEXTHUB_SYSTEM_PROMPT.lower()

    def test_contexthub_prompt_enforces_workflow(self):
        """ContextHub prompt should enforce context-first workflow."""
        # Should mention checking definitions BEFORE writing SQL
        assert "BEFORE" in CONTEXTHUB_SYSTEM_PROMPT or "before" in CONTEXTHUB_SYSTEM_PROMPT
        assert "MUST" in CONTEXTHUB_SYSTEM_PROMPT

    def test_both_prompts_restrict_to_select(self):
        """Both prompts should mention read-only/SELECT restriction."""
        assert "SELECT" in BASELINE_SYSTEM_PROMPT or "read-only" in BASELINE_SYSTEM_PROMPT.lower()
        assert "SELECT" in CONTEXTHUB_SYSTEM_PROMPT or "read-only" in CONTEXTHUB_SYSTEM_PROMPT.lower()


class TestAgentInterface:
    """Test that agents have the correct interface."""

    def test_baseline_agent_has_ask_method(self):
        """BaselineAgent should have an ask() method."""
        from app.agent.baseline import BaselineAgent
        agent = BaselineAgent()
        assert hasattr(agent, "ask")
        assert agent.name == "baseline"

    def test_contexthub_agent_has_ask_method(self):
        """ContextHubAgent should have an ask() method."""
        from app.agent.contexthub import ContextHubAgent
        agent = ContextHubAgent()
        assert hasattr(agent, "ask")
        assert agent.name == "contexthub"

    def test_baseline_has_limited_tools(self):
        """Baseline agent should only have execute_sql tool."""
        from app.agent.baseline import BASELINE_TOOLS
        tool_names = [t.name for t in BASELINE_TOOLS]
        assert "execute_sql" in tool_names
        assert len(tool_names) == 1  # Only SQL execution

    def test_contexthub_has_all_tools(self):
        """ContextHub agent should have all 7 tools."""
        from app.agent.contexthub import CONTEXTHUB_TOOLS
        tool_names = [t.name for t in CONTEXTHUB_TOOLS]
        assert "search_assets" in tool_names
        assert "get_definition" in tool_names
        assert "get_trust_signal" in tool_names
        assert "get_schema" in tool_names
        assert "get_lineage" in tool_names
        assert "execute_sql" in tool_names
        assert "list_metrics" in tool_names
        assert len(tool_names) == 7


class TestEvaluationScoring:
    """Test evaluation scoring functions."""

    def test_metric_selection_scoring(self):
        """Test that metric selection scoring works correctly."""
        from evaluation.runner import score_metric_selection

        # Correct metric mentioned in answer
        response = {"answer": "Using net_revenue metric which is certified.", "tool_calls": []}
        expected = {"expected_metric": "net_revenue"}
        assert score_metric_selection(response, expected) == 1.0

        # Wrong metric
        response = {"answer": "I used gross_revenue for this calculation.", "tool_calls": []}
        expected = {"expected_metric": "net_revenue"}
        assert score_metric_selection(response, expected) == 0.0

    def test_sql_correctness_scoring(self):
        """Test SQL correctness scoring."""
        from evaluation.runner import score_sql_correctness

        # Correct filter applied
        response = {
            "answer": "",
            "tool_calls": [
                {"tool": "execute_sql", "args": {"query": "SELECT SUM(net_amount) FROM business.orders WHERE status = 'completed'"}, "result_preview": '{"rows": []}'}
            ],
        }
        expected = {"expected_filter": "status = 'completed'"}
        score = score_sql_correctness(response, expected)
        assert score == 1.0

    def test_groundedness_scoring(self):
        """Test groundedness scoring."""
        from evaluation.runner import score_groundedness

        # Well-grounded answer
        response = {
            "answer": "Net revenue in July was ₹48,21,320. I used the certified net_revenue metric from the orders table.",
            "tool_calls": [{"tool": "get_definition", "args": {}}],
        }
        score = score_groundedness(response, {})
        assert score > 0.5

        # Ungrounded answer
        response = {"answer": "I think maybe it's around some amount.", "tool_calls": []}
        score = score_groundedness(response, {})
        assert score < 0.5
