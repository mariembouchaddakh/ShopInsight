"""BO4 customer assistant endpoints."""
from __future__ import annotations
from fastapi import APIRouter, Depends, Query
from ..registry import AgentRegistry
from ..schemas import AgentReportResponse, BO4AskRequest, ToolResponse
from .common import registry, run_report, run_tool

router = APIRouter(prefix="/api/bo4", tags=["BO4 - Assistant client"])

@router.get("/orders/{order_id}/context", response_model=ToolResponse)
def context(order_id: str, as_of: str | None = Query(None), reg: AgentRegistry = Depends(registry)):
    return run_tool(reg, "bo4", "get_order_context", lambda a: a.get_delivery_context(order_id, as_of))

@router.get("/orders/{order_id}/eta", response_model=ToolResponse)
def eta(order_id: str, as_of: str | None = Query(None), reg: AgentRegistry = Depends(registry)):
    return run_tool(reg, "bo4", "predict_delivery_interval", lambda a: a.predict_delivery_interval(order_id, as_of))

@router.get("/orders/{order_id}/similar", response_model=ToolResponse)
def similar(order_id: str, as_of: str | None = Query(None), k: int = Query(5, ge=1, le=20), reg: AgentRegistry = Depends(registry)):
    return run_tool(reg, "bo4", "find_similar_orders", lambda a: a.find_similar_orders(order_id, as_of, k))

@router.post("/ask", response_model=AgentReportResponse)
def ask(body: BO4AskRequest, reg: AgentRegistry = Depends(registry)):
    return run_report(reg, "bo4", lambda a: a.answer_customer_question(body.order_id, body.question, body.as_of))
