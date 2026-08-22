from datetime import datetime, timezone
from pathlib import Path
from typing import Tuple, Optional

class MigrationGenerator:
    def __init__(self, migrations_dir: Path):
        self.migrations_dir = migrations_dir
        self.up_dir = migrations_dir / "up"
        self.down_dir = migrations_dir / "down"
        self.up_dir.mkdir(parents=True, exist_ok=True)
        self.down_dir.mkdir(parents=True, exist_ok=True)

    def generate_migration(
        self,
        name: str,
        up_sql: str = "-- Migration UP SQL statements\n",
        down_sql: str = "-- Migration DOWN SQL statements\n"
    ) -> Tuple[Path, Path]:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        clean_name = name.strip().lower().replace(" ", "_")
        if not clean_name:
            clean_name = "migration"

        filename = f"{timestamp}_{clean_name}.sql"

        up_file_path = self.up_dir / filename
        down_file_path = self.down_dir / filename

        up_file_path.write_text(up_sql, encoding="utf-8")
        down_file_path.write_text(down_sql, encoding="utf-8")

        return up_file_path, down_file_path

    def delete_migration(self, version_or_name: str) -> List[Path]:
        deleted_files: List[Path] = []
        clean_target = version_or_name.strip()

        for search_dir in [self.up_dir, self.down_dir, self.migrations_dir]:
            if not search_dir.exists():
                continue
            for file_path in search_dir.glob("*.sql"):
                if clean_target in file_path.name:
                    file_path.unlink()
                    deleted_files.append(file_path)

        return deleted_files

    @staticmethod
    def read_all_schema_sql(schema_dir: Path) -> str:
        """
        Concatenates all .sql files in the schema directory in logical dependency order
        (tables -> functions/procedures -> views -> standalone indexes) to build target DDL state.
        """
        if not schema_dir.exists():
            return "-- Migration UP SQL statements\n"

        sql_files = list(schema_dir.glob("**/*.sql"))
        if not sql_files:
            return "-- Migration UP SQL statements\n"

        def get_category_priority(p: Path) -> int:
            parts = [part.lower() for part in p.parts]
            if "tables" in parts:
                return 1
            if "functions" in parts or "procedures" in parts:
                return 2
            if "views" in parts:
                return 3
            if "indexes" in parts:
                return 4
            return 5

        sorted_files = sorted(sql_files, key=lambda f: (get_category_priority(f), str(f)))

        schemas = set()
        for f in sorted_files:
            rel = f.relative_to(schema_dir)
            if len(rel.parts) > 1:
                schemas.add(rel.parts[0])

        parts = []
        if schemas:
            parts.append("-- Ensure Schemas Exist")
            for sname in sorted(schemas):
                if sname not in ("public", "psqlmigr"):
                    parts.append(f"CREATE SCHEMA IF NOT EXISTS {sname};")
            parts.append("")

        for f in sorted_files:
            rel_path = f.relative_to(schema_dir)
            content = f.read_text(encoding="utf-8").strip()
            if content:
                parts.append(f"-- ==========================================")
                parts.append(f"-- Object: {rel_path}")
                parts.append(f"-- ==========================================")
                parts.append(content)
                parts.append("")

        return "\n".join(parts)
