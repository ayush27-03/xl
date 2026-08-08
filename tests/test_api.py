from fastapi.testclient import TestClient

import excel_analysis.api as api
from excel_analysis.api import _is_local, app

_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def test_compare_endpoint_returns_metadata_and_analysis(compare_pair):
    client = TestClient(app)
    with open(compare_pair["compare_left"], "rb") as left, open(
        compare_pair["compare_right"], "rb"
    ) as right:
        response = client.post(
            "/compare",
            files={
                "left_file": ("left.xlsx", left, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
                "right_file": ("right.xlsx", right, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["metadata"]["left_filename"] == "left.xlsx"
    assert payload["metadata"]["right_filename"] == "right.xlsx"
    assert payload["metadata"]["engine_version"] == "0.1.0"
    assert "request_id" in payload["metadata"]
    assert payload["analysis"]["comparison"]["alignment"]["row_key"] == "Emp_ID"
    assert payload["analysis"]["insights"][0]["severity"] == "integrity"
    assert payload["presentation"]["ai_summary"] == {
        "requested": False,
        "available": False,
        "model": None,
        "bullets": [],
        "note": "AI summary not requested.",
        "source": "none",
    }


def test_compare_endpoint_returns_validated_ai_summary_outside_analysis(compare_pair, monkeypatch):
    def fake_narrate(self, insights, warnings):
        return ("DoB changed in 1/3 rows.", "Salary changed by +10.0%.")

    monkeypatch.setattr(api.OllamaAIProvider, "narrate", fake_narrate)
    client = TestClient(app)
    with open(compare_pair["compare_left"], "rb") as left, open(
        compare_pair["compare_right"], "rb"
    ) as right:
        response = client.post(
            "/compare?ai=true&ai_model=llama3.2",
            files={
                "left_file": ("left.xlsx", left, _XLSX),
                "right_file": ("right.xlsx", right, _XLSX),
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert "ai_summary" not in payload["analysis"]
    assert payload["presentation"]["ai_summary"] == {
        "requested": True,
        "available": True,
        "model": "llama3.2",
        "bullets": ["DoB changed in 1/3 rows.", "Salary changed by +10.0%."],
        "note": None,
        "source": "ollama",
    }


def test_compare_endpoint_falls_back_when_ai_unavailable(compare_pair, monkeypatch):
    monkeypatch.setattr(api.OllamaAIProvider, "narrate", lambda self, insights, warnings: ())
    client = TestClient(app)
    with open(compare_pair["compare_left"], "rb") as left, open(
        compare_pair["compare_right"], "rb"
    ) as right:
        response = client.post(
            "/compare?ai=true",
            files={
                "left_file": ("left.xlsx", left, _XLSX),
                "right_file": ("right.xlsx", right, _XLSX),
            },
        )

    assert response.status_code == 200
    payload = response.json()
    summary = payload["presentation"]["ai_summary"]
    assert summary["requested"] is True
    assert summary["available"] is False
    assert summary["model"] == "llama3.2"
    assert summary["source"] == "deterministic_fallback"
    assert summary["note"] == "AI summary unavailable; showing deterministic insights instead."
    assert summary["bullets"][0] == payload["analysis"]["insights"][0]["message"]


def test_compare_endpoint_rejects_non_xlsx(compare_pair):
    client = TestClient(app)
    with open(compare_pair["compare_right"], "rb") as right:
        response = client.post(
            "/compare",
            files={
                "left_file": ("left.csv", b"not,xlsx", "text/csv"),
                "right_file": ("right.xlsx", right, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
            },
        )

    assert response.status_code == 400
    assert "Only .xlsx files are supported" in response.json()["detail"]


def test_oversized_upload_returns_413_before_parsing(compare_pair, monkeypatch):
    monkeypatch.setattr(api, "_MAX_UPLOAD_BYTES", 16)  # tiny cap; the fixtures exceed it
    client = TestClient(app)
    with open(compare_pair["compare_left"], "rb") as left, open(
        compare_pair["compare_right"], "rb"
    ) as right:
        response = client.post(
            "/compare",
            files={
                "left_file": ("left.xlsx", left, _XLSX),
                "right_file": ("right.xlsx", right, _XLSX),
            },
        )
    assert response.status_code == 413
    assert "too large" in response.json()["detail"].lower()


def test_is_local_accepts_loopback_and_rejects_remote():
    assert _is_local("127.0.0.1") and _is_local("::1") and _is_local("localhost")
    assert not _is_local("10.0.0.5")
    assert not _is_local("1.2.3.4")
    assert not _is_local(None)
