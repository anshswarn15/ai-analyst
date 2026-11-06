"""API tests. Skipped automatically if fastapi/httpx are not installed."""
import json
from dataclasses import replace

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

from app.config import Settings  # noqa: E402
from app.main import create_app  # noqa: E402
from tests.fakes import FakeLLM, calls, reply, tool  # noqa: E402


def _client(llm):
    return TestClient(create_app(replace(Settings.from_env(), auth_enabled=False), llm=llm))


def test_end_to_end_flow():
    llm = FakeLLM([calls(tool("run_sql", query="SELECT COUNT(*) AS n FROM sales", purpose="Count")), reply("There are many rows."),
                   reply("Streamed answer.")])
    c = _client(llm)
    assert c.get("/api/health").json()["status"] == "ok"
    sid = c.post("/api/sessions").json()["session_id"]

    bad = c.post(f"/api/sessions/{sid}/files", files=[("files", ("x.xlsx", b"nope", "application/octet-stream"))]).json()
    assert bad["results"][0]["status"] == "rejected"

    loaded = c.post(f"/api/sessions/{sid}/load-samples").json()
    assert {r["status"] for r in loaded["results"]} == {"loaded"}

    turn = c.post(f"/api/sessions/{sid}/chat", json={"message": "how many rows?"}).json()
    assert turn["answer"] == "There are many rows." and turn["artifacts"][0]["type"] == "sql"

    with c.stream("POST", f"/api/sessions/{sid}/chat/stream", json={"message": "again"}) as r:
        body = "".join(r.iter_text())
    events = [json.loads(l[6:]) for l in body.splitlines() if l.startswith("data: ")]
    assert events[-1]["type"] == "final"

    assert c.get(f"/api/sessions/{sid}/dashboard").json()["sections"]
    assert c.post(f"/api/sessions/{sid}/sql", json={"query": "DROP TABLE sales"}).status_code == 400
    assert "DataPilot" in c.get(f"/api/sessions/{sid}/export.md").text
    assert c.get("/api/sessions/nope").status_code == 404


def test_upload_returns_a_safe_per_file_error_for_unexpected_failures(monkeypatch):
    c = _client(FakeLLM([]))
    sid = c.post("/api/sessions").json()["session_id"]
    session = c.app.state.store.get(sid)

    def crash(*_args, **_kwargs):
        raise RuntimeError("parser implementation detail")

    monkeypatch.setattr(session, "add_csv", crash)
    response = c.post(f"/api/sessions/{sid}/files", files=[("files", ("broken.csv", b"a\n1\n", "text/csv"))])

    assert response.status_code == 200
    result = response.json()["results"][0]
    assert result == {"filename": "broken.csv", "status": "rejected",
                      "error": "'broken.csv': the file could not be processed."}


def test_clear_all_files_also_clears_conversation():
    c = _client(FakeLLM([reply("Saved answer.")]))
    sid = c.post("/api/sessions").json()["session_id"]
    c.post(f"/api/sessions/{sid}/load-samples")
    c.post(f"/api/sessions/{sid}/chat", json={"message": "remember this"})

    response = c.delete(f"/api/sessions/{sid}/files")

    assert response.status_code == 200 and len(response.json()["removed"]) == 3
    state = c.get(f"/api/sessions/{sid}").json()
    assert state["tables"] == [] and state["turns"] == []


def test_optional_account_login_and_signup(settings, tmp_path):
    configured = replace(settings, auth_enabled=True, allow_signup=True,
                         auth_db_path=tmp_path / "auth.db", session_secret="test-secret")
    protected = TestClient(create_app(configured, llm=FakeLLM([])))

    assert protected.get("/api/health").status_code == 200
    assert protected.get("/", follow_redirects=False).status_code == 303
    assert "Create your account" in protected.get("/signup").text
    assert protected.post("/signup", data={"username": "analyst", "password": "safe-password"}, follow_redirects=False).status_code == 303
    assert protected.post("/login", data={"username": "analyst", "password": "wrong-password"}).status_code == 200
    assert protected.post("/login", data={"username": "analyst", "password": "safe-password"}, follow_redirects=False).status_code == 303
    assert protected.get("/").status_code == 200
