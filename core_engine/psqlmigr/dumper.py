import difflib
import re
from pathlib import Path
from typing import Dict, Any, List, Optional
from psqlmigr.inspector import PostgresInspector

class SchemaDumper:
    def __init__(self, db_url: str, output_dir: Path):
        self.inspector = PostgresInspector(db_url)
        self.output_dir = output_dir

    def fetch_db_schema_files(self) -> Dict[str, str]:
        """
        Inspects the PostgreSQL database and returns an in-memory map of
        relative POSIX paths (e.g. 'public/tables/users.sql') to DDL content.
        """
        db_files: Dict[str, str] = {}
        schemas = self.inspector.get_user_schemas()

        if not schemas:
            schemas = ["public"]

        for sname in schemas:
            tables = self.inspector.inspect_tables(sname)
            views = self.inspector.inspect_views(sname)
            routines = self.inspector.inspect_functions_and_procedures(sname)
            indexes = self.inspector.inspect_indexes(sname)
            sequences = self.inspector.inspect_sequences(sname)

            # 0. Sequences
            if sequences:
                for seq in sequences:
                    rel_path = f"{sname}/sequences/{seq['name']}.sql"
                    ddl = f"CREATE SEQUENCE IF NOT EXISTS {sname}.{seq['name']};\n"
                    db_files[rel_path] = ddl

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

            # 1. Tables (Master Table + Child Partitions + Table Indexes in ONE file)
            if main_tables or child_tables:
                processed_child_names = set()

                for tbl in main_tables:
                    tname = tbl["name"]
                    rel_path = f"{sname}/tables/{tname}.sql"

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
                    db_files[rel_path] = full_ddl

                # Orphaned child partitions (if parent is outside schema)
                for child in child_tables:
                    if child["name"] not in processed_child_names:
                        rel_path = f"{sname}/tables/{child['name']}.sql"
                        full_ddl = self._generate_table_ddl(sname, child)
                        db_files[rel_path] = full_ddl

            # 2. Views
            if views:
                for vw in views:
                    rel_path = f"{sname}/views/{vw['name']}.sql"
                    ddl = f"CREATE OR REPLACE VIEW {sname}.{vw['name']} AS\n{vw['definition']};\n"
                    db_files[rel_path] = ddl

            # 3. Functions vs Procedures
            if routines:
                for r in routines:
                    if r["kind"] == "p":
                        rel_path = f"{sname}/procedures/{r['name']}.sql"
                    else:
                        rel_path = f"{sname}/functions/{r['name']}.sql"

                    ddl = f"{r['definition']};\n"
                    db_files[rel_path] = ddl

            # 4. Standalone Indexes (e.g. on views / materialized views)
            if standalone_indexes:
                for idx in standalone_indexes:
                    rel_path = f"{sname}/indexes/{idx['name']}.sql"
                    ddl = f"{idx['definition']};\n"
                    db_files[rel_path] = ddl

        return db_files

    def dump_schema(self, clean: bool = True) -> List[Path]:
        written_files: List[Path] = []

        if clean and self.output_dir.exists():
            import shutil
            for child in self.output_dir.iterdir():
                if child.is_dir():
                    shutil.rmtree(child)
                elif child.is_file():
                    child.unlink()

        db_files = self.fetch_db_schema_files()

        for rel_path, ddl in db_files.items():
            file_path = self.output_dir / Path(rel_path)
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(ddl, encoding="utf-8")
            written_files.append(file_path)

        return written_files

    @staticmethod
    def _normalize_sql(sql: str) -> str:
        return "\n".join(line.rstrip() for line in sql.replace("\r\n", "\n").strip().splitlines()) + "\n"

    def diff_schema(self) -> List[Dict[str, Any]]:
        """
        Compares live PostgreSQL database objects against local DDL files in self.output_dir.
        Returns a list of difference dicts with keys:
        - rel_path: str (e.g. 'public/tables/users.sql')
        - status: 'ADDED_IN_DB' | 'MODIFIED' | 'DELETED_IN_DB'
        - db_ddl: Optional[str]
        - local_ddl: Optional[str]
        - diff: str (unified diff)
        """
        db_files = self.fetch_db_schema_files()

        local_files: Dict[str, str] = {}
        if self.output_dir.exists():
            for f in self.output_dir.glob("**/*.sql"):
                if f.is_file():
                    rel_path = f.relative_to(self.output_dir).as_posix()
                    local_files[rel_path] = f.read_text(encoding="utf-8")

        all_paths = sorted(set(db_files.keys()) | set(local_files.keys()))
        diffs: List[Dict[str, Any]] = []

        for rel_path in all_paths:
            in_db = rel_path in db_files
            in_local = rel_path in local_files

            if in_db and not in_local:
                db_ddl = db_files[rel_path]
                diff_lines = difflib.unified_diff(
                    [],
                    self._normalize_sql(db_ddl).splitlines(keepends=True),
                    fromfile=f"local/{rel_path} (missing)",
                    tofile=f"db/{rel_path}",
                )
                diffs.append({
                    "rel_path": rel_path,
                    "status": "ADDED_IN_DB",
                    "db_ddl": db_ddl,
                    "local_ddl": None,
                    "diff": "".join(diff_lines),
                })
            elif in_local and not in_db:
                local_ddl = local_files[rel_path]
                diff_lines = difflib.unified_diff(
                    self._normalize_sql(local_ddl).splitlines(keepends=True),
                    [],
                    fromfile=f"local/{rel_path}",
                    tofile=f"db/{rel_path} (missing in DB)",
                )
                diffs.append({
                    "rel_path": rel_path,
                    "status": "DELETED_IN_DB",
                    "db_ddl": None,
                    "local_ddl": local_ddl,
                    "diff": "".join(diff_lines),
                })
            else:
                db_ddl = db_files[rel_path]
                local_ddl = local_files[rel_path]
                norm_db = self._normalize_sql(db_ddl)
                norm_local = self._normalize_sql(local_ddl)

                if norm_db != norm_local:
                    diff_lines = difflib.unified_diff(
                        norm_local.splitlines(keepends=True),
                        norm_db.splitlines(keepends=True),
                        fromfile=f"local/{rel_path}",
                        tofile=f"db/{rel_path}",
                    )
                    diffs.append({
                        "rel_path": rel_path,
                        "status": "MODIFIED",
                        "db_ddl": db_ddl,
                        "local_ddl": local_ddl,
                        "diff": "".join(diff_lines),
                    })

        return diffs

    def apply_selected_diffs(
        self,
        selected_paths: List[str],
        diffs: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, List[str]]:
        """
        Applies the user-selected differences from the database to the local schemas/ directory.
        - ADDED_IN_DB / MODIFIED: writes the database DDL into schemas/<rel_path>
        - DELETED_IN_DB: removes schemas/<rel_path> from the local project
        """
        if diffs is None:
            diffs = self.diff_schema()

        selected_norm = {p.replace("\\", "/").strip("/") for p in selected_paths}
        written: List[str] = []
        deleted: List[str] = []

        for item in diffs:
            rel_path = item["rel_path"]
            if rel_path not in selected_norm:
                continue

            target_file = self.output_dir / Path(rel_path)
            status = item["status"]

            if status in ("ADDED_IN_DB", "MODIFIED") and item.get("db_ddl") is not None:
                target_file.parent.mkdir(parents=True, exist_ok=True)
                target_file.write_text(item["db_ddl"], encoding="utf-8")
                written.append(rel_path)
            elif status == "DELETED_IN_DB":
                if target_file.exists():
                    target_file.unlink()
                    deleted.append(rel_path)

        return {"written": written, "deleted": deleted}

    def _generate_table_ddl(self, schema_name: str, table_info: Dict[str, Any]) -> str:
        # Check if any column default contains nextval(...) and ensure sequence creation DDL is included
        required_sequences = []
        for col in table_info.get("columns", []):
            cdef = col.get("default")
            if cdef and "nextval" in str(cdef).lower():
                matches = re.findall(r"nextval\(\s*['\"]([^'\"]+)['\"]", str(cdef), re.IGNORECASE)
                for m in matches:
                    raw_seq = m.split("::")[0].strip()
                    full_seq = raw_seq if "." in raw_seq else f"{schema_name}.{raw_seq}"
                    if full_seq not in required_sequences:
                        required_sequences.append(full_seq)

        seq_header = ""
        if required_sequences:
            seq_lines = [f"CREATE SEQUENCE IF NOT EXISTS {seq};" for seq in required_sequences]
            seq_header = "\n".join(seq_lines) + "\n\n"

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
            return seq_header + "\n".join(lines)

        # Case B & C: Master Partitioned Table or Regular Table
        lines = [f"CREATE TABLE IF NOT EXISTS {schema_name}.{table_info['name']} ("]
        col_defs = []

        for col in table_info.get("columns", []):
            null_str = "" if col["nullable"] else " NOT NULL"
            identity_str = f" {col['identity']}" if col.get("identity") else ""
            def_str = f" DEFAULT {col['default']}" if (col.get("default") is not None and not col.get("identity")) else ""
            col_defs.append(f"    {col['name']} {col['type']}{null_str}{identity_str}{def_str}")

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

        return seq_header + "\n".join(lines)
