import time
from pathlib import Path
from typing import Dict, List, Tuple, Any, Optional
import psycopg
from psycopg import sql
from psqlmigr.db import DatabaseManager
from psqlmigr.checksum import ChecksumManager

class MigrationExecutor:
    def __init__(self, db_url: str, tracking_schema: str = "psqlmigr", tracking_table: str = "schema_migrations"):
        self.db_url = db_url
        self.tracking_schema = tracking_schema
        self.tracking_table = tracking_table
        self.db = DatabaseManager(db_url)

    def get_applied_migrations(self) -> Dict[str, Dict[str, Any]]:
        self.db.ensure_tracking_schema_and_table(self.tracking_schema, self.tracking_table)
        table_ident = sql.Identifier(self.tracking_schema, self.tracking_table)
        
        applied = {}
        query = sql.SQL("SELECT version, name, checksum, applied_at FROM {} ORDER BY version;").format(table_ident)
        
        with psycopg.connect(self.db_url, connect_timeout=3) as conn:
            with conn.cursor() as cur:
                cur.execute(query)
                for row in cur.fetchall():
                    ver, name, checksum, applied_at = row
                    applied[ver] = {
                        "version": ver,
                        "name": name,
                        "checksum": checksum,
                        "applied_at": applied_at.isoformat() if applied_at else None
                    }
        return applied

    def apply_pending_migrations(self, migrations_dir: Path) -> List[Dict[str, Any]]:
        manifest = ChecksumManager.get_migrations_manifest(migrations_dir)
        applied = self.get_applied_migrations()
        executed = []

        table_ident = sql.Identifier(self.tracking_schema, self.tracking_table)

        for item in manifest:
            version = item["version"]
            if version in applied:
                # Verify checksum integrity
                if applied[version]["checksum"] != item["up_checksum"]:
                    print(f"Warning: Checksum mismatch for applied migration {version}!")
                continue

            up_file = migrations_dir / item["up_file"]
            if not up_file.exists():
                raise FileNotFoundError(f"Migration file missing: {up_file}")

            sql_content = up_file.read_text(encoding="utf-8")
            start_time = time.time()

            with psycopg.connect(self.db_url) as conn:
                with conn.cursor() as cur:
                    # Execute migration SQL in a single transaction
                    cur.execute(sql_content)
                    
                    # Record migration in tracking table
                    insert_stmt = sql.SQL("""
                        INSERT INTO {} (version, name, checksum, project_version, execution_time_ms)
                        VALUES (%s, %s, %s, %s, %s);
                    """).format(table_ident)

                    elapsed_ms = int((time.time() - start_time) * 1000)
                    cur.execute(insert_stmt, (version, item["name"], item["up_checksum"], item.get("project_version", ""), elapsed_ms))
                conn.commit()

            executed.append({
                "version": version,
                "name": item["name"],
                "execution_time_ms": elapsed_ms,
                "status": "APPLIED"
            })

        return executed

    def validate_migrations_dry_run(self, migrations_dir: Path) -> List[Dict[str, Any]]:
        """
        Executes pending migrations inside a TRANSACTION with ROLLBACK to verify correctness without mutating database.
        """
        manifest = ChecksumManager.get_migrations_manifest(migrations_dir)
        applied = self.get_applied_migrations()
        results = []

        with psycopg.connect(self.db_url) as conn:
            with conn.cursor() as cur:
                try:
                    for item in manifest:
                        version = item["version"]
                        if version in applied:
                            results.append({"version": version, "name": item["name"], "status": "ALREADY_APPLIED", "error": None})
                            continue

                        up_file = migrations_dir / item["up_file"]
                        if not up_file.exists():
                            results.append({"version": version, "name": item["name"], "status": "FAILED", "error": f"File not found: {up_file}"})
                            break

                        sql_content = up_file.read_text(encoding="utf-8")
                        
                        start_time = time.time()
                        try:
                            cur.execute(sql_content)
                            elapsed_ms = int((time.time() - start_time) * 1000)
                            results.append({
                                "version": version,
                                "name": item["name"],
                                "execution_time_ms": elapsed_ms,
                                "status": "VALIDATED_DRY_RUN",
                                "error": None
                            })
                        except Exception as e:
                            results.append({
                                "version": version,
                                "name": item["name"],
                                "execution_time_ms": 0,
                                "status": "FAILED",
                                "error": str(e)
                            })
                            break
                finally:
                    conn.rollback() # Always rollback dry-run executions!

        return results
