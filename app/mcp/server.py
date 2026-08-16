"""MCP Server for ContextHub.

Exposes the context layer tools via the Model Context Protocol (MCP),
providing a standardized interface for AI agents to access business
context, schema information, and execute read-only SQL queries.

Run standalone:
    python -m app.mcp.server

Or use programmatically via ContextTools class for in-process access.
"""

import asyncio
import json
import logging

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import (
    TextContent,
    Tool,
)

from app.mcp.tools import ContextTools

logger = logging.getLogger(__name__)

# Initialize the MCP server
server = Server("contexthub")
tools = ContextTools()


# Define available tools
TOOL_DEFINITIONS = [
    Tool(
        name="search_assets",
        description=(
            "Search for data assets (tables, columns, metrics) by name or description. "
            "Use this FIRST to discover what data assets are relevant to the user's question. "
            "Returns matching assets with metadata including owner, type, and description."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search term (e.g., 'revenue', 'customer', 'orders')",
                }
            },
            "required": ["query"],
        },
    ),
    Tool(
        name="get_definition",
        description=(
            "Get the certified business definition for a specific metric. "
            "Returns the exact calculation, source table/column, required filters, "
            "owner, certification status, and usage examples. "
            "ALWAYS check the definition before writing SQL for a metric."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "metric_name": {
                    "type": "string",
                    "description": "Name of the metric (e.g., 'net_revenue', 'active_customer_count')",
                }
            },
            "required": ["metric_name"],
        },
    ),
    Tool(
        name="get_trust_signal",
        description=(
            "Check the trust/certification status of a data asset or metric. "
            "Returns whether the asset is certified, deprecated, experimental, or stale. "
            "ALWAYS prefer certified metrics over deprecated or experimental ones."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "asset_name": {
                    "type": "string",
                    "description": "Name of the asset or metric to check trust status for",
                }
            },
            "required": ["asset_name"],
        },
    ),
    Tool(
        name="get_schema",
        description=(
            "Get detailed schema information for a database table, including business context "
            "for each column. Use this to understand what columns exist and their business "
            "meaning BEFORE writing SQL. Available tables: customers, orders, products, payments."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "table_name": {
                    "type": "string",
                    "description": "Name of the table (e.g., 'orders', 'customers', 'products', 'payments')",
                }
            },
            "required": ["table_name"],
        },
    ),
    Tool(
        name="get_lineage",
        description=(
            "Get data lineage showing how tables and metrics relate to each other. "
            "Shows foreign key relationships and metric source dependencies."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "asset_name": {
                    "type": "string",
                    "description": "Name of the asset (table name or metric name)",
                }
            },
            "required": ["asset_name"],
        },
    ),
    Tool(
        name="execute_sql",
        description=(
            "Execute a read-only SQL SELECT query against the business database. "
            "ONLY SELECT queries are allowed. Use schema prefix 'business.' for all tables "
            "(e.g., business.orders, business.customers). "
            "Apply appropriate WHERE clauses based on business definitions. "
            "Results are limited to 100 rows."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "SQL SELECT query (e.g., \"SELECT SUM(net_amount) FROM business.orders WHERE status = 'completed' AND order_date >= '2026-07-01'\")",
                }
            },
            "required": ["query"],
        },
    ),
    Tool(
        name="list_metrics",
        description=(
            "List all available business metric definitions with their certification status. "
            "Use this to see what metrics exist and which ones are certified vs deprecated."
        ),
        inputSchema={
            "type": "object",
            "properties": {},
            "required": [],
        },
    ),
]


@server.list_tools()
async def list_tools() -> list[Tool]:
    """List available MCP tools."""
    return TOOL_DEFINITIONS


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    """Handle tool invocations from the MCP client."""
    logger.info(f"MCP tool call: {name}({arguments})")

    try:
        if name == "search_assets":
            result = tools.search_assets(arguments["query"])
        elif name == "get_definition":
            result = tools.get_definition(arguments["metric_name"])
        elif name == "get_trust_signal":
            result = tools.get_trust_signal(arguments["asset_name"])
        elif name == "get_schema":
            result = tools.get_schema(arguments["table_name"])
        elif name == "get_lineage":
            result = tools.get_lineage(arguments["asset_name"])
        elif name == "execute_sql":
            result = tools.execute_sql(arguments["query"])
        elif name == "list_metrics":
            result = tools.list_metrics()
        else:
            result = {"error": f"Unknown tool: {name}"}

        return [TextContent(type="text", text=json.dumps(result, indent=2, default=str))]

    except Exception as e:
        logger.error(f"Tool error {name}: {e}")
        error_result = {"error": str(e), "tool": name}
        return [TextContent(type="text", text=json.dumps(error_result))]


async def run_server():
    """Run the MCP server over stdio."""
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


def main():
    """Entry point for running MCP server standalone."""
    logging.basicConfig(level=logging.INFO)
    logger.info("Starting ContextHub MCP Server...")
    asyncio.run(run_server())


if __name__ == "__main__":
    main()
