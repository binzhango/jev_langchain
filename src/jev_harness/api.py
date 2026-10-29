"""A local-only FastAPI surface for the teaching dashboard."""
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal
import json

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .config import Settings
from .domain import SCENARIOS, AUTO_REFUND_LIMIT, HARD_REFUND_LIMIT
from .runner import ComparisonRunner


class StartRequest(BaseModel):
    scenario_id: str = "missing-item"
    task: str | None = Field(default=None, max_length=10000)
    execution: Literal["live", "fixture"] = "live"


class ReviewRequest(BaseModel):
    path: Literal["normal", "jev"]
    review_id: str
    decision: Literal["approve", "edit", "reject"]
    args: dict | None = None


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    runner = ComparisonRunner(settings)

    @asynccontextmanager
    async def lifespan(app):
        yield
        runner.close()

    app = FastAPI(title="Jev Decision Lab", lifespan=lifespan)
    app.state.runner = runner

    @app.exception_handler(KeyError)
    async def not_found(request, error):
        return JSONResponse(status_code=404, content={"detail": "Comparison not found."})

    @app.exception_handler(ValueError)
    async def bad_request(request, error):
        return JSONResponse(status_code=400, content={"detail": settings.safe_error(error)})

    @app.get("/api/config")
    def configuration():
        return {"model": settings.model, "base_url": settings.base_url, "jev_model": settings.jev_model,
                "jev_configured": bool(settings.jev_token), "risk_threshold": settings.risk_threshold,
                "auto_refund_limit": AUTO_REFUND_LIMIT, "hard_refund_limit": HARD_REFUND_LIMIT}

    @app.get("/api/scenarios")
    def scenarios():
        return SCENARIOS

    @app.get("/benchmark/{filename}")
    def benchmark_report(filename: Literal["report.html", "report.json", "report.md"]):
        path = settings.data_dir / "benchmark" / filename
        if not path.is_file():
            raise HTTPException(status_code=404, detail="Run uv run jev-lab benchmark first; save output to your data directory's benchmark folder.")
        return FileResponse(path, headers={"Cache-Control": "no-store"})

    @app.get("/api/comparisons")
    def comparisons():
        return runner.store.list()

    @app.post("/api/comparisons", status_code=202)
    def start(request: StartRequest):
        return runner.create(request.scenario_id, task=request.task, execution=request.execution)

    @app.get("/api/comparisons/{identifier}")
    def comparison(identifier: str):
        return runner.store.get(identifier)

    @app.post("/api/comparisons/{identifier}/review", status_code=202)
    def review(identifier: str, request: ReviewRequest):
        return runner.review(identifier, request.path, request.review_id, request.decision, request.args)

    @app.get("/api/comparisons/{identifier}/export")
    def export(identifier: str):
        value = runner.store.get(identifier)
        return Response(json.dumps(value, indent=2), media_type="application/json",
                        headers={"Content-Disposition": f'attachment; filename="comparison-{value["id"]}.json"'})

    dist = Path(__file__).resolve().parents[2] / "dashboard" / "dist"
    if (dist / "assets").exists():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

    @app.get("/")
    def index():
        if (dist / "index.html").exists():
            return FileResponse(dist / "index.html")
        return JSONResponse({"message": "Build the dashboard: npm --prefix dashboard install && npm --prefix dashboard run build", "api_docs": "/docs"})

    return app
