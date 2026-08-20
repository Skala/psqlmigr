from datetime import datetime, timezone
from pathlib import Path
from typing import Tuple, Optional
import sqlglot

class MigrationGenerator:
    def __init__(self, migrations_dir: Path):
        self.migrations_dir = migrations_dir
        self.migrations_dir.mkdir(parents=True, exist_ok=True)

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

        up_filename = f"{timestamp}_{clean_name}.up.sql"
        down_filename = f"{timestamp}_{clean_name}.down.sql"

        up_file_path = self.migrations_dir / up_filename
        down_file_path = self.migrations_dir / down_filename

        up_file_path.write_text(up_sql, encoding="utf-8")
        down_file_path.write_text(down_sql, encoding="utf-8")

        return up_file_path, down_file_path

    @staticmethod
    def read_all_schema_sql(schema_dir: Path) -> str:
        """
        Concatenates all .sql files in the schema directory to build target DDL state.
        """
        if not schema_dir.exists():
            return ""
        
        sql_parts = []
        for file_path in sorted(schema_dir.glob("**/*.sql")):
            sql_parts.append(f"-- File: {file_path.relative_to(schema_dir)}\n" + file_path.read_text(encoding="utf-8"))
        
        return "\n\n".join(sql_parts)
