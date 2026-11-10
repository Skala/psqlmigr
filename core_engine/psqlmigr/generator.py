from datetime import datetime, timezone
from pathlib import Path
from typing import Tuple, Optional, List

def bump_semver(version_str: str) -> str:
    cleaned = version_str.strip().lstrip("v")
    parts = cleaned.split(".")
    if len(parts) == 3 and all(p.isdigit() for p in parts):
        major, minor, patch = int(parts[0]), int(parts[1]), int(parts[2])
        return f"{major}.{minor}.{patch + 1}"
    elif len(parts) == 2 and all(p.isdigit() for p in parts):
        return f"{parts[0]}.{int(parts[1]) + 1}.0"
    return "0.1.1"

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
        down_sql: str = "-- Migration DOWN SQL statements\n",
        project_version: Optional[str] = None
    ) -> Tuple[Path, Path, str]:
        from psqlmigr import __version__ as engine_version
        from psqlmigr.checksum import ChecksumManager
        from psqlmigr.config import ConfigManager

        cfg_mgr = ConfigManager(self.migrations_dir.parent)
        cfg_data = cfg_mgr.load_config()
        current_version = cfg_data.get("version", "0.1.0")

        manifest = ChecksumManager.get_migrations_manifest(self.migrations_dir)

        # Determine target project version
        if project_version and project_version.strip():
            target_version = project_version.strip().lstrip("v")
        else:
            if not manifest:
                target_version = current_version
            else:
                target_version = bump_semver(current_version)

        # Save updated version to psqlmigr.yaml
        cfg_data["version"] = target_version
        cfg_mgr.save_config(cfg_data)

        next_seq = len(manifest) + 1
        seq_prefix = f"v{next_seq:03d}"
        
        now = datetime.now(timezone.utc)
        timestamp = now.strftime("%Y%m%d%H%M%S")
        iso_time = now.strftime("%Y-%m-%d %H:%M:%S UTC")

        clean_name = name.strip().lower().replace(" ", "_")
        if not clean_name:
            clean_name = "migration"

        version_id = f"v{target_version}_{timestamp}"
        filename = f"{version_id}_{clean_name}.sql"

        up_file_path = self.up_dir / filename
        down_file_path = self.down_dir / filename

        header = (
            f"-- ==============================================================================\n"
            f"-- Migration Version : {version_id}\n"
            f"-- Project Version   : {target_version}\n"
            f"-- Description       : {clean_name}\n"
            f"-- Generated At      : {iso_time}\n"
            f"-- Engine Version    : psqlmigr-core v{engine_version}\n"
            f"-- ==============================================================================\n\n"
        )

        final_up_sql = header + (up_sql if up_sql.strip() else "-- Migration UP SQL statements\n")
        final_down_sql = header + (down_sql if down_sql.strip() else "-- Migration DOWN SQL statements\n")

        up_file_path.write_text(final_up_sql, encoding="utf-8")
        down_file_path.write_text(final_down_sql, encoding="utf-8")

        return up_file_path, down_file_path, target_version

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
    def _sort_schema_files_by_dependency(sql_files: List[Path], schema_dir: Path) -> List[Path]:
        import re

        def get_category_priority(p: Path) -> int:
            parts = [part.lower() for part in p.parts]
            if "sequences" in parts:
                return 1
            if "tables" in parts:
                return 2
            if "functions" in parts or "procedures" in parts or "views" in parts:
                return 3
            if "indexes" in parts:
                return 4
            return 5

        file_info = []
        for f in sql_files:
            rel = f.relative_to(schema_dir)
            sname = rel.parts[0] if len(rel.parts) > 1 else "public"
            stem = f.stem
            priority = get_category_priority(rel)
            content = f.read_text(encoding="utf-8").lower()
            file_info.append({
                "file": f,
                "rel": str(rel),
                "sname": sname.lower(),
                "stem": stem.lower(),
                "priority": priority,
                "content": content
            })

        prereqs: dict[int, set[int]] = {i: set() for i in range(len(file_info))}

        for i, target in enumerate(file_info):
            for j, provider in enumerate(file_info):
                if i == j:
                    continue

                stem = provider['stem']
                sname = provider['sname']

                pattern_q = r"\b" + re.escape(sname) + r"\s*\.\s*" + re.escape(stem) + r"\b"
                pattern_stem = r"\b" + re.escape(stem) + r"\b"

                is_dependent = False
                if re.search(pattern_q, target['content']):
                    is_dependent = True
                elif len(stem) > 3 and stem not in ("select", "from", "where", "table", "index", "view", "type", "date", "name", "id", "user", "data", "status", "value", "key", "code") and re.search(pattern_stem, target['content']):
                    is_dependent = True

                if is_dependent:
                    prereqs[i].add(j)

        sorted_indices: list[int] = []
        remaining = set(range(len(file_info)))

        while remaining:
            candidates = [
                idx for idx in remaining 
                if prereqs[idx].issubset(set(sorted_indices))
            ]

            if not candidates:
                candidates = list(remaining)

            best = min(candidates, key=lambda idx: (file_info[idx]["priority"], file_info[idx]["rel"]))
            sorted_indices.append(best)
            remaining.remove(best)

        return [file_info[idx]["file"] for idx in sorted_indices]

    @staticmethod
    def read_all_schema_sql(schema_dir: Path) -> str:
        """
        Concatenates all .sql files in the schema directory in logical dependency order
        (sequences -> tables -> functions/procedures/views -> standalone indexes) to build target DDL state.
        """
        if not schema_dir.exists():
            return "-- Migration UP SQL statements\n"

        sql_files = list(schema_dir.glob("**/*.sql"))
        if not sql_files:
            return "-- Migration UP SQL statements\n"

        sorted_files = MigrationGenerator._sort_schema_files_by_dependency(sql_files, schema_dir)

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

    @staticmethod
    def generate_down_sql_from_schema(schema_dir: Path) -> str:
        """
        Generates corresponding rollback/reversal DDL statements (DROP TABLE, DROP VIEW, etc.)
        for all objects present in the schema directory in reverse dependency order.
        """
        if not schema_dir.exists():
            return "-- Migration DOWN SQL statements\n"

        sql_files = list(schema_dir.glob("**/*.sql"))
        if not sql_files:
            return "-- Migration DOWN SQL statements\n"

        schemas = set()
        tables = []
        views = []
        functions = []
        procedures = []
        indexes = []
        sequences = []

        for f in sql_files:
            rel = f.relative_to(schema_dir)
            if len(rel.parts) < 2:
                continue

            sname = rel.parts[0]
            if sname not in ("public", "psqlmigr"):
                schemas.add(sname)

            obj_type = rel.parts[1].lower() if len(rel.parts) > 2 else ""
            obj_name = f.stem

            if obj_type == "tables":
                tables.append(f"{sname}.{obj_name}")
            elif obj_type == "views":
                views.append(f"{sname}.{obj_name}")
            elif obj_type == "functions":
                functions.append(f"{sname}.{obj_name}")
            elif obj_type == "procedures":
                procedures.append(f"{sname}.{obj_name}")
            elif obj_type == "indexes":
                indexes.append(f"{sname}.{obj_name}")
            elif obj_type == "sequences":
                sequences.append(f"{sname}.{obj_name}")

        down_parts = []

        # 1. Drop Standalone Indexes
        if indexes:
            down_parts.append("-- Drop Standalone Indexes")
            for idx in sorted(indexes, reverse=True):
                down_parts.append(f"DROP INDEX IF EXISTS {idx} CASCADE;")
            down_parts.append("")

        # 2. Drop Views
        if views:
            down_parts.append("-- Drop Views")
            for vw in sorted(views, reverse=True):
                down_parts.append(f"DROP VIEW IF EXISTS {vw} CASCADE;")
            down_parts.append("")

        # 3. Drop Functions & Procedures
        if functions or procedures:
            down_parts.append("-- Drop Functions & Procedures")
            for fn in sorted(functions, reverse=True):
                down_parts.append(f"DROP FUNCTION IF EXISTS {fn} CASCADE;")
            for pr in sorted(procedures, reverse=True):
                down_parts.append(f"DROP PROCEDURE IF EXISTS {pr} CASCADE;")
            down_parts.append("")

        # 4. Drop Tables (includes child partitions automatically via CASCADE)
        if tables:
            down_parts.append("-- Drop Tables")
            for tbl in sorted(tables, reverse=True):
                down_parts.append(f"DROP TABLE IF EXISTS {tbl} CASCADE;")
            down_parts.append("")

        # 5. Drop Sequences
        if sequences:
            down_parts.append("-- Drop Sequences")
            for seq in sorted(sequences, reverse=True):
                down_parts.append(f"DROP SEQUENCE IF EXISTS {seq} CASCADE;")
            down_parts.append("")

        # 6. Drop Schemas
        if schemas:
            down_parts.append("-- Drop Schemas")
            for sname in sorted(schemas, reverse=True):
                down_parts.append(f"DROP SCHEMA IF EXISTS {sname} CASCADE;")
            down_parts.append("")

        return "\n".join(down_parts) if down_parts else "-- Migration DOWN SQL statements\n"
