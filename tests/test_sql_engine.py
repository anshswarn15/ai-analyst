import pytest

from app.core.sql_engine import SQLEngine, SQLExecutionError, SQLValidationError


def _engine(session):
    return session.engine


def test_basic_query_and_cache(session):
    e = _engine(session)
    r1 = e.query("SELECT region, SUM(revenue) AS rev FROM sales GROUP BY region ORDER BY rev DESC")
    assert r1.columns == ["region", "rev"] and r1.rows[0][1] >= r1.rows[1][1]
    assert e.query("SELECT region, SUM(revenue) AS rev FROM sales GROUP BY region ORDER BY rev DESC").cached


def test_blocks_writes_and_multi_statements(session):
    e = _engine(session)
    for bad in ["DROP TABLE sales", "DELETE FROM sales", "UPDATE sales SET revenue=0",
                "SELECT 1; SELECT 2", "PRAGMA table_info(sales)", "ATTACH DATABASE 'x' AS y", ""]:
        with pytest.raises((SQLValidationError, SQLExecutionError)):
            e.query(bad)
    # data still intact
    assert e.query("SELECT COUNT(*) FROM sales").rows[0][0] > 2000


def test_cte_insert_is_denied_by_authorizer(session):
    with pytest.raises(SQLExecutionError):
        session.engine.query("WITH x AS (SELECT 1) INSERT INTO sales SELECT * FROM sales")


def test_helpers_and_errors(session):
    e = _engine(session)
    r = e.query("SELECT DATE_TRUNC('month', order_date) m, MEDIAN(revenue), STDEV(revenue) FROM sales GROUP BY 1 LIMIT 2")
    assert r.rows[0][0].endswith("-01")
    with pytest.raises(SQLExecutionError):
        e.query("SELECT nope FROM sales")


def test_row_limit_truncates():
    from app.core.ingestion import load_csv
    e = SQLEngine(row_limit=5)
    t = load_csv("n.csv", ("a\n" + "\n".join(str(i) for i in range(50))).encode(), max_bytes=10**6, max_rows=10**6)
    e.register("n", t.df)
    r = e.query("SELECT a FROM n")
    assert r.row_count == 5 and r.truncated


def test_drop_table(session):
    session.remove_table("products")
    with pytest.raises(SQLExecutionError):
        session.engine.query("SELECT * FROM products")
