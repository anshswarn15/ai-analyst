import pytest

from app.core.ingestion import IngestionError, load_csv

KW = dict(max_bytes=1_000_000, max_rows=1000)


def test_rejects_wrong_extension():
    with pytest.raises(IngestionError):
        load_csv("data.xlsx", b"a,b\n1,2", **KW)


def test_rejects_empty_and_binary():
    with pytest.raises(IngestionError):
        load_csv("a.csv", b"   \n", **KW)
    with pytest.raises(IngestionError):
        load_csv("a.csv", b"\x00\x01\x02binary", **KW)


def test_rejects_too_large_and_too_many_rows():
    with pytest.raises(IngestionError):
        load_csv("a.csv", b"a,b\n1,2\n", max_bytes=3, max_rows=10)
    with pytest.raises(IngestionError):
        load_csv("a.csv", b"a\n" + b"1\n" * 20, max_bytes=10_000, max_rows=5)


def test_header_only_rejected():
    with pytest.raises(IngestionError):
        load_csv("a.csv", b"a,b,c\n", **KW)


def test_cleans_names_types_and_delimiter():
    raw = b"Order ID;Amount;Sale Date;Region\n1;$1,200;2024-03-04; north \n2;$300;2024-04-04;South\n"
    t = load_csv("My Sales.csv", raw, **KW)
    assert t.name == "my_sales"
    assert list(t.df.columns) == ["order_id", "amount", "sale_date", "region"]
    assert t.df["amount"].tolist() == [1200, 300]
    assert str(t.df["sale_date"].dtype).startswith("datetime64")
    assert t.df["region"].iloc[0] == "north"  # whitespace stripped


def test_duplicate_and_reserved_column_names():
    t = load_csv("x.csv", b"order,Order,group\n1,2,3\n", **KW)
    assert len(set(t.df.columns)) == 3
    assert "order" not in t.df.columns  # reserved word renamed


def test_ids_with_leading_zeros_stay_text():
    t = load_csv("x.csv", b"code,v\n007,1\n042,2\n", **KW)
    assert t.df["code"].tolist() == ["007", "042"]


def test_unique_table_names():
    t = load_csv("sales.csv", b"a\n1\n", taken_names={"sales"}, **KW)
    assert t.name == "sales_2"


def test_latin1_encoding():
    t = load_csv("x.csv", "name\ncaf\xe9\n".encode("latin-1"), **KW)
    assert t.df["name"].iloc[0] == "café"


def test_ragged_rows_are_skipped_with_warning():
    t = load_csv("x.csv", b"a,b\n1,2\n3,4,5,6\n7,8\n", **KW)
    assert len(t.df) >= 2


def test_drops_nearly_empty_unnamed_spreadsheet_export_columns():
    raw = ("year,value,Unnamed: 9\n" + "2024,10,\n" * 20 + "2026,30,notes\n").encode()
    t = load_csv("survey.csv", raw, **KW)
    assert list(t.df.columns) == ["year", "value"]
    assert "spreadsheet-export" in " ".join(t.warnings)
