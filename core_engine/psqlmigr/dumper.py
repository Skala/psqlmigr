from pathlib import Path
from typing import Dict, Any, List
from psqlmigr.inspector import PostgresInspector

class SchemaDumper:
    def __init__(self, db_url: str, output_dir: Path):
        self.inspector = PostgresInspector(db_url)
        self.output_dir = output_dir

    def dump_schema(self) -> List[Path]:
        written_files: List[Path] = []
        schemas = self.inspector.get_user_schemas()

        if not schemas:
            schemas = ["public"]

        for sname in schemas:
            schema_dir = self.output_dir / sname
            
            # 1. Dump Tables
            tables = self.inspector.inspect_tables(sname)
            if tables:
                tables_dir = schema_dir / "tables"
                tables_dir.mkdir(parents=True, exist_ok=True)
                for tbl in tables:
                    file_path = tables_dir / f"{tbl['name']}.sql"
                    ddl = self._generate_table_ddl(sname, tbl)
                    file_path.write_text(ddl, encoding="utf-8")
                    written_files.append(file_path)

            # 2. Dump Views
            views = self.inspector.inspect_views(sname)
            if views:
                views_dir = schema_dir / "views"
                views_dir.mkdir(parents=True, exist_ok=True)
                for vw in views:
                    file_path = views_dir / f"{vw['name']}.sql"
                    ddl = f"CREATE OR REPLACE VIEW {sname}.{vw['name']} AS\n{vw['definition']};\n"
                    file_path.write_text(ddl, encoding="utf-8")
                    written_files.append(file_path)

            # 3. Dump Functions vs Procedures
            routines = self.inspector.inspect_functions_and_procedures(sname)
            if routines:
                funcs_dir = schema_dir / "functions"
                procs_dir = schema_dir / "procedures"

                for r in routines:
                    if r["kind"] == "p":
                        procs_dir.mkdir(parents=True, exist_ok=True)
                        file_path = procs_dir / f"{r['name']}.sql"
                    else:
                        funcs_dir.mkdir(parents=True, exist_ok=True)
                        file_path = funcs_dir / f"{r['name']}.sql"

                    ddl = f"{r['definition']};\n"
                    file_path.write_text(ddl, encoding="utf-8")
                    written_files.append(file_path)

            # 4. Dump Indexes
            indexes = self.inspector.inspect_indexes(sname)
            if indexes:
                indexes_dir = schema_dir / "indexes"
                indexes_dir.mkdir(parents=True, exist_ok=True)
                for idx in indexes:
                    file_path = indexes_dir / f"{idx['name']}.sql"
                    ddl = f"{idx['definition']};\n"
                    file_path.write_text(ddl, encoding="utf-8")
                    written_files.append(file_path)

        return written_files

    def _generate_table_ddl(self, schema_name: str, table_info: Dict[str, Any]) -> str:
        lines = [f"CREATE TABLE IF NOT EXISTS {schema_name}.{table_info['name']} ("]
        col_defs = []

        for col in table_info["columns"]:
            null_str = "" if col["nullable"] else " NOT NULL"
            def_str = f" DEFAULT {col['default']}" if col["default"] is not None else ""
            col_defs.append(f"    {col['name']} {col['type']}{null_str}{def_str}")

        if table_info.get("primary_key"):
            pk_str = ", ".join(table_info["primary_key"])
            col_defs.append(f"    PRIMARY KEY ({pk_str})")

        for fk in table_info.get("foreign_keys", []):
            col_defs.append(
                f"    CONSTRAINT {fk['constraint_name']} FOREIGN KEY ({fk['column']}) "
                f"REFERENCES {fk['foreign_schema']}.{fk['foreign_table']}({fk['foreign_column']})"
            )

        for uq in table_info.get("unique_constraints", []):
            cols_str = ", ".join(uq["columns"])
            col_defs.append(f"    CONSTRAINT {uq['constraint_name']} UNIQUE ({cols_str})")

        lines.append(",\n".join(col_defs))
        lines.append(");\n")
        return "\n".join(lines)
