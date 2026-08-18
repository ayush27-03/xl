"""FastAPI adapter for the Excel Analysis engine.

This is deliberately thin: it accepts uploaded workbooks, feeds them through the
existing loader + comparison pipeline, and returns the already-serialized
AnalysisResult under a metadata wrapper. It performs no analysis and recomputes
no values.
"""

from __future__ import annotations

import ipaddress
import json
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, File, HTTPException, Query, Request, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

# Reject any upload larger than this before openpyxl parses it (413). Real
# workbooks are small; this caps memory/DoS from a hostile or accidental upload.
_MAX_UPLOAD_BYTES = 25 * 1024 * 1024  # 25 MiB
_UPLOAD_CHUNK = 1024 * 1024           # 1 MiB

from .adapters.ai import NullAIProvider, OllamaAIProvider
from .adapters.report_pdf import render_pdf
from .adapters.report_xlsx import render_xlsx
from .adapters.serialization import analysis_to_json
from .adapters.workbook_loader import load_workbook
from .app.payroll_report import build_payroll_report, period_token
from .app.pipeline import compare_workbooks
from .domain.errors import AnalysisError


app = FastAPI(
    title="Excel Analysis Tool API",
    version="0.1.0",
    description="Thin HTTP adapter over the deterministic Excel comparison engine.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=False,
    allow_methods=["POST", "GET", "OPTIONS"],
    allow_headers=["*"],
)

# Local-only enforcement. Even if the server is (mis)configured to bind 0.0.0.0,
# any request from a non-loopback peer is refused: payroll data must never be
# reachable over the network.
_LOCAL_HOST_NAMES = frozenset({"localhost", "testclient"})  # 'testclient' = in-process test peer


def _is_local(host: Optional[str]) -> bool:
    if host in _LOCAL_HOST_NAMES:
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except (ValueError, TypeError):
        return False


@app.middleware("http")
async def _local_only(request: Request, call_next):
    client = request.client
    if client is None or not _is_local(client.host):
        return JSONResponse(
            status_code=403, content={"detail": "This API is local-only; remote access is refused."}
        )
    return await call_next(request)


@dataclass(frozen=True)
class UploadedWorkbook:
    filename: str
    path: Path


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/compare")
async def compare_endpoint(
    left_file: UploadFile = File(...),
    right_file: UploadFile = File(...),
    ai: bool = Query(False, description="Opt in to local Ollama narration."),
    ai_model: str = Query("llama3.2", description="Local Ollama model name."),
    anchor: str = Query("Net Payable", description="Headline total column for the reconciliation bridge."),
) -> dict[str, Any]:
    """Compare two uploaded .xlsx workbooks.

    The response shape is AnalysisResponse:

    {
      "metadata": {...},
      "analysis": AnalysisResult-as-JSON-object
    }
    """
    _validate_upload(left_file)
    _validate_upload(right_file)
    request_id = str(uuid.uuid4())

    with tempfile.TemporaryDirectory(prefix="excel-analysis-") as tmp:
        left = await _persist_upload(left_file, Path(tmp) / "left.xlsx")
        right = await _persist_upload(right_file, Path(tmp) / "right.xlsx")
        try:
            result = compare_workbooks(
                load_workbook(str(left.path)), load_workbook(str(right.path)), anchor=anchor
            )
        except AnalysisError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    analysis = json.loads(analysis_to_json(result, indent=None))
    return {
        "metadata": {
            "request_id": request_id,
            "engine_version": "0.1.0",
            "left_filename": left.filename,
            "right_filename": right.filename,
        },
        "analysis": analysis,
        "presentation": {
            "ai_summary": _ai_summary(result, requested=ai, model=ai_model),
        },
    }


_REPORT_MEDIA = {
    "pdf": "application/pdf",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}


@app.post("/report")
async def report_endpoint(
    left_file: UploadFile = File(...),
    right_file: UploadFile = File(...),
    fmt: str = Query("pdf", alias="format", description="Report file format: pdf or xlsx."),
    anchor: str = Query("Net Payable", description="Headline total column for the reconciliation."),
    prepared_by: str = Query("Payroll Portal", description="Name shown on the report header."),
) -> Response:
    """Generate the one-page reconciliation report as a real file. Every figure
    is the Python-canonical value; the file is streamed with a period-encoded
    name so it is self-identifying in an inbox."""
    _validate_upload(left_file)
    _validate_upload(right_file)
    if fmt not in _REPORT_MEDIA:
        raise HTTPException(status_code=400, detail="format must be 'pdf' or 'xlsx'.")

    with tempfile.TemporaryDirectory(prefix="excel-analysis-") as tmp:
        left = await _persist_upload(left_file, Path(tmp) / "left.xlsx")
        right = await _persist_upload(right_file, Path(tmp) / "right.xlsx")
        try:
            left_raw = load_workbook(str(left.path))
            right_raw = load_workbook(str(right.path))
            result = compare_workbooks(left_raw, right_raw, anchor=anchor)
            report = build_payroll_report(
                result, left_raw, right_raw,
                left_name=left.filename, right_name=right.filename, prepared_by=prepared_by,
            )
        except AnalysisError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except ValueError as exc:  # reconciliation not applicable to these files
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    data = render_pdf(report) if fmt == "pdf" else render_xlsx(report)
    filename = f"Payroll_Reconciliation_{period_token(report.period_prev)}_vs_{period_token(report.period_curr)}.{fmt}"
    return Response(
        content=data,
        media_type=_REPORT_MEDIA[fmt],
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _ai_summary(result, *, requested: bool, model: str) -> dict[str, Any]:
    """Presentation-only narration. Never mutates AnalysisResult."""
    if not requested:
        return {
            "requested": False,
            "available": False,
            "model": None,
            "bullets": [],
            "note": "AI summary not requested.",
            "source": "none",
        }

    provider = OllamaAIProvider(model) if model else NullAIProvider()
    bullets = provider.narrate(result.insights, result.warnings)
    if bullets:
        return {
            "requested": True,
            "available": True,
            "model": model,
            "bullets": list(bullets),
            "note": None,
            "source": "ollama",
        }

    return {
        "requested": True,
        "available": False,
        "model": model,
        "bullets": [insight.message for insight in result.insights],
        "note": "AI summary unavailable; showing deterministic insights instead.",
        "source": "deterministic_fallback",
    }


def _validate_upload(upload: UploadFile) -> None:
    filename = upload.filename or ""
    if not filename.lower().endswith(".xlsx"):
        raise HTTPException(status_code=400, detail=f"Only .xlsx files are supported: {filename}")


async def _persist_upload(upload: UploadFile, target: Path) -> UploadedWorkbook:
    """Stream the upload to disk, rejecting (413) once it exceeds the cap - before
    the file is ever handed to openpyxl."""
    size = 0
    with target.open("wb") as sink:
        while chunk := await upload.read(_UPLOAD_CHUNK):
            size += len(chunk)
            if size > _MAX_UPLOAD_BYTES:
                raise HTTPException(
                    status_code=413,
                    detail=(
                        f"File too large: {upload.filename or target.name} exceeds "
                        f"{_MAX_UPLOAD_BYTES // (1024 * 1024)} MiB."
                    ),
                )
            sink.write(chunk)
    return UploadedWorkbook(filename=upload.filename or target.name, path=target)


def run(port: int = 8000) -> None:
    """Serve the API on loopback only. The host is fixed to 127.0.0.1 and cannot
    be overridden - the data must never leave this machine."""
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=port)


if __name__ == "__main__":
    run()
