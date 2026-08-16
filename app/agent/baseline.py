"""Baseline agent - has database access but NO business context layer.

This agent can only see the raw schema and execute SQL queries.
It represents the "naive" approach where an LLM is given database
access without understanding business definitions, trust signals,
or metric semantics.

Used as the control group in evaluation.
"""

import json
import logging
import time
from typing import Any, TypedDict

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool
from langgraph.graph import END, StateGraph
from langgraph.prebuilt import ToolNode

from app.agent.llm import get_llm
from app.agent.prompts import BASELINE_SYSTEM_PROMPT
from app.mcp.tools import ContextTools

logger = logging.getLogger(__name__)


# --- Tool definitions for baseline agent (only SQL execution) ---

_tools_instance = ContextTools()


@tool
def execute_sql(query: str) -> str:
    """Execute a read-only SQL SELECT query against the business database.

    Only SELECT queries are allowed. Use 'business.' schema prefix for all tables
    (e.g., business.orders, business.customers).

    Args:
        query: SQL SELECT query to execute
    """
    result = _tools_instance.execute_sql(query)
    return json.dumps(result, default=str)


# Baseline only gets SQL execution - no context tools
BASELINE_TOOLS = [execute_sql]


# --- LangGraph State ---

class AgentState(TypedDict):
    """State for the LangGraph agent."""
    messages: list
    tool_calls_log: list[dict[str, Any]]
    start_time: float


# --- LangGraph Nodes ---

def agent_node(state: AgentState) -> dict:
    """The LLM reasoning node - decides whether to call a tool or respond."""
    llm = get_llm(temperature=0.0)
    llm_with_tools = llm.bind_tools(BASELINE_TOOLS)

    messages = state["messages"]
    response = llm_with_tools.invoke(messages)

    if response.content == [] or response.content is None:
        response.content = ""

    return {"messages": [response]}


def tool_node(state: AgentState) -> dict:
    """Execute tools and log the calls."""
    messages = state["messages"]
    last_message = messages[-1]

    tool_messages = []
    tool_logs = state.get("tool_calls_log", [])

    for tool_call in last_message.tool_calls:
        tool_name = tool_call["name"]
        tool_args = tool_call["args"]

        logger.info(f"[Baseline] Tool call: {tool_name}({tool_args})")

        # Execute the tool
        if tool_name == "execute_sql":
            result = _tools_instance.execute_sql(tool_args.get("query", ""))
        else:
            result = {"error": f"Unknown tool: {tool_name}"}

        result_str = json.dumps(result, default=str)

        tool_messages.append(
            ToolMessage(content=result_str, tool_call_id=tool_call["id"])
        )

        tool_logs.append({
            "tool": tool_name,
            "args": tool_args,
            "result_preview": result_str[:500],
        })

    return {
        "messages": tool_messages,
        "tool_calls_log": tool_logs,
    }


def should_continue(state: AgentState) -> str:
    """Determine if the agent should call more tools or finish."""
    messages = state["messages"]
    last_message = messages[-1]

    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        return "tools"
    return END


# --- Build the Graph ---

def build_baseline_graph():
    """Build the LangGraph for the baseline agent."""
    workflow = StateGraph(AgentState)

    workflow.add_node("agent", agent_node)
    workflow.add_node("tools", tool_node)

    workflow.set_entry_point("agent")
    workflow.add_conditional_edges("agent", should_continue, {"tools": "tools", END: END})
    workflow.add_edge("tools", "agent")

    return workflow.compile()


# --- Public Interface ---

class BaselineAgent:
    """Baseline agent with only schema knowledge and SQL execution.

    No access to business definitions, trust signals, or context layer.
    """

    def __init__(self):
        self.graph = build_baseline_graph()
        self.name = "baseline"

    def ask(self, question: str) -> dict[str, Any]:
        """Ask the baseline agent a question.

        Args:
            question: Natural language question about the data

        Returns:
            Dict with answer, tool_calls, latency, etc.
        """
        start_time = time.time()

        initial_state: AgentState = {
            "messages": [
                SystemMessage(content=BASELINE_SYSTEM_PROMPT),
                HumanMessage(content=question),
            ],
            "tool_calls_log": [],
            "start_time": start_time,
        }

        try:
            final_state = self.graph.invoke(initial_state)

            # Extract the final answer
            messages = final_state["messages"]
            final_answer = ""
            for msg in reversed(messages):
                if isinstance(msg, AIMessage) and not msg.tool_calls:
                    final_answer = msg.content
                    break

            elapsed = time.time() - start_time

            return {
                "agent": self.name,
                "question": question,
                "answer": final_answer,
                "tool_calls": final_state.get("tool_calls_log", []),
                "latency_seconds": round(elapsed, 2),
                "success": True,
                "error": None,
            }

        except Exception as e:
            elapsed = time.time() - start_time
            logger.error(f"[Baseline] Error: {e}")
            return {
                "agent": self.name,
                "question": question,
                "answer": f"Error: {str(e)}",
                "tool_calls": [],
                "latency_seconds": round(elapsed, 2),
                "success": False,
                "error": str(e),
            }
