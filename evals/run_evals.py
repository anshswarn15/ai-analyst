"""Evaluation harness: asks the REAL model a fixed set of questions about the sample data and checks
the answers against ground truth computed independently with pandas.

    python -m evals.run_evals            # needs an API key in .env
Exit code is non-zero if any case fails, so it can gate a release.
"""
import sys
from pathlib import Path

import pandas as pd

from app.agent.agent import DataAnalystAgent
from app.config import Settings
from app.core.session import SessionStore
from app.llm.client import OpenAICompatClient

SAMPLE = Path(__file__).resolve().parent.parent / "data" / "sample"


def ground_truth():
    sales = pd.read_csv(SAMPLE / "sales.csv")
    cust = pd.read_csv(SAMPLE / "customers.csv")
    by_region = sales.groupby("region")["revenue"].sum()
    top_cust = (sales.groupby("customer_id")["revenue"].sum().nlargest(5).reset_index()
                .merge(cust, on="customer_id"))
    return {"top_region": by_region.idxmax(), "top_customers": top_cust}


def run_turn(agent, session, question):
    final = [e for e in agent.run(session, question) if e["type"] in ("final", "error")][-1]
    if final["type"] == "error":
        raise RuntimeError(final["message"])
    return final["turn"]


def main() -> int:
    settings = Settings.from_env()
    if not settings.llm_configured:
        print("No API key configured - set one in .env first.")
        return 2
    session = SessionStore(settings).create()
    for p in sorted(SAMPLE.glob("*.csv")):
        session.add_csv(p.name, p.read_bytes())
    agent = DataAnalystAgent(OpenAICompatClient(settings), settings)
    truth = ground_truth()
    tools = lambda t: {s["tool"] for s in t["steps"]}
    kinds = lambda t: {a["type"] for a in t["artifacts"]}

    cases = []

    def case(name, question, check):
        cases.append((name, question, check))

    case("top region", "Which region generated the highest revenue?",
         lambda t: truth["top_region"].lower() in t["answer"].lower())
    case("top 5 customers", "What are the top five customers by revenue?",
         lambda t: sum(r.customer_id in t["answer"] or r.customer_name in t["answer"]
                       or any(r.customer_id in str(row) for a in t["artifacts"] if a["type"] == "sql" for row in a["rows"])
                       for r in truth["top_customers"].itertuples()) >= 4)
    case("monthly trend chart", "Show monthly sales trends.",
         lambda t: "chart" in kinds(t))
    case("sql on request", "Generate SQL for revenue by product category.",
         lambda t: "```sql" in t["answer"].lower() and "select" in t["answer"].lower())
    case("anomaly tool used", "Detect anomalies in the dataset.",
         lambda t: "detect_anomalies" in tools(t) and "anomalies" in kinds(t))
    case("data quality", "How is the quality of the sales data?",
         lambda t: "data_quality_report" in tools(t))

    failed = 0
    print(f"model={settings.llm_model}\n")
    for name, question, check in cases:
        try:
            turn = run_turn(agent, session, question)
            ok = bool(check(turn))
            detail = f"{turn['elapsed_ms']} ms, {len(turn['steps'])} tool calls, {turn['usage'].get('prompt_tokens', 0) + turn['usage'].get('completion_tokens', 0)} tokens"
        except Exception as exc:  # noqa: BLE001
            ok, detail = False, f"error: {exc}"
        failed += not ok
        print(f"{'PASS' if ok else 'FAIL'}  {name:<22} {detail}")
    print(f"\n{len(cases) - failed}/{len(cases)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
