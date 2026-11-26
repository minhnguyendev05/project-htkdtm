from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI(title="AI Pricing API")

pricing_rules = []
recommendations = []


class PricingRule(BaseModel):
    id: str
    name: str
    min_price: float
    max_price: float


class PreviewRequest(BaseModel):
    cost: float
    competitor_price: float


@app.get("/pricing-rules")
def list_rules():
    return pricing_rules


@app.post("/pricing-rules")
def create_rule(rule: PricingRule):
    pricing_rules.append(rule.dict())
    return rule


@app.post("/pricing/preview")
def preview(req: PreviewRequest):
    pmin = req.cost * 1.1
    suggested = max(pmin, min(req.competitor_price, pmin * 1.2))
    return {"pmin": pmin, "suggested_price": suggested}


@app.post("/pricing/run")
def run_pricing():
    rec = {"id": "r1", "product": "demo", "suggested_price": 100.0, "status": "pending"}
    recommendations.append(rec)
    return rec


@app.get("/recommendations")
def list_recs():
    return recommendations


@app.post("/recommendations/{rid}/approve")
def approve(rid: str):
    for r in recommendations:
        if r["id"] == rid:
            r["status"] = "approved"
            return r
    raise HTTPException(status_code=404, detail="not found")


@app.post("/recommendations/{rid}/reject")
def reject(rid: str):
    for r in recommendations:
        if r["id"] == rid:
            r["status"] = "rejected"
            return r
    raise HTTPException(status_code=404, detail="not found")
"""