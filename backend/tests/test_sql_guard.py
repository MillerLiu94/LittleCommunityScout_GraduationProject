import unittest
from unittest.mock import patch

from app.tools import query as query_module
from app.tools.sql_guard import SQLValidationError, validate_readonly_sql


class ValidateReadonlySqlTests(unittest.TestCase):
    def test_allows_select_on_allowed_tables(self):
        for sql in (
            "SELECT * FROM cases",
            "SELECT * FROM categories",
            "SELECT * FROM public.cases",
            "WITH x AS (SELECT * FROM cases) SELECT * FROM x",
            "SELECT * FROM information_schema.columns WHERE table_name = 'cases'",
            "SELECT * FROM cases WHERE description LIKE '%漏水%'",
            "SELECT * FROM cases WHERE description LIKE '%nextval(%'",
        ):
            with self.subTest(sql=sql):
                self.assertTrue(validate_readonly_sql(sql))

    def test_rejects_disallowed_tables(self):
        for sql in (
            "SELECT * FROM users",
            "SELECT * FROM pg_catalog.pg_tables",
            "SELECT * FROM cases JOIN users ON cases.author_account = users.account",
        ):
            with self.subTest(sql=sql):
                with self.assertRaises(SQLValidationError):
                    validate_readonly_sql(sql)

    def test_rejects_writes_and_ddl(self):
        for sql in (
            "INSERT INTO cases (description) VALUES ('x')",
            "UPDATE cases SET description = 'x'",
            "DELETE FROM cases",
            "DROP TABLE cases",
            "TRUNCATE cases",
            "ALTER TABLE cases ADD COLUMN x int",
            "CALL do_something()",
            "DO $$ BEGIN DELETE FROM cases; END $$",
            "COPY cases TO '/tmp/x'",
            "SELECT * INTO new_table FROM cases",
            "WITH x AS (INSERT INTO cases (description) VALUES ('x') RETURNING *) SELECT * FROM x",
        ):
            with self.subTest(sql=sql):
                with self.assertRaises(SQLValidationError):
                    validate_readonly_sql(sql)

    def test_rejects_dangerous_functions(self):
        for sql in (
            "SELECT pg_sleep(10)",
            "SELECT setval('s', 1)",
            "SELECT nextval('s')",
            "SELECT set_config('default_transaction_read_only', 'off', false)",
            "SELECT pg_read_file('/etc/passwd')",
            "SELECT query_to_xml('SELECT account FROM users', true, false, '')",
        ):
            with self.subTest(sql=sql):
                with self.assertRaises(SQLValidationError):
                    validate_readonly_sql(sql)

    def test_rejects_locks_and_multiple_statements(self):
        for sql in (
            "SELECT * FROM cases FOR UPDATE",
            "SELECT * FROM cases FOR SHARE",
            "SELECT 1; SELECT 2",
        ):
            with self.subTest(sql=sql):
                with self.assertRaises(SQLValidationError):
                    validate_readonly_sql(sql)


class QueryToolFailClosedTests(unittest.TestCase):
    def test_disabled_without_readonly_engine(self):
        with patch.object(query_module, "readonly_engine", None):
            result = query_module.query_community_database.invoke(
                {"sql_query": "SELECT * FROM cases"}
            )
        self.assertIn("未啟用", result)

    def test_rejects_before_touching_database(self):
        with patch.object(query_module, "readonly_engine", object()):
            result = query_module.query_community_database.invoke(
                {"sql_query": "DELETE FROM cases"}
            )
        self.assertIn("查詢被拒絕", result)


if __name__ == "__main__":
    unittest.main()
