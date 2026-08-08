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
