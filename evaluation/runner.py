"""Evaluation runner for ContextHub.

Runs both baseline and ContextHub agents on the benchmark dataset,
scores them on 5 dimensions, and produces a comparison report.

Usage:
    python -m evaluation.runner [--questions N] [--agent baseline|contexthub|both]
"""

import json
import logging
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.agent.baseline import BaselineAgent
from app.agent.contexthub import ContextHubAgent

logger = logging.getLogger(__name__)

EVAL_DIR = Path(__file__).parent
DATASET_PATH = EVAL_DIR / "dataset.json"
RESULTS_DIR = EVAL_DIR / "results"


def load_dataset(limit: int | None = None) -> list[dict]:
    """Load the evaluation dataset."""
    with open(DATASET_PATH) as f:
        data = json.load(f)
    questions = data["questions"]
    if limit:
        questions = questions[:limit]
    return questions


def score_metric_selection(response: dict, expected: dict) -> float:
    """Score whether the agent selected the correct metric.

    Returns 1.0 for correct, 0.5 for partial, 0.0 for incorrect.
    """
    expected_metric = expected.get("expected_metric")
    if not expected_metric:
        return 1.0  # No metric expected, skip

    answer = response.get("answer", "").lower()
    tool_calls = response.get("tool_calls", [])

    # Check if the expected metric appears in the answer
    metric_normalized = expected_metric.lower().replace("_", " ")
    metric_with_underscore = expected_metric.lower()

    if metric_with_underscore in answer or metric_normalized in answer:
        return 1.0

    # Check if the metric was looked up via tools
    for call in tool_calls:
        if call.get("tool") == "get_definition":
            args = call.get("args", {})
            if expected_metric.lower() in str(args).lower():
                return 0.75  # Looked it up but may not have used it

    # Check for related column reference
    expected_col = expected.get("expected_source_column", "")
    if expected_col and expected_col.lower() in answer:
        return 0.5  # Used correct column but didn't name the metric

    return 0.0


def score_source_selection(response: dict, expected: dict) -> float:
    """Score whether the agent chose the correct source table/column.

    Returns 1.0 for correct table+column, 0.5 for correct table only.
    """
    answer = response.get("answer", "").lower()
    tool_calls = response.get("tool_calls", [])

    expected_table = expected.get("expected_source_table", "")
    expected_column = expected.get("expected_source_column", "")

    if not expected_table:
        return 1.0  # No source expected

    # Check SQL in tool calls
    sql_queries = []
    for call in tool_calls:
        if call.get("tool") == "execute_sql":
            sql_queries.append(str(call.get("args", {}).get("query", "")).lower())

    all_text = answer + " " + " ".join(sql_queries)

    table_name = expected_table.replace("business.", "")
    has_table = table_name in all_text or expected_table.lower() in all_text
    has_column = expected_column.lower() in all_text if expected_column else True

    if has_table and has_column:
        return 1.0
    elif has_table:
        return 0.5
    return 0.0


def score_sql_correctness(response: dict, expected: dict) -> float:
    """Score SQL correctness based on expected filters and structure.

    Returns 1.0 if correct filters applied, 0.5 for partial, 0.0 for wrong.
    """
    expected_filter = expected.get("expected_filter")
    tool_calls = response.get("tool_calls", [])

    # If no filter expected, check if SQL was executed at all
    if not expected_filter:
        for call in tool_calls:
            if call.get("tool") == "execute_sql":
                # Check if it returned results (no error)
                result_preview = call.get("result_preview", "")
                if "error" not in result_preview.lower():
                    return 1.0
        # No SQL needed or no SQL executed
        return 1.0 if expected.get("category") == "context_awareness" else 0.5

    # Check if the filter condition appears in executed SQL
    sql_queries = []
    for call in tool_calls:
        if call.get("tool") == "execute_sql":
            query = str(call.get("args", {}).get("query", "")).lower()
            sql_queries.append(query)

    if not sql_queries:
        return 0.0

    # Parse expected filter parts
    filter_parts = re.split(r'\s+AND\s+', expected_filter, flags=re.IGNORECASE)
    matched_parts = 0

    for part in filter_parts:
        part_lower = part.lower().strip()
        for query in sql_queries:
            if part_lower in query or _fuzzy_filter_match(part_lower, query):
                matched_parts += 1
                break

    if len(filter_parts) == 0:
        return 1.0

    return matched_parts / len(filter_parts)


def _fuzzy_filter_match(expected_part: str, query: str) -> bool:
    """Fuzzy matching for filter conditions (handles slight variations)."""
    # Handle common variations
    variations = {
        "status = 'completed'": ["status='completed'", "status = 'completed'", "\"status\" = 'completed'"],
        "is_active = true": ["is_active = true", "is_active=true", "is_active = 't'"],
    }

    for canonical, alts in variations.items():
        if expected_part == canonical.lower():
            for alt in alts:
                if alt.lower() in query:
                    return True
    return False


