"""FastAPI adapter for the Excel Analysis engine.

This is deliberately thin: it accepts uploaded workbooks, feeds them through the
existing loader + comparison pipeline, and returns the already-serialized
AnalysisResult under a metadata wrapper. It performs no analysis and recomputes
no values.
"""

from __future__ import annotations

import json
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from .adapters.serialization import analysis_to_json
from .adapters.workbook_loader import load_workbook
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
            result = compare_workbooks(load_workbook(str(left.path)), load_workbook(str(right.path)))
        except AnalysisError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    return {
        "metadata": {
            "request_id": request_id,
            "engine_version": "0.1.0",
            "left_filename": left.filename,
            "right_filename": right.filename,
        },
        "analysis": json.loads(analysis_to_json(result, indent=None)),
    }


def _validate_upload(upload: UploadFile) -> None:
    filename = upload.filename or ""
    if not filename.lower().endswith(".xlsx"):
        raise HTTPException(status_code=400, detail=f"Only .xlsx files are supported: {filename}")


async def _persist_upload(upload: UploadFile, target: Path) -> UploadedWorkbook:
    target.write_bytes(await upload.read())
    return UploadedWorkbook(filename=upload.filename or target.name, path=target)
