from app.agent.agent import DataAnalystAgent, split_followups
from app.agent.tools import ToolExecutor
from app.llm.prompts import SYSTEM_PROMPT
from tests.fakes import FakeLLM, calls, reply, tool


def test_split_followups():
    text, fu = split_followups("Answer.\n```followups\n- a?\n2. b?\n```")
    assert text == "Answer." and fu == ["a?", "b?"]


def test_prompt_requires_evidence_for_summary_insights():
    assert "describe_table" in SYSTEM_PROMPT
    assert "computed that exact metric" in SYSTEM_PROMPT
    assert "NEVER sum totals and detail rows" in SYSTEM_PROMPT


def test_tool_executor_errors_are_returned_not_raised(session):
    ex = ToolExecutor(session)
    out = ex.execute("run_sql", {"query": "SELECT * FROM missing_table", "purpose": "x"})
    assert not out.ok and "error" in out.llm_text
    assert not ex.execute("nonexistent_tool", {}).ok
    assert not ex.execute("run_sql", {"wrong": 1}).ok
    assert not ex.execute("run_sql", {"__parse_error__": "{bad"}).ok
    assert not ex.execute("detect_anomalies", {"table": "nope"}).ok


def test_full_agent_turn_with_self_correction_and_context(session, settings):
    llm = FakeLLM([
        calls(tool("run_sql", query="SELECT regionn FROM sales", purpose="oops")),           # bad SQL
        calls(tool("run_sql", query="SELECT region, SUM(revenue) r FROM sales GROUP BY 1 ORDER BY 2 DESC LIMIT 1", purpose="Top region"),
              tool("create_chart", chart_type="bar", query="SELECT region, SUM(revenue) r FROM sales GROUP BY 1",
                   x="region", y=["r"], title="Revenue by region")),
        reply("**North** leads.\n\n**How I got this**\n- sales.revenue\n```followups\nBreak down by month?\n```"),
    ])
    agent = DataAnalystAgent(llm, settings)
    events = list(agent.run(session, "Which region generated the highest revenue?"))
    kinds = [e["type"] for e in events]
    assert kinds[0] == "status" and kinds[-1] == "final"
    assert [e["ok"] for e in events if e["type"] == "tool_result"] == [False, True, True]
    final = events[-1]["turn"]
    assert final["answer"].startswith("**North**") and final["followups"] == ["Break down by month?"]
    assert {a["type"] for a in final["artifacts"]} == {"sql", "chart"}
    assert final["usage"]["llm_calls"] == 3

    # second turn: history must be sent to the model (conversation context)
    llm2 = FakeLLM([reply("Done.")])
    list(DataAnalystAgent(llm2, settings).run(session, "and for 2025 only?"))
    sent = llm2.calls[0]["messages"]
    assert sent[0]["role"] == "system" and "TABLE sales" in sent[0]["content"]
    assert any("Which region" in m["content"] for m in sent if m["role"] == "user")
    assert len(session.turns) == 2


def test_no_data_short_circuits_without_calling_llm(settings):
    from app.core.session import SessionStore
    empty = SessionStore(settings).create()
    llm = FakeLLM([])
    events = list(DataAnalystAgent(llm, settings).run(empty, "hi"))
    assert events[-1]["type"] == "final" and "Upload" in events[-1]["turn"]["answer"] and not llm.calls


def test_step_limit_forces_final_answer(session, settings):
    from dataclasses import replace
    s = replace(settings, max_agent_steps=2)
    loop = calls(tool("run_sql", query="SELECT 1", purpose="loop"))
    llm = FakeLLM([loop, loop, reply("Gave up looping.")])
    events = list(DataAnalystAgent(llm, s).run(session, "q"))
    assert events[-1]["turn"]["answer"] == "Gave up looping."
    assert llm.calls[-1]["tools"] is None  # last call forbids tools


def test_llm_error_becomes_error_event(session, settings):
    from app.llm.client import LLMError

    class Boom:
        def chat(self, *a, **k):
            raise LLMError("provider down")

    events = list(DataAnalystAgent(Boom(), settings).run(session, "q"))
    assert events[-1] == {"type": "error", "message": "provider down"}
    assert session.turns == []


def test_anomaly_forecast_quality_tools(session):
    ex = ToolExecutor(session)
    assert ex.execute("detect_anomalies", {"table": "sales"}).artifact["type"] == "anomalies"
    assert ex.execute("data_quality_report", {}).artifact["type"] == "quality"
    f = ex.execute("forecast", {"query": "SELECT strftime('%Y-%m', order_date) m, SUM(revenue) v FROM sales GROUP BY 1",
                                "date_column": "m", "value_column": "v", "periods": 4})
    assert f.ok and len(f.artifact["chart"]["labels"]) == 24 + 4
