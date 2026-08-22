import pytest
from pathlib import Path
from typer.testing import CliRunner
from psqlmigr.cli import app

runner = CliRunner()

def test_version_command():
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert "psqlmigr-core" in result.stdout

def test_init_command(tmp_path: Path):
    result = runner.invoke(app, ["init", "--dir", str(tmp_path)])
    assert result.exit_code == 0
    assert (tmp_path / "psqlmigr.yaml").exists()
    assert (tmp_path / ".env").exists()
    assert (tmp_path / "schema").exists()
    assert (tmp_path / "migrations").exists()

def test_plan_command(tmp_path: Path, monkeypatch):
    runner.invoke(app, ["init", "--dir", str(tmp_path)])
    monkeypatch.chdir(tmp_path)
    
    # Create sample schema DDL file
    tables_dir = tmp_path / "schema" / "public" / "tables"
    tables_dir.mkdir(parents=True, exist_ok=True)
    (tables_dir / "users.sql").write_text("CREATE TABLE public.users (id INT PRIMARY KEY);", encoding="utf-8")

    result = runner.invoke(app, ["plan", "create_users_table"])
    assert result.exit_code == 0
    
    migrations = list((tmp_path / "migrations").glob("*.sql"))
    assert len(migrations) == 2  # .up.sql and .down.sql

    up_file = [m for m in migrations if m.name.endswith(".up.sql")][0]
    up_content = up_file.read_text(encoding="utf-8")
    assert "CREATE TABLE public.users" in up_content

def test_special_character_password_connection_url(tmp_path: Path, monkeypatch):
    from psqlmigr.config import ConfigManager
    import psycopg.conninfo

    runner.invoke(app, ["init", "--dir", str(tmp_path)])
    monkeypatch.chdir(tmp_path)

    runner.invoke(app, ["set-env", "--host", "localhost", "--port", "5432", "--user", "postgres", "--password", "P@ssw#rd!", "--database", "test_db"])

    cfg_mgr = ConfigManager(tmp_path)
    db_url = cfg_mgr.get_database_url()
    assert db_url is not None
    assert "P%40ssw%23rd%21" in db_url

    parsed = psycopg.conninfo.conninfo_to_dict(db_url)
    assert parsed["password"] == "P@ssw#rd!"
    assert parsed["user"] == "postgres"
    assert parsed["dbname"] == "test_db"

def test_dumper_routing(tmp_path: Path):
    from psqlmigr.dumper import SchemaDumper
    from unittest.mock import MagicMock

    dumper = SchemaDumper("postgresql://postgres:postgres@localhost:5432/test", tmp_path)
    dumper.inspector.get_user_schemas = MagicMock(return_value=["public"])
    dumper.inspector.inspect_tables = MagicMock(return_value=[
        {"name": "users", "relkind": "r", "is_partition": False, "partition_by": None, "partition_bound": None, "parent_table": None, "columns": [{"name": "id", "type": "INT", "nullable": False, "default": None}], "primary_key": ["id"], "foreign_keys": [], "unique_constraints": []}
    ])
    dumper.inspector.inspect_views = MagicMock(return_value=[])
    dumper.inspector.inspect_functions_and_procedures = MagicMock(return_value=[
        {"name": "my_func", "definition": "CREATE FUNCTION my_func() RETURNS void AS $$ $$ LANGUAGE plpgsql", "language": "plpgsql", "kind": "f"},
        {"name": "my_proc", "definition": "CREATE PROCEDURE my_proc() AS $$ $$ LANGUAGE plpgsql", "language": "plpgsql", "kind": "p"}
    ])
    dumper.inspector.inspect_indexes = MagicMock(return_value=[
        {"name": "idx_users_email", "table_name": "users", "definition": "CREATE INDEX idx_users_email ON public.users (email)"}
    ])

    written = dumper.dump_schema()
    
    assert (tmp_path / "public" / "functions" / "my_func.sql").exists()
    assert (tmp_path / "public" / "procedures" / "my_proc.sql").exists()
    
    users_sql = (tmp_path / "public" / "tables" / "users.sql").read_text(encoding="utf-8")
    assert "CREATE TABLE IF NOT EXISTS public.users" in users_sql
    assert "CREATE INDEX idx_users_email ON public.users (email);" in users_sql

def test_partitioned_table_dumper(tmp_path: Path):
    from psqlmigr.dumper import SchemaDumper
    from unittest.mock import MagicMock

    dumper = SchemaDumper("postgresql://postgres:postgres@localhost:5432/test", tmp_path)
    dumper.inspector.get_user_schemas = MagicMock(return_value=["transform"])
    dumper.inspector.inspect_tables = MagicMock(return_value=[
        {
            "name": "measurement",
            "relkind": "p",
            "is_partition": False,
            "partition_by": "RANGE (logdate)",
            "partition_bound": None,
            "parent_table": None,
            "columns": [{"name": "city_id", "type": "INT", "nullable": False, "default": None}, {"name": "logdate", "type": "DATE", "nullable": False, "default": None}],
            "primary_key": ["city_id", "logdate"],
            "foreign_keys": [],
            "unique_constraints": []
        },
        {
            "name": "measurement_y2026m01",
            "relkind": "r",
            "is_partition": True,
            "partition_by": None,
            "partition_bound": "FOR VALUES FROM ('2026-01-01') TO ('2026-02-01')",
            "parent_table": "measurement",
            "columns": [],
            "primary_key": [],
            "foreign_keys": [],
            "unique_constraints": []
        }
    ])
    dumper.inspector.inspect_views = MagicMock(return_value=[])
    dumper.inspector.inspect_functions_and_procedures = MagicMock(return_value=[])
    dumper.inspector.inspect_indexes = MagicMock(return_value=[
        {"name": "idx_measurement_logdate", "table_name": "measurement", "definition": "CREATE INDEX idx_measurement_logdate ON transform.measurement (logdate)"}
    ])

    written = dumper.dump_schema()

    master_sql = (tmp_path / "transform" / "tables" / "measurement.sql").read_text(encoding="utf-8")
    assert "PARTITION BY RANGE (logdate);" in master_sql
    assert "CREATE TABLE IF NOT EXISTS transform.measurement_y2026m01 PARTITION OF transform.measurement" in master_sql
    assert "FOR VALUES FROM ('2026-01-01') TO ('2026-02-01');" in master_sql
    assert "CREATE INDEX idx_measurement_logdate ON transform.measurement (logdate);" in master_sql
