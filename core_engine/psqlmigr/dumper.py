from pathlib import Path
from typing import Dict, Any, List
from psqlmigr.inspector import PostgresInspector

class SchemaDumper:
    def __init__(self, db_url: str, output_dir: Path):
        self.inspector = PostgresInspector(db_url)
        self.output_dir = output_dir

    def dump_schema(self, clean: bool = True) -> List[Path]:
        written_files: List[Path] = []

        if clean and self.output_dir.exists():
            import shutil
            for child in self.output_dir.iterdir():
                if child.is_dir():
                    shutil.rmtree(child)
                elif child.is_file():
                    child.unlink()

        schemas = self.inspector.get_user_schemas()

        if not schemas:
            schemas = ["public"]

        for sname in schemas:
            schema_dir = self.output_dir / sname
            
            tables = self.inspector.inspect_tables(sname)
            views = self.inspector.inspect_views(sname)
            routines = self.inspector.inspect_functions_and_procedures(sname)
            indexes = self.inspector.inspect_indexes(sname)

            # Map child partitions to parent table
            parent_to_children: Dict[str, List[Dict[str, Any]]] = {}
            main_tables: List[Dict[str, Any]] = []
            child_tables: List[Dict[str, Any]] = []

            for tbl in tables:
                if tbl.get("is_partition") and tbl.get("parent_table"):
                    parent_to_children.setdefault(tbl["parent_table"], []).append(tbl)
                    child_tables.append(tbl)
                else:
                    main_tables.append(tbl)

            # Map indexes to table name
            table_indexes: Dict[str, List[Dict[str, Any]]] = {}
            standalone_indexes: List[Dict[str, Any]] = []

            all_table_names = {t["name"] for t in tables}

            for idx in indexes:
                tname = idx.get("table_name")
                if tname in all_table_names:
                    table_indexes.setdefault(tname, []).append(idx)
                else:
                    standalone_indexes.append(idx)

            # 1. Dump Tables (Master Table + Child Partitions + Table Indexes in ONE file)
            if main_tables or child_tables:
                tables_dir = schema_dir / "tables"
                tables_dir.mkdir(parents=True, exist_ok=True)

                processed_child_names = set()

                for tbl in main_tables:
                    tname = tbl["name"]
                    file_path = tables_dir / f"{tname}.sql"
                    
                    ddl_parts = []
                    # Base Table DDL
                    ddl_parts.append(self._generate_table_ddl(sname, tbl))

                    # Child Partitions (if any)
                    children = parent_to_children.get(tname, [])
                    if children:
                        ddl_parts.append("-- Partitions")
                        for child in children:
                            processed_child_names.add(child["name"])
                            ddl_parts.append(self._generate_table_ddl(sname, child))

                    # Collect indexes for main table + child partitions
                    idxs = list(table_indexes.get(tname, []))
                    for child in children:
                        idxs.extend(table_indexes.get(child["name"], []))

                    # Deduplicate indexes by index name
                    seen_idx_names = set()
                    unique_idxs = []
                    for idx_item in idxs:
                        if idx_item["name"] not in seen_idx_names:
                            seen_idx_names.add(idx_item["name"])
                            unique_idxs.append(idx_item)

                    if unique_idxs:
                        ddl_parts.append("-- Indexes")
                        for idx_item in unique_idxs:
                            ddl_parts.append(f"{idx_item['definition']};\n")

                    full_ddl = "\n".join(ddl_parts)
                    file_path.write_text(full_ddl, encoding="utf-8")
                    written_files.append(file_path)

                # Orphaned child partitions (if parent is outside schema)
                for child in child_tables:
                    if child["name"] not in processed_child_names:
                        file_path = tables_dir / f"{child['name']}.sql"
                        full_ddl = self._generate_table_ddl(sname, child)
                        file_path.write_text(full_ddl, encoding="utf-8")
                        written_files.append(file_path)

            # 2. Dump Views
            if views:
                views_dir = schema_dir / "views"
                views_dir.mkdir(parents=True, exist_ok=True)
                for vw in views:
                    file_path = views_dir / f"{vw['name']}.sql"
                    ddl = f"CREATE OR REPLACE VIEW {sname}.{vw['name']} AS\n{vw['definition']};\n"
                    file_path.write_text(ddl, encoding="utf-8")
                    written_files.append(file_path)

            # 3. Dump Functions vs Procedures
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

            # 4. Dump Standalone Indexes (e.g. on views / materialized views)
            if standalone_indexes:
                indexes_dir = schema_dir / "indexes"
                indexes_dir.mkdir(parents=True, exist_ok=True)
                for idx in standalone_indexes:
                    file_path = indexes_dir / f"{idx['name']}.sql"
                    ddl = f"{idx['definition']};\n"
                    file_path.write_text(ddl, encoding="utf-8")
                    written_files.append(file_path)

        return written_files

    def _generate_table_ddl(self, schema_name: str, table_info: Dict[str, Any]) -> str:
        # Case A: Child Partition Table
        if table_info.get("is_partition") and table_info.get("parent_table"):
            parent = table_info["parent_table"]
            part_bound = table_info.get("partition_bound") or ""
            part_by = table_info.get("partition_by")

            lines = [f"CREATE TABLE IF NOT EXISTS {schema_name}.{table_info['name']} PARTITION OF {schema_name}.{parent}"]
            if part_bound:
                lines.append(f"    {part_bound}")
            if part_by:
                lines.append(f"PARTITION BY {part_by}")
            lines[-1] += ";\n"
            return "\n".join(lines)

        # Case B & C: Master Partitioned Table or Regular Table
        lines = [f"CREATE TABLE IF NOT EXISTS {schema_name}.{table_info['name']} ("]
        col_defs = []

        for col in table_info.get("columns", []):
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

        part_by = table_info.get("partition_by")
        if part_by:
            lines.append(f") PARTITION BY {part_by};\n")
        else:
            lines.append(");\n")

        return "\n".join(lines)