def score_groundedness(response: dict, expected: dict) -> float:
    """Score whether the answer is grounded in actual data/context.

    Checks if the agent references specific sources, metrics, or data values.
    """
    answer = response.get("answer", "")
    tool_calls = response.get("tool_calls", [])

    if not answer:
        return 0.0

    score = 0.0
    checks = 0

    # Check 1: Does the answer reference specific data?
    checks += 1
    has_specific_data = bool(re.search(r'\d+[,.]?\d*', answer))  # Contains numbers
    if has_specific_data:
        score += 1.0

    # Check 2: Does the answer mention the source?
    checks += 1
    source_indicators = ["table", "column", "orders", "customers", "payments", "products",
                         "net_amount", "total_amount", "metric", "definition"]
    mentions_source = any(ind in answer.lower() for ind in source_indicators)
    if mentions_source:
        score += 1.0

    # Check 3: Does the answer reference certification/trust status?
    checks += 1
    trust_indicators = ["certified", "deprecated", "experimental", "approved", "trusted"]
    mentions_trust = any(ind in answer.lower() for ind in trust_indicators)
    if mentions_trust:
        score += 1.0

    # Check 4: Did the agent actually use tools to get data?
    checks += 1
    if tool_calls:
        score += 1.0

    return score / checks if checks > 0 else 0.0


def score_tool_success(response: dict, expected: dict) -> float:
    """Score whether tools were called successfully (no errors).

    Returns ratio of successful tool calls to total tool calls.
    """
    tool_calls = response.get("tool_calls", [])

    if not tool_calls:
        # For context_awareness questions, having no tool calls for baseline is expected
        if expected.get("category") in ("context_awareness", "trust_signal", "lineage"):
            return 0.0  # Should have used tools
        return 0.5  # Neutral for simple queries

    successful = 0
    for call in tool_calls:
        result = call.get("result_preview", "")
        if "error" not in result.lower():
            successful += 1

    return successful / len(tool_calls)


def evaluate_response(response: dict, expected: dict) -> dict[str, float]:
    """Evaluate a single agent response against expected results."""
    return {
        "metric_selection": score_metric_selection(response, expected),
        "source_selection": score_source_selection(response, expected),
        "sql_correctness": score_sql_correctness(response, expected),
        "groundedness": score_groundedness(response, expected),
        "tool_success": score_tool_success(response, expected),
    }


def run_evaluation(
    agent_type: str = "both",
    limit: int | None = None,
    verbose: bool = True,
) -> dict[str, Any]:
    """Run the full evaluation pipeline.

    Args:
        agent_type: "baseline", "contexthub", or "both"
        limit: Maximum number of questions to evaluate
        verbose: Print progress during evaluation

    Returns:
        Complete evaluation results including per-question scores and averages.
    """
    questions = load_dataset(limit)

    if verbose:
        print(f"\n{'='*60}")
        print(f"  ContextHub Evaluation - {len(questions)} questions")
        print(f"{'='*60}\n")

    results = {
        "timestamp": datetime.now().isoformat(),
        "num_questions": len(questions),
        "agents": {},
    }

    agents_to_run = []
    if agent_type in ("baseline", "both"):
        agents_to_run.append(("baseline", BaselineAgent()))
    if agent_type in ("contexthub", "both"):
        agents_to_run.append(("contexthub", ContextHubAgent()))

    for agent_name, agent in agents_to_run:
        if verbose:
            print(f"\n--- Running {agent_name.upper()} agent ---\n")

        agent_results = {
            "responses": [],
            "scores": [],
            "totals": {
                "metric_selection": 0.0,
                "source_selection": 0.0,
                "sql_correctness": 0.0,
                "groundedness": 0.0,
                "tool_success": 0.0,
            },
            "avg_latency": 0.0,
            "total_tool_calls": 0,
            "errors": 0,
        }

        total_latency = 0.0

        for i, q in enumerate(questions):
            if verbose:
                print(f"  [{i+1}/{len(questions)}] {q['question'][:60]}...", end=" ")

            try:
                response = agent.ask(q["question"])
                scores = evaluate_response(response, q)

                agent_results["responses"].append({
                    "question_id": q["id"],
                    "question": q["question"],
                    "answer": response.get("answer", "")[:500],
                    "tool_calls": response.get("tool_calls", []),
                    "latency": response.get("latency_seconds", 0),
                    "success": response.get("success", False),
                })
                agent_results["scores"].append({
                    "question_id": q["id"],
                    **scores,
                })

                for metric, value in scores.items():
                    agent_results["totals"][metric] += value

                total_latency += response.get("latency_seconds", 0)
                agent_results["total_tool_calls"] += len(response.get("tool_calls", []))

                if not response.get("success"):
                    agent_results["errors"] += 1

                if verbose:
                    avg_score = sum(scores.values()) / len(scores)
                    status = "✓" if avg_score > 0.6 else "△" if avg_score > 0.3 else "✗"
                    print(f"{status} (avg: {avg_score:.2f}, latency: {response.get('latency_seconds', 0):.1f}s)")

            except Exception as e:
                logger.error(f"Error evaluating question {q['id']}: {e}")
                agent_results["errors"] += 1
                if verbose:
                    print(f"✗ ERROR: {e}")

            # Rate limiting for free tier APIs
            time.sleep(2)

        # Calculate averages
        n = len(questions)
        if n > 0:
            for metric in agent_results["totals"]:
                agent_results["totals"][metric] = round(agent_results["totals"][metric] / n, 4)
            agent_results["avg_latency"] = round(total_latency / n, 2)

        results["agents"][agent_name] = agent_results

    # Print summary
    if verbose and agent_type == "both":
        print_comparison(results)

    # Save results
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    results_path = RESULTS_DIR / f"eval_{timestamp}.json"
    with open(results_path, "w") as f:
        json.dump(results, f, indent=2, default=str)

    if verbose:
        print(f"\nResults saved to: {results_path}")

    return results


