"""LLM 產生的 SQL 進入資料庫前的最後一道靜態檢查。

DB 角色（readonly_user）與連線層的 read-only 設定才是主要防線；這裡負責把
明顯不該出現的語法先擋掉，避免依賴單一防線。
"""

import sqlglot
from sqlglot import exp
from sqlglot.errors import ParseError

_MAX_SQL_LENGTH = 20_000

_ALLOWED_TABLES = frozenset({"cases", "categories"})
_ALLOWED_QUALIFIED_TABLES = frozenset({("information_schema", "columns")})
_ALLOWED_DATABASES = frozenset({"", "public"})

# 即使語法上只是 SELECT，這些函式仍可能造成副作用或資源濫用。
_DENIED_FUNCTIONS = frozenset(
    {
        "pg_sleep",
        "pg_read_file",
        "pg_read_binary_file",
        "pg_ls_dir",
        "pg_stat_file",
        "setval",
        "nextval",
        "set_config",
        "dblink",
        "dblink_exec",
        "lo_import",
        "lo_export",
        "lo_create",
        "lo_unlink",
        "pg_terminate_backend",
        "pg_cancel_backend",
        "pg_reload_conf",
        "pg_rotate_logfile",
        "pg_switch_wal",
        "pg_create_restore_point",
        "pg_promote",
        "pg_drop_replication_slot",
        "pg_create_physical_replication_slot",
        "pg_create_logical_replication_slot",
        "pg_logical_emit_message",
        "pg_notify",
        # 這些函式會把字串當 SQL 執行，可繞過資料表白名單。
        "query_to_xml",
        "query_to_xmlschema",
        "query_to_xml_and_xmlschema",
        "cursor_to_xml",
        "cursor_to_xmlschema",
        "table_to_xml",
        "table_to_xmlschema",
        "table_to_xml_and_xmlschema",
        "schema_to_xml",
        "schema_to_xmlschema",
        "schema_to_xml_and_xmlschema",
        "database_to_xml",
        "database_to_xmlschema",
        "database_to_xml_and_xmlschema",
    }
)

_DENIED_NODES = (
    exp.Command,
    exp.Copy,
    exp.Insert,
    exp.Update,
    exp.Delete,
    exp.Create,
    exp.Drop,
    exp.Alter,
    exp.TruncateTable,
    exp.Merge,
    exp.Grant,
    exp.Revoke,
    exp.Set,
    exp.Show,
    exp.Use,
    exp.Transaction,
    exp.Commit,
    exp.Rollback,
    exp.Describe,
)

_ALLOWED_ROOTS = (exp.Select, exp.Union, exp.Intersect, exp.Except)


class SQLValidationError(ValueError):
    """SQL 不符合唯讀查詢規則。"""


def _function_name(func: exp.Func) -> str:
    name = getattr(func, "name", None)
    if name:
        return str(name).lower()
    try:
        return str(func.sql_name()).lower()
    except Exception:  # pragma: no cover - sqlglot 版本差異的保險
        return str(getattr(func, "key", "")).lower()


def _cte_names(expression: exp.Expression) -> set[str]:
    return {
        str(cte.alias).lower()
        for cte in expression.find_all(exp.CTE)
        if cte.alias
    }


def _check_table(table: exp.Table, cte_names: set[str]) -> None:
    name = (table.name or "").lower()
    database = (table.db or "").lower()
    catalog = (table.catalog or "").lower()

    if catalog:
        raise SQLValidationError(f"不允許查詢其他資料庫：{catalog}")

    if not database and name in cte_names:
        return
    if database in _ALLOWED_DATABASES and name in _ALLOWED_TABLES:
        return
    if (database, name) in _ALLOWED_QUALIFIED_TABLES:
        return

    raise SQLValidationError(f"不允許查詢資料表：{table.sql(dialect='postgres')}")


def validate_readonly_sql(sql_query: str) -> str:
    """驗證 SQL 是否為單一、唯讀、且只碰允許的資料表。

    回傳正規化後的 SQL（不含結尾分號）；不合法時丟 SQLValidationError。
    """
    if not isinstance(sql_query, str):
        raise SQLValidationError("SQL 必須是文字。")

    sql = sql_query.strip()
    if not sql:
        raise SQLValidationError("SQL 不可為空。")
    if len(sql) > _MAX_SQL_LENGTH:
        raise SQLValidationError("SQL 過長，請縮小查詢範圍。")

    try:
        statements = sqlglot.parse(sql, read="postgres")
    except ParseError as exc:
        raise SQLValidationError("SQL 語法無法解析。") from exc

    statements = [statement for statement in statements if statement is not None]
    if len(statements) != 1:
        raise SQLValidationError("一次只能執行一個 SELECT 查詢。")

    expression = statements[0]
    if not isinstance(expression, _ALLOWED_ROOTS):
        raise SQLValidationError("只允許 SELECT 查詢。")

    for node_type in _DENIED_NODES:
        if expression.find(node_type):
            raise SQLValidationError("查詢含有不允許的語法。")

    if expression.find(exp.Into):
        raise SQLValidationError("不允許 SELECT INTO。")
    if expression.find(exp.Lock):
        raise SQLValidationError("不允許 FOR UPDATE / FOR SHARE。")

    normalized = expression.sql(dialect="postgres")

    for func in expression.find_all(exp.Func):
        if _function_name(func) in _DENIED_FUNCTIONS:
            raise SQLValidationError(f"不允許使用函式：{_function_name(func)}")

    cte_names = _cte_names(expression)
    for table in expression.find_all(exp.Table):
        _check_table(table, cte_names)

    return normalized
