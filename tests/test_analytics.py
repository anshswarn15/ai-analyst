import pytest
import pandas as pd

from app.core.anomalies import detect_anomalies
from app.core.charts import ChartError, build_chart
from app.core.dashboard import build_dashboard
from app.core.forecasting import forecast_series
from app.core.profiling import quality_report, schema_prompt


def test_anomalies_find_planted_outliers_with_explanations(session):
    rep = detect_anomalies(session.tables["sales"].df, columns=["quantity"])
    top = rep["anomalies"][0]
    assert top["value"] == 900 and "expected range" in top["reason"]
    assert rep["columns"][0]["flagged"] >= 3


def test_anomalies_grouped_and_methods(session):
    df = session.tables["sales"].df
    assert detect_anomalies(df, columns=["revenue"], group_by="region", method="mad")["group_by"] == "region"
    assert detect_anomalies(df, columns=["revenue"], method="zscore")["method"] == "zscore"
    with pytest.raises(ValueError):
        detect_anomalies(df, columns=["nope"])
    with pytest.raises(ValueError):
        detect_anomalies(df, method="magic")


def test_quality_report_catches_planted_issues(session):
    q = quality_report(session.tables["sales"].df, "sales")
    issues = {i["issue"] for i in q["issues"]}
    assert {"Duplicate rows", "Missing values", "Negative values", "Inconsistent categories"} <= issues
    assert 0 <= q["score"] < 100


def test_forecast_trend_and_seasonality():
    dates = [f"{2023 + i // 12}-{i % 12 + 1:02d}-01" for i in range(36)]
    vals = [100 + 5 * i + (20 if i % 12 == 11 else 0) for i in range(36)]
    fc = forecast_series(dates, vals, periods=3)
    assert fc["direction"] == "upward" and "seasonality" in fc["method"] and len(fc["forecast"]) == 3
    assert fc["forecast"][0]["lower"] <= fc["forecast"][0]["value"] <= fc["forecast"][0]["upper"]
    with pytest.raises(ValueError):
        forecast_series(dates[:3], vals[:3])


def test_charts():
    cols, rows = ["region", "rev"], [["N", 5], ["S", 3], [None, 1]]
    bar = build_chart("bar", cols, rows, "region", "rev")
    assert bar["labels"] == ["N", "S", "(missing)"]
    pie = build_chart("pie", cols, rows, "REGION", ["rev"])  # case-insensitive column resolution
    assert pie["datasets"][0]["data"][0] == 5
    sc = build_chart("scatter", ["a", "b"], [[1, 2], [3, 4]], "a", "b")
    assert sc["datasets"][0]["data"][0] == {"x": 1, "y": 2}
    with pytest.raises(ChartError):
        build_chart("bar", cols, rows, "nope", "rev")
    with pytest.raises(ChartError):
        build_chart("bar", cols, [], "region", "rev")
    with pytest.raises(ChartError):
        build_chart("radar", cols, rows, "region", "rev")


def test_dashboard_and_schema(session):
    d = build_dashboard(session.tables)
    sales = next(s for s in d["sections"] if s["table"] == "sales")
    assert len(sales["charts"]) >= 3 and sales["kpis"][0]["value"] > 2000
    assert "TABLE sales" in schema_prompt(session.tables)


def test_dashboard_does_not_treat_calendar_year_as_a_business_measure():
    class Table:
        df = pd.DataFrame({"year": [2024, 2025, 2026], "industry": ["A", "B", "A"], "value": [10, 30, 20]})

    dashboard = build_dashboard({"survey": Table()})
    section = dashboard["sections"][0]
    labels = [k["label"] for k in section["kpis"]]
    assert "Average year" not in labels
    assert "Average value" in labels
    assert all("year by" not in chart["title"] for chart in section["charts"])


def test_enterprise_survey_dashboard_uses_one_hierarchy_level_per_metric():
    rows = []
    for year, total, small, other in [(2024, 100, 60, 40), (2025, 120, 75, 45)]:
        rows.extend([
            {"year": year, "industry_code_anzsic": "all", "industry_name_anzsic": "All Industries", "rme_size_grp": "j_Grand_Total", "variable": "Activity unit", "unit": "COUNT", "value": total},
            {"year": year, "industry_code_anzsic": "A", "industry_name_anzsic": "Agriculture", "rme_size_grp": "a_0", "variable": "Activity unit", "unit": "COUNT", "value": small},
            {"year": year, "industry_code_anzsic": "B", "industry_name_anzsic": "Mining", "rme_size_grp": "b_1-5", "variable": "Activity unit", "unit": "COUNT", "value": other},
            {"year": year, "industry_code_anzsic": "A", "industry_name_anzsic": "Agriculture", "rme_size_grp": "i_Industry_Total", "variable": "Activity unit", "unit": "COUNT", "value": small},
            {"year": year, "industry_code_anzsic": "B", "industry_name_anzsic": "Mining", "rme_size_grp": "i_Industry_Total", "variable": "Activity unit", "unit": "COUNT", "value": other},
        ])

    class Table:
        df = pd.DataFrame(rows)

    section = build_dashboard({"survey": Table()})["sections"][0]
    assert {k["label"] for k in section["kpis"]} >= {"Latest year", "Activity units"}
    assert next(k["value"] for k in section["kpis"] if k["label"] == "Activity units") == 120
    size_chart = next(c for c in section["charts"] if c["title"].startswith("Activity units by size"))
    assert size_chart["datasets"][0]["data"] == [75, 45]
    assert size_chart["labels"] == ["0 employees", "1–5 employees"]
