from typing import Tuple, Dict, Any, Optional
import psycopg
from psycopg import sql

class DatabaseManager:
    def __init__(self, db_url: str):
        self.db_url = db_url

    def test_connection(self) -> Tuple[bool, str, Dict[str, Any]]:
        """
        Tests connection to PostgreSQL database.
        Returns: (success: bool, message: str, details: dict)
        """
        try:
            with psycopg.connect(self.db_url, connect_timeout=5) as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT version(), current_database(), current_user, current_schema();")
                    row = cur.fetchone()
                    if row:
                        version, db_name, user, schema = row
                        return True, "Successfully connected to PostgreSQL database.", {
                            "version": version,
                            "database": db_name,
                            "user": user,
                            "schema": schema
                        }
                    return True, "Connected successfully.", {}
        except Exception as e:
            return False, f"Failed to connect to database: {str(e)}", {}

    def execute_query(self, query: str, params: Optional[Tuple] = None) -> list:
        with psycopg.connect(self.db_url) as conn:
            with conn.cursor() as cur:
                cur.execute(query, params)
                if cur.description:
                    return cur.fetchall()
                return []

    def ensure_tracking_schema_and_table(self, tracking_schema: str, tracking_table: str) -> None:
        """
        Ensures the dedicated psqlmigr tracking schema and migrations table exist.
        """
        schema_ident = sql.Identifier(tracking_schema)
        table_ident = sql.Identifier(tracking_schema, tracking_table)

        with psycopg.connect(self.db_url, connect_timeout=3) as conn:
            with conn.cursor() as cur:
                # Create schema if not exists
                cur.execute(sql.SQL("CREATE SCHEMA IF NOT EXISTS {};").format(schema_ident))
                
                # Create tracking table if not exists
                cur.execute(sql.SQL("""
                    CREATE TABLE IF NOT EXISTS {} (
                        id SERIAL PRIMARY KEY,
                        version VARCHAR(255) NOT NULL UNIQUE,
                        name VARCHAR(255) NOT NULL,
                        checksum VARCHAR(64) NOT NULL,
                        project_version VARCHAR(50),
                        applied_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                        execution_time_ms INT
                    );
                """).format(table_ident))
                # Ensure project_version column exists for existing tracking tables
                cur.execute(sql.SQL("""
                    ALTER TABLE {} ADD COLUMN IF NOT EXISTS project_version VARCHAR(50);
                """).format(table_ident))
            conn.commit()
