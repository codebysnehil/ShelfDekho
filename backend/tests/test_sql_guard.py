import pytest

from app.services.sql_guard import UnsafeSQLError, guard_sql


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT * FROM stores",
        "select name from STORES where city ilike '%pune%'",
        "WITH t AS (SELECT store_id, SUM(revenue) r FROM daily_sales GROUP BY 1) SELECT * FROM t",
        "SELECT code FROM stores UNION SELECT sku FROM products",
        "SELECT gs::date FROM generate_series(DATE '2026-01-01', DATE '2026-02-01', interval '1 week') gs",
        "SELECT * FROM public.products",
    ],
)
def test_allows_read_queries(sql: str) -> None:
    assert "LIMIT" in guard_sql(sql, max_rows=200).upper()


@pytest.mark.parametrize(
    ("sql", "reason"),
    [
        ("DROP TABLE stores", "SELECT"),
        ("DELETE FROM daily_sales", "SELECT"),
        ("UPDATE products SET unit_price = 0", "SELECT"),
        ("INSERT INTO stores (code) VALUES ('X')", "SELECT"),
        ("SELECT 1; DROP TABLE stores", "single statement"),
        ("SELECT * FROM stores; -- harmless?\nDELETE FROM stores", "single statement"),
        ("SELECT * INTO backup FROM stores", "Into"),
        ("SELECT * FROM ai_query_log", "ai_query_log"),
        ("SELECT * FROM pg_catalog.pg_user", "pg_catalog"),
        ("SELECT * FROM information_schema.tables", "information_schema"),
        ("SELECT pg_sleep(30)", "pg_sleep"),
        ("SELECT pg_read_file('/etc/passwd')", "pg_read_file"),
        ("SELECT current_setting('server_version')", "current_setting"),
        ("SELECT * FROM stores FOR UPDATE", "locks"),
        ("WITH x AS (DELETE FROM stores RETURNING *) SELECT * FROM x", "Delete"),
        ("", "Empty"),
    ],
)
def test_blocks_unsafe_queries(sql: str, reason: str) -> None:
    with pytest.raises(UnsafeSQLError, match=reason):
        guard_sql(sql, max_rows=200)


def test_adds_limit_when_missing() -> None:
    assert guard_sql("SELECT * FROM stores", 50).endswith("LIMIT 50")


def test_caps_excessive_limit() -> None:
    assert guard_sql("SELECT * FROM stores LIMIT 100000", 50).endswith("LIMIT 50")


def test_keeps_smaller_limit() -> None:
    assert guard_sql("SELECT * FROM stores LIMIT 5", 50).endswith("LIMIT 5")


def test_wraps_set_operations() -> None:
    sql = guard_sql("SELECT code FROM stores UNION ALL SELECT sku FROM products", 10)
    assert sql.startswith("SELECT * FROM (") and sql.endswith("LIMIT 10")