def print_comparison(results: dict) -> None:
    """Print a formatted comparison table."""
    print(f"\n{'='*60}")
    print(f"  EVALUATION RESULTS")
    print(f"{'='*60}\n")

    header = f"{'Metric':<25} {'Baseline':>12} {'ContextHub':>12} {'Δ':>8}"
    print(header)
    print("-" * 60)

    baseline = results["agents"].get("baseline", {}).get("totals", {})
    contexthub = results["agents"].get("contexthub", {}).get("totals", {})

    metrics = [
        ("Metric Selection", "metric_selection"),
        ("Source Selection", "source_selection"),
        ("SQL Correctness", "sql_correctness"),
        ("Groundedness", "groundedness"),
        ("Tool Success", "tool_success"),
    ]

    for display_name, key in metrics:
        b_val = baseline.get(key, 0)
        c_val = contexthub.get(key, 0)
        delta = c_val - b_val
        delta_str = f"+{delta:.2%}" if delta > 0 else f"{delta:.2%}"
        print(f"{display_name:<25} {b_val:>11.1%} {c_val:>11.1%} {delta_str:>8}")

    print("-" * 60)

    # Overall average
    b_avg = sum(baseline.values()) / len(baseline) if baseline else 0
    c_avg = sum(contexthub.values()) / len(contexthub) if contexthub else 0
    delta = c_avg - b_avg
    delta_str = f"+{delta:.2%}" if delta > 0 else f"{delta:.2%}"
    print(f"{'Overall Average':<25} {b_avg:>11.1%} {c_avg:>11.1%} {delta_str:>8}")

    print(f"\n{'Latency & Tool Usage':<25}")
    print("-" * 60)

    b_latency = results["agents"].get("baseline", {}).get("avg_latency", 0)
    c_latency = results["agents"].get("contexthub", {}).get("avg_latency", 0)
    b_tools = results["agents"].get("baseline", {}).get("total_tool_calls", 0)
    c_tools = results["agents"].get("contexthub", {}).get("total_tool_calls", 0)
    b_errors = results["agents"].get("baseline", {}).get("errors", 0)
    c_errors = results["agents"].get("contexthub", {}).get("errors", 0)

    print(f"{'Avg Latency (s)':<25} {b_latency:>12.1f} {c_latency:>12.1f}")
    print(f"{'Total Tool Calls':<25} {b_tools:>12} {c_tools:>12}")
    print(f"{'Errors':<25} {b_errors:>12} {c_errors:>12}")
    print()


def main():
    """CLI entry point for evaluation."""
    import argparse

    parser = argparse.ArgumentParser(description="Run ContextHub evaluation")
    parser.add_argument("--agent", choices=["baseline", "contexthub", "both"], default="both")
    parser.add_argument("--questions", type=int, default=None, help="Limit number of questions")
    parser.add_argument("--verbose", action="store_true", default=True)
    parser.add_argument("--quiet", action="store_true")

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO if not args.quiet else logging.WARNING,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )

    run_evaluation(
        agent_type=args.agent,
        limit=args.questions,
        verbose=not args.quiet,
    )


if __name__ == "__main__":
    main()
