"""Validate LLM-generated SQL before it reaches the database.

This is one of three layers. The others are a read-only database role and a
``READ ONLY`` transaction with a statement timeout (see ``analyst.execute``). The guard
parses the SQL into an AST rather than matching keywords, so tricks like comments,
odd casing or a second statement after a semicolon do not get through.
"""

import sqlglot
from sqlglot import exp
from sqlglot.errors import ParseError, TokenError

from app.models import ANALYST_TABLES


class UnsafeSQLError(ValueError):
    pass


FORBIDDEN_NODES = tuple(
    getattr(exp, name)
    for name in (
        "Insert",
        "Update",
        "Delete",
        "Merge",
        "Drop",
        "Create",
        "Alter",
        "TruncateTable",
        "Command",
        "Into",
        "Set",
        "Grant",
        "Copy",
        "Transaction",
        "Commit",
        "Rollback",
    )
    if hasattr(exp, name)
)

# Functions that can read files, sleep, touch other databases or change settings.
FORBIDDEN_FUNCTIONS = {
    "pg_sleep",
    "pg_sleep_for",
    "pg_sleep_until",
    "pg_read_file",
    "pg_read_binary_file",
    "pg_ls_dir",
    "pg_stat_file",
    "lo_import",
    "lo_export",
    "lo_get",
    "dblink",
    "dblink_exec",
    "set_config",
    "current_setting",
    "pg_terminate_backend",
    "pg_cancel_backend",
    "pg_reload_conf",
    "query_to_xml",
    "table_to_xml",
    "database_to_xml",
    "txid_current",
}


def _function_name(node: exp.Func) -> str:
    if isinstance(node, exp.Anonymous):
        return str(node.name).lower()
    return node.sql_name().lower()


def guard_sql(sql: str, max_rows: int) -> str:
    """Return a safe, row-limited version of ``sql`` or raise UnsafeSQLError."""
    cleaned = sql.strip().rstrip(";").strip()
    if not cleaned:
        raise UnsafeSQLError("Empty query")
    try:
        statements = [s for s in sqlglot.parse(cleaned, read="postgres") if s is not None]
    except (ParseError, TokenError) as exc:
        raise UnsafeSQLError(f"Could not parse SQL: {exc}") from exc
    if len(statements) != 1:
        raise UnsafeSQLError("Only a single statement is allowed")
    tree = statements[0]

    if not isinstance(tree, exp.Select | exp.Union | exp.Intersect | exp.Except):
        raise UnsafeSQLError("Only SELECT queries are allowed")
    forbidden = tree.find(*FORBIDDEN_NODES)
    if forbidden is not None:
        raise UnsafeSQLError(f"{type(forbidden).__name__} is not allowed")
    for select in tree.find_all(exp.Select):
        if select.args.get("locks"):
            raise UnsafeSQLError("Row locks are not allowed")

    cte_names = {cte.alias_or_name.lower() for cte in tree.find_all(exp.CTE)}
    for table in tree.find_all(exp.Table):
        name = table.name.lower()
        if not name:
            continue  # e.g. generate_series(...) used as a table
        if table.db and table.db.lower() != "public":
            raise UnsafeSQLError(f"Schema '{table.db}' is not allowed")
        if name not in ANALYST_TABLES and name not in cte_names:
            raise UnsafeSQLError(f"Table '{name}' is not allowed")

    for func in tree.find_all(exp.Func):
        name = _function_name(func)
        if name in FORBIDDEN_FUNCTIONS or name.startswith("pg_"):
            raise UnsafeSQLError(f"Function '{name}' is not allowed")

    return _apply_limit(tree, max_rows).sql(dialect="postgres")


def _apply_limit(tree: exp.Expression, max_rows: int) -> exp.Expression:
    if isinstance(tree, exp.Select):
        limit = tree.args.get("limit")
        current = None
        if limit is not None:
            value = limit.expression
            if isinstance(value, exp.Literal) and value.is_int:
                current = int(value.this)
        if current is None or current > max_rows:
            return tree.limit(max_rows)
        return tree
    # UNION / INTERSECT / EXCEPT: wrap rather than editing each branch.
    return exp.select("*").from_(tree.subquery("q")).limit(max_rows)
