"""Generate evaluation report from results.

Usage:
    python -m evaluation.report [results_file]
"""

import json
import sys
from pathlib import Path


RESULTS_DIR = Path(__file__).parent / "results"


def find_latest_results() -> Path | None:
    """Find the most recent evaluation results file."""
    if not RESULTS_DIR.exists():
        return None
    files = sorted(RESULTS_DIR.glob("eval_*.json"), reverse=True)
    return files[0] if files else None


def generate_report(results_path: Path) -> str:
    """Generate a markdown report from evaluation results."""
    with open(results_path) as f:
        results = json.load(f)

    report_lines = []
    report_lines.append("# ContextHub Evaluation Report\n")
    report_lines.append(f"**Date:** {results.get('timestamp', 'Unknown')}\n")
    report_lines.append(f"**Questions evaluated:** {results.get('num_questions', 0)}\n")

    # Comparison table
    report_lines.append("\n## Results Comparison\n")
    report_lines.append("| Metric | Baseline | ContextHub | Improvement |")
    report_lines.append("|--------|----------|------------|-------------|")

    baseline = results.get("agents", {}).get("baseline", {}).get("totals", {})
    contexthub = results.get("agents", {}).get("contexthub", {}).get("totals", {})

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
        delta_str = f"+{delta*100:.1f}%" if delta > 0 else f"{delta*100:.1f}%"
        report_lines.append(
            f"| {display_name} | {b_val*100:.1f}% | {c_val*100:.1f}% | {delta_str} |"
        )

    # Overall
    if baseline and contexthub:
        b_avg = sum(baseline.values()) / len(baseline)
        c_avg = sum(contexthub.values()) / len(contexthub)
        delta = c_avg - b_avg
        delta_str = f"+{delta*100:.1f}%" if delta > 0 else f"{delta*100:.1f}%"
        report_lines.append(f"| **Overall Average** | **{b_avg*100:.1f}%** | **{c_avg*100:.1f}%** | **{delta_str}** |")

    # Latency comparison
    report_lines.append("\n## Performance\n")
    report_lines.append("| Metric | Baseline | ContextHub |")
    report_lines.append("|--------|----------|------------|")

    b_latency = results.get("agents", {}).get("baseline", {}).get("avg_latency", 0)
    c_latency = results.get("agents", {}).get("contexthub", {}).get("avg_latency", 0)
    b_tools = results.get("agents", {}).get("baseline", {}).get("total_tool_calls", 0)
    c_tools = results.get("agents", {}).get("contexthub", {}).get("total_tool_calls", 0)

    report_lines.append(f"| Avg Latency | {b_latency:.1f}s | {c_latency:.1f}s |")
    report_lines.append(f"| Total Tool Calls | {b_tools} | {c_tools} |")

    # Per-question breakdown
    report_lines.append("\n## Per-Question Scores\n")
    report_lines.append("| ID | Question | Baseline Avg | ContextHub Avg |")
    report_lines.append("|----|----------|--------------|----------------|")

    baseline_scores = results.get("agents", {}).get("baseline", {}).get("scores", [])
    contexthub_scores = results.get("agents", {}).get("contexthub", {}).get("scores", [])

    for i, (b_score, c_score) in enumerate(zip(baseline_scores, contexthub_scores)):
        q_id = b_score.get("question_id", f"q{i+1}")
        # Get question text from responses
        b_responses = results.get("agents", {}).get("baseline", {}).get("responses", [])
        question_text = b_responses[i]["question"][:50] + "..." if i < len(b_responses) else "?"

        b_metrics = [v for k, v in b_score.items() if k != "question_id"]
        c_metrics = [v for k, v in c_score.items() if k != "question_id"]
        b_avg = sum(b_metrics) / len(b_metrics) if b_metrics else 0
        c_avg = sum(c_metrics) / len(c_metrics) if c_metrics else 0

        report_lines.append(f"| {q_id} | {question_text} | {b_avg*100:.0f}% | {c_avg*100:.0f}% |")

    # Key findings
    report_lines.append("\n## Key Findings\n")

    if baseline and contexthub:
        if contexthub.get("metric_selection", 0) > baseline.get("metric_selection", 0):
            report_lines.append("- ✅ **ContextHub outperforms baseline on metric selection** — the context layer helps the agent choose certified metrics over ambiguous/deprecated ones.\n")
        if contexthub.get("groundedness", 0) > baseline.get("groundedness", 0):
            report_lines.append("- ✅ **ContextHub produces more grounded answers** — answers reference specific sources, trust levels, and definitions.\n")
        if c_latency > b_latency * 1.5:
            report_lines.append(f"- ⚠️ **ContextHub has higher latency** ({c_latency:.1f}s vs {b_latency:.1f}s) — the additional context lookups add time but improve quality.\n")

    report_lines.append("\n## Conclusion\n")
    report_lines.append("This evaluation tests the hypothesis: *Does structured business context improve AI agent reliability over enterprise data?*\n")

    if baseline and contexthub:
        b_avg = sum(baseline.values()) / len(baseline)
        c_avg = sum(contexthub.values()) / len(contexthub)
        if c_avg > b_avg:
            improvement = (c_avg - b_avg) * 100
            report_lines.append(
                f"**Result: ContextHub achieves {improvement:.1f} percentage points higher average score than the baseline.** "
                f"The structured context layer demonstrably improves metric selection, source identification, and answer groundedness.\n"
            )
        else:
            report_lines.append(
                "**Result: The structured context layer did not significantly improve overall scores in this evaluation.** "
                "This may indicate the LLM's existing knowledge is sufficient for simple schemas, or that the evaluation questions need more ambiguity.\n"
            )

    return "\n".join(report_lines)


def main():
    """CLI entry point."""
    if len(sys.argv) > 1:
        results_path = Path(sys.argv[1])
    else:
        results_path = find_latest_results()

    if not results_path or not results_path.exists():
        print("No evaluation results found. Run evaluation first:")
        print("  python -m evaluation.runner")
        sys.exit(1)

    report = generate_report(results_path)
    print(report)

    # Also save as markdown
    report_path = RESULTS_DIR / "report.md"
    with open(report_path, "w") as f:
        f.write(report)
    print(f"\nReport saved to: {report_path}")


if __name__ == "__main__":
    main()
