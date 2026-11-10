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
    assert (tmp_path / "schemas").exists()
    assert (tmp_path / "migrations" / "up").exists()
    assert (tmp_path / "migrations" / "down").exists()

def test_plan_command(tmp_path: Path, monkeypatch):
    runner.invoke(app, ["init", "--dir", str(tmp_path)])
    monkeypatch.chdir(tmp_path)
    
    # Create sample schema DDL file
    tables_dir = tmp_path / "schemas" / "public" / "tables"
    tables_dir.mkdir(parents=True, exist_ok=True)
    (tables_dir / "users.sql").write_text("CREATE TABLE public.users (id INT PRIMARY KEY);", encoding="utf-8")

    result = runner.invoke(app, ["plan", "create_users_table"])
    assert result.exit_code == 0
    
    up_files = list((tmp_path / "migrations" / "up").glob("*.sql"))
    down_files = list((tmp_path / "migrations" / "down").glob("*.sql"))
    assert len(up_files) == 1
    assert len(down_files) == 1
    assert up_files[0].name.startswith("v0.1.0_")

    up_content = up_files[0].read_text(encoding="utf-8")
    assert "-- Project Version   : 0.1.0" in up_content
    assert "CREATE TABLE public.users" in up_content

    down_content = down_files[0].read_text(encoding="utf-8")
    assert "DROP TABLE IF EXISTS public.users CASCADE;" in down_content

    # Second migration test (auto-bump to 0.1.1)
    result2 = runner.invoke(app, ["plan", "add_indexes"])
    assert result2.exit_code == 0
    up_files2 = sorted(list((tmp_path / "migrations" / "up").glob("*.sql")))
    assert len(up_files2) == 2
    assert up_files2[1].name.startswith("v0.1.1_")

def test_remove_migration_command(tmp_path: Path, monkeypatch):
    runner.invoke(app, ["init", "--dir", str(tmp_path)])
    monkeypatch.chdir(tmp_path)
    
    runner.invoke(app, ["plan", "temp_migration"])
    up_files = list((tmp_path / "migrations" / "up").glob("*.sql"))
    assert len(up_files) == 1

    version_prefix = up_files[0].name.split("_")[0]
    rm_res = runner.invoke(app, ["remove-migration", version_prefix])
    assert rm_res.exit_code == 0
    assert not list((tmp_path / "migrations" / "up").glob("*.sql"))
    assert not list((tmp_path / "migrations" / "down").glob("*.sql"))

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
    dumper.inspector.inspect_sequences = MagicMock(return_value=[])

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
    dumper.inspector.inspect_sequences = MagicMock(return_value=[])

    written = dumper.dump_schema()

    master_sql = (tmp_path / "transform" / "tables" / "measurement.sql").read_text(encoding="utf-8")
    assert "PARTITION BY RANGE (logdate);" in master_sql
    assert "CREATE TABLE IF NOT EXISTS transform.measurement_y2026m01 PARTITION OF transform.measurement" in master_sql

def test_sequence_handling(tmp_path: Path, monkeypatch):
    runner.invoke(app, ["init", "--dir", str(tmp_path)])
    monkeypatch.chdir(tmp_path)

    seq_dir = tmp_path / "schemas" / "bronze" / "sequences"
    tbl_dir = tmp_path / "schemas" / "bronze" / "tables"
    seq_dir.mkdir(parents=True, exist_ok=True)
    tbl_dir.mkdir(parents=True, exist_ok=True)

    (seq_dir / "nbp_rates_id_seq.sql").write_text("CREATE SEQUENCE IF NOT EXISTS bronze.nbp_rates_id_seq;", encoding="utf-8")
    (tbl_dir / "nbp_rates.sql").write_text("CREATE TABLE bronze.nbp_rates (id BIGINT DEFAULT nextval('bronze.nbp_rates_id_seq'::regclass));", encoding="utf-8")

    from psqlmigr.generator import MigrationGenerator
    up_sql = MigrationGenerator.read_all_schema_sql(tmp_path / "schemas")
    down_sql = MigrationGenerator.generate_down_sql_from_schema(tmp_path / "schemas")

    seq_pos = up_sql.find("CREATE SEQUENCE IF NOT EXISTS bronze.nbp_rates_id_seq")
    tbl_pos = up_sql.find("CREATE TABLE bronze.nbp_rates")
    assert seq_pos != -1
    assert tbl_pos != -1
    assert seq_pos < tbl_pos

    assert "DROP SEQUENCE IF EXISTS bronze.nbp_rates_id_seq CASCADE;" in down_sql
    assert "DROP TABLE IF EXISTS bronze.nbp_rates CASCADE;" in down_sql

