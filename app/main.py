"""FastAPI application for ContextHub.

Exposes a simple API for querying the AI agents.

Usage:
    uvicorn app.main:app --reload
"""

import logging
import time
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from app.config import get_settings

logger = logging.getLogger(__name__)

app = FastAPI(
    title="ContextHub",
    description="AI Context Layer for Enterprise Data - structured business context makes AI agents more reliable",
    version="1.0.0",
)

# CORS - allow frontend to call backend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- Request/Response Models ---


class AskRequest(BaseModel):
    """Request model for the /ask endpoint."""
    question: str = Field(..., description="Natural language question about the enterprise data")
    agent: str = Field(default="contexthub", description="Agent to use: 'contexthub' or 'baseline'")


class ToolCallInfo(BaseModel):
    """Information about a tool call made by the agent."""
    tool: str
    args: dict[str, Any]
    result_preview: str | None = None


class AskResponse(BaseModel):
    """Response model for the /ask endpoint."""
    answer: str
    agent: str
    question: str
    sources: list[dict[str, str]] = []
    tool_calls: list[ToolCallInfo] = []
    latency_seconds: float
    success: bool
    error: str | None = None


class HealthResponse(BaseModel):
    """Health check response."""
    status: str
    version: str


# --- Endpoints ---


@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint."""
    return HealthResponse(status="healthy", version="1.0.0")


@app.post("/ask", response_model=AskResponse)
async def ask_question(request: AskRequest):
    """Ask a question to the AI agent.

    The ContextHub agent will:
    1. Search for relevant assets
    2. Look up business definitions
    3. Check trust signals
    4. Generate and execute SQL
    5. Return a grounded answer with sources
    """
    try:
        if request.agent == "baseline":
            from app.agent.baseline import BaselineAgent
            agent = BaselineAgent()
        elif request.agent == "contexthub":
            from app.agent.contexthub import ContextHubAgent
            agent = ContextHubAgent()
        else:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown agent: {request.agent}. Use 'contexthub' or 'baseline'.",
            )

        response = agent.ask(request.question)

        return AskResponse(
            answer=response.get("answer", ""),
            agent=response.get("agent", request.agent),
            question=request.question,
            sources=response.get("sources", []),
            tool_calls=[
                ToolCallInfo(
                    tool=tc.get("tool", ""),
                    args=tc.get("args", {}),
                    result_preview=tc.get("result_preview", "")[:200],
                )
                for tc in response.get("tool_calls", [])
            ],
            latency_seconds=response.get("latency_seconds", 0),
            success=response.get("success", False),
            error=response.get("error"),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing question: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/metrics")
async def list_available_metrics():
    """List all available business metrics and their status."""
    from app.mcp.tools import ContextTools

    tools = ContextTools()
    result = tools.list_metrics()
    return result


@app.get("/schema/{table_name}")
async def get_table_schema(table_name: str):
    """Get schema information for a table."""
    from app.mcp.tools import ContextTools

    tools = ContextTools()
    result = tools.get_schema(table_name)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result
