from app.agent.agent import DataAnalystAgent
from app.core.report import build_markdown_report
from tests.fakes import FakeLLM, calls, reply, tool


def test_markdown_export(session, settings):
    llm = FakeLLM([calls(tool("run_sql", query="SELECT 1 AS x", purpose="One")), reply("Result is 1.")])
    list(DataAnalystAgent(llm, settings).run(session, "Give me one"))
    md = build_markdown_report(session)
    assert "# DataPilot analysis report" in md and "SELECT 1 AS x" in md and "Result is 1." in md