def test_dumper_extracts_nextval_sequences(tmp_path: Path):
    from psqlmigr.dumper import SchemaDumper
    from unittest.mock import MagicMock

    dumper = SchemaDumper("postgresql://user:pass@localhost:5432/db", tmp_path / "schemas")
    dumper.inspector.get_user_schemas = MagicMock(return_value=["bronze"])
    dumper.inspector.inspect_tables = MagicMock(return_value=[
        {
            "name": "nbp_rates",
            "relkind": "r",
            "is_partition": False,
            "columns": [{"name": "id", "type": "BIGINT", "nullable": False, "default": "nextval('bronze.nbp_rates_id_seq'::regclass)"}],
            "primary_key": ["id"],
            "foreign_keys": [],
            "unique_constraints": []
        }
    ])
    dumper.inspector.inspect_views = MagicMock(return_value=[])
    dumper.inspector.inspect_functions_and_procedures = MagicMock(return_value=[])
    dumper.inspector.inspect_indexes = MagicMock(return_value=[])
    dumper.inspector.inspect_sequences = MagicMock(return_value=[])

    written = dumper.dump_schema()
    tbl_sql = (tmp_path / "schemas" / "bronze" / "tables" / "nbp_rates.sql").read_text(encoding="utf-8")
    assert "CREATE SEQUENCE IF NOT EXISTS bronze.nbp_rates_id_seq;" in tbl_sql
    assert "CREATE TABLE IF NOT EXISTS bronze.nbp_rates" in tbl_sql

def test_inspect_indexes_excludes_constraints():
    from psqlmigr.inspector import PostgresInspector
    inspector = PostgresInspector("postgresql://user:pass@localhost:5432/db")
    import inspect
    source = inspect.getsource(inspector.inspect_indexes)
    assert "c.conindid = idx.indexrelid" in source

def test_topological_view_dependency_ordering(tmp_path: Path):
    from psqlmigr.generator import MigrationGenerator

    schema_dir = tmp_path / "schemas"
    views_dir = schema_dir / "monitoring" / "views"
    views_dir.mkdir(parents=True, exist_ok=True)

    # v_etl_summary comes BEFORE v_etl_runs alphabetically
    (views_dir / "v_etl_summary.sql").write_text(
        "CREATE VIEW monitoring.v_etl_summary AS SELECT * FROM monitoring.v_etl_runs r;",
        encoding="utf-8"
    )
    (views_dir / "v_etl_runs.sql").write_text(
        "CREATE VIEW monitoring.v_etl_runs AS SELECT 1 AS id;",
        encoding="utf-8"
    )

    combined_sql = MigrationGenerator.read_all_schema_sql(schema_dir)
    pos_runs = combined_sql.find("monitoring.v_etl_runs")
    pos_summary = combined_sql.find("monitoring.v_etl_summary")

    assert pos_runs < pos_summary

def test_diff_and_selective_sync(tmp_path: Path):
    from psqlmigr.dumper import SchemaDumper
    from unittest.mock import MagicMock

    schemas_dir = tmp_path / "schemas"
    pub_tables = schemas_dir / "public" / "tables"
    pub_tables.mkdir(parents=True, exist_ok=True)

    # Local existing modified file & local-only file
    (pub_tables / "users.sql").write_text(
        "CREATE TABLE IF NOT EXISTS public.users (\n    id INT NOT NULL\n);\n",
        encoding="utf-8"
    )
    (pub_tables / "obsolete_logs.sql").write_text(
        "CREATE TABLE IF NOT EXISTS public.obsolete_logs (\n    id INT NOT NULL\n);\n",
        encoding="utf-8"
    )

    dumper = SchemaDumper("postgresql://postgres:postgres@localhost:5432/test", schemas_dir)
    dumper.inspector.get_user_schemas = MagicMock(return_value=["public"])
    dumper.inspector.inspect_tables = MagicMock(return_value=[
        {
            "name": "users",
            "relkind": "r",
            "is_partition": False,
            "partition_by": None,
            "partition_bound": None,
            "parent_table": None,
            "columns": [
                {"name": "id", "type": "INT", "nullable": False, "default": None},
                {"name": "email", "type": "TEXT", "nullable": True, "default": None}
            ],
            "primary_key": ["id"],
            "foreign_keys": [],
            "unique_constraints": []
        },
        {
            "name": "orders",
            "relkind": "r",
            "is_partition": False,
            "partition_by": None,
            "partition_bound": None,
            "parent_table": None,
            "columns": [{"name": "id", "type": "INT", "nullable": False, "default": None}],
            "primary_key": ["id"],
            "foreign_keys": [],
            "unique_constraints": []
        }
    ])
    dumper.inspector.inspect_views = MagicMock(return_value=[])
    dumper.inspector.inspect_functions_and_procedures = MagicMock(return_value=[])
    dumper.inspector.inspect_indexes = MagicMock(return_value=[])
    dumper.inspector.inspect_sequences = MagicMock(return_value=[])

    diffs = dumper.diff_schema()
    diff_map = {d["rel_path"]: d for d in diffs}

    assert len(diffs) == 3
    assert diff_map["public/tables/orders.sql"]["status"] == "ADDED_IN_DB"
    assert diff_map["public/tables/users.sql"]["status"] == "MODIFIED"
    assert "+    email TEXT" in diff_map["public/tables/users.sql"]["diff"]
    assert diff_map["public/tables/obsolete_logs.sql"]["status"] == "DELETED_IN_DB"

    # Selectively apply ONLY 'orders.sql' and 'users.sql', leaving 'obsolete_logs.sql' untouched
    applied = dumper.apply_selected_diffs(
        ["public/tables/orders.sql", "public/tables/users.sql"],
        diffs=diffs
    )
    assert set(applied["written"]) == {"public/tables/orders.sql", "public/tables/users.sql"}
    assert applied["deleted"] == []
    assert (pub_tables / "orders.sql").exists()
    assert "email TEXT" in (pub_tables / "users.sql").read_text(encoding="utf-8")
    assert (pub_tables / "obsolete_logs.sql").exists()

    # Now selectively apply deletion of 'obsolete_logs.sql'
    applied2 = dumper.apply_selected_diffs(["public/tables/obsolete_logs.sql"])
    assert applied2["deleted"] == ["public/tables/obsolete_logs.sql"]
    assert not (pub_tables / "obsolete_logs.sql").exists()
    assert dumper.diff_schema() == []

def test_identity_numeric_precision_and_index_if_not_exists(tmp_path: Path):
    from psqlmigr.dumper import SchemaDumper
    from psqlmigr.inspector import PostgresInspector
    from unittest.mock import MagicMock

    assert PostgresInspector._ensure_index_if_not_exists(
        "CREATE INDEX idx_test ON bronze.t USING btree (id)"
    ) == "CREATE INDEX IF NOT EXISTS idx_test ON bronze.t USING btree (id)"
    assert PostgresInspector._ensure_index_if_not_exists(
        "CREATE UNIQUE INDEX idx_uniq ON bronze.t USING btree (id)"
    ) == "CREATE UNIQUE INDEX IF NOT EXISTS idx_uniq ON bronze.t USING btree (id)"

    schemas_dir = tmp_path / "schemas"
    dumper = SchemaDumper("postgresql://postgres:postgres@localhost:5432/test", schemas_dir)
    dumper.inspector.get_user_schemas = MagicMock(return_value=["bronze"])
    dumper.inspector.inspect_tables = MagicMock(return_value=[
        {
            "name": "optima_asr_bnkdokelem",
            "relkind": "r",
            "is_partition": False,
            "partition_by": None,
            "partition_bound": None,
            "parent_table": None,
            "columns": [
                {"name": "etl_id", "type": "BIGINT", "nullable": False, "default": None, "identity": "GENERATED ALWAYS AS IDENTITY"},
                {"name": "bde_kwota1", "type": "NUMERIC(15,2)", "nullable": False, "default": None, "identity": None},
            ],
            "primary_key": ["etl_id"],
            "foreign_keys": [],
            "unique_constraints": []
        }
    ])
    dumper.inspector.inspect_views = MagicMock(return_value=[])
    dumper.inspector.inspect_functions_and_procedures = MagicMock(return_value=[])
    dumper.inspector.inspect_indexes = MagicMock(return_value=[])
    dumper.inspector.inspect_sequences = MagicMock(return_value=[])

    dumper.dump_schema()
    tbl_sql = (schemas_dir / "bronze" / "tables" / "optima_asr_bnkdokelem.sql").read_text(encoding="utf-8")
    assert "etl_id BIGINT NOT NULL GENERATED ALWAYS AS IDENTITY" in tbl_sql
    assert "bde_kwota1 NUMERIC(15,2) NOT NULL" in tbl_sql

    # Default identity parameters -> concise clause
    assert PostgresInspector._build_identity_clause(
        "bigint", "ALWAYS", "1", "1", "1", "9223372036854775807", "NO"
    ) == "GENERATED ALWAYS AS IDENTITY"

    # Non-default INCREMENT 2 and START 973 -> explicit options included
    assert PostgresInspector._build_identity_clause(
        "bigint", "ALWAYS", "2", "973", "1", "9223372036854775807", "NO"
    ) == "GENERATED ALWAYS AS IDENTITY ( INCREMENT 2 START 973 )"


