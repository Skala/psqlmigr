from typing import Dict, List, Any, Optional
import psycopg

class PostgresInspector:
    def __init__(self, db_url: str):
        self.db_url = db_url

    def get_user_schemas(self) -> List[str]:
        query = """
            SELECT nspname 
            FROM pg_namespace 
            WHERE nspname NOT IN ('pg_catalog', 'information_schema', 'pg_toast', 'psqlmigr')
              AND nspname NOT LIKE 'pg_temp_%'
              AND nspname NOT LIKE 'pg_toast_temp_%'
            ORDER BY nspname;
        """
        with psycopg.connect(self.db_url) as conn:
            with conn.cursor() as cur:
                cur.execute(query)
                return [row[0] for row in cur.fetchall()]

    def inspect_tables(self, schema_name: str) -> List[Dict[str, Any]]:
        query = """
            SELECT 
                c.relname AS table_name,
                c.relkind AS relkind,
                c.relispartition AS is_partition,
                pg_get_partkeydef(c.oid) AS partition_by,
                pg_get_expr(c.relpartbound, c.oid) AS partition_bound,
                parent.relname AS parent_table
            FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            LEFT JOIN pg_inherits i ON i.inhrelid = c.oid
            LEFT JOIN pg_class parent ON parent.oid = i.inhparent
            WHERE n.nspname = %s
              AND c.relkind IN ('r', 'p')
            ORDER BY c.relname;
        """
        tables = []
        with psycopg.connect(self.db_url) as conn:
            with conn.cursor() as cur:
                cur.execute(query, (schema_name,))
                rows = cur.fetchall()

                for tname, relkind, is_partition, part_by, part_bound, parent_tname in rows:
                    columns = self._get_table_columns(cur, schema_name, tname)
                    pk_cols = self._get_primary_key(cur, schema_name, tname)
                    fk_constraints = self._get_foreign_keys(cur, schema_name, tname)
                    unique_constraints = self._get_unique_constraints(cur, schema_name, tname)

                    tables.append({
                        "name": tname,
                        "relkind": relkind,
                        "is_partition": is_partition,
                        "partition_by": part_by,
                        "partition_bound": part_bound,
                        "parent_table": parent_tname,
                        "columns": columns,
                        "primary_key": pk_cols,
                        "foreign_keys": fk_constraints,
                        "unique_constraints": unique_constraints
                    })
        return tables

    def _get_table_columns(self, cur, schema_name: str, table_name: str) -> List[Dict[str, Any]]:
        query = """
            SELECT column_name, data_type, udt_name, is_nullable, column_default, character_maximum_length
            FROM information_schema.columns
            WHERE table_schema = %s AND table_name = %s
            ORDER BY ordinal_position;
        """
        cur.execute(query, (schema_name, table_name))
        cols = []
        for row in cur.fetchall():
            cname, dtype, udt_name, is_null, cdef, char_len = row
            full_type = udt_name.upper() if dtype == 'USER-DEFINED' else (
                f"{dtype.upper()}({char_len})" if char_len and dtype in ('character varying', 'character') else dtype.upper()
            )
            cols.append({
                "name": cname,
                "type": full_type,
                "nullable": is_null == 'YES',
                "default": cdef
            })
        return cols

    def _get_primary_key(self, cur, schema_name: str, table_name: str) -> List[str]:
        query = """
            SELECT kcu.column_name
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu
              ON tc.constraint_name = kcu.constraint_name
             AND tc.table_schema = kcu.table_schema
            WHERE tc.constraint_type = 'PRIMARY KEY'
              AND tc.table_schema = %s
              AND tc.table_name = %s
            ORDER BY kcu.ordinal_position;
        """
        cur.execute(query, (schema_name, table_name))
        return [row[0] for row in cur.fetchall()]

    def _get_foreign_keys(self, cur, schema_name: str, table_name: str) -> List[Dict[str, Any]]:
        query = """
            SELECT
                tc.constraint_name,
                kcu.column_name,
                ccu.table_schema AS foreign_table_schema,
                ccu.table_name AS foreign_table_name,
                ccu.column_name AS foreign_column_name
            FROM information_schema.table_constraints AS tc
            JOIN information_schema.key_column_usage AS kcu
              ON tc.constraint_name = kcu.constraint_name
             AND tc.table_schema = kcu.table_schema
            JOIN information_schema.constraint_column_usage AS ccu
              ON ccu.constraint_name = tc.constraint_name
             AND ccu.table_schema = tc.table_schema
            WHERE tc.constraint_type = 'FOREIGN KEY'
              AND tc.table_schema = %s
              AND tc.table_name = %s;
        """
        cur.execute(query, (schema_name, table_name))
        fks = []
        for row in cur.fetchall():
            cname, col, fschema, ftable, fcol = row
            fks.append({
                "constraint_name": cname,
                "column": col,
                "foreign_schema": fschema,
                "foreign_table": ftable,
                "foreign_column": fcol
            })
        return fks

    def _get_unique_constraints(self, cur, schema_name: str, table_name: str) -> List[Dict[str, Any]]:
        query = """
            SELECT tc.constraint_name, kcu.column_name
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu
              ON tc.constraint_name = kcu.constraint_name
             AND tc.table_schema = kcu.table_schema
            WHERE tc.constraint_type = 'UNIQUE'
              AND tc.table_schema = %s
              AND tc.table_name = %s;
        """
        cur.execute(query, (schema_name, table_name))
        uniques = {}
        for cname, col in cur.fetchall():
            uniques.setdefault(cname, []).append(col)
        return [{"constraint_name": k, "columns": v} for k, v in uniques.items()]

    def inspect_views(self, schema_name: str) -> List[Dict[str, str]]:
        query = """
            SELECT table_name, view_definition
            FROM information_schema.views
            WHERE table_schema = %s
            ORDER BY table_name;
        """
        views = []
        with psycopg.connect(self.db_url) as conn:
            with conn.cursor() as cur:
                cur.execute(query, (schema_name,))
                for name, vdef in cur.fetchall():
                    views.append({
                        "name": name,
                        "definition": vdef.strip()
                    })
        return views

    def inspect_functions_and_procedures(self, schema_name: str) -> List[Dict[str, Any]]:
        query = """
            SELECT 
                p.proname AS name,
                pg_get_functiondef(p.oid) AS definition,
                l.lanname AS language,
                p.prokind AS kind
            FROM pg_proc p
            JOIN pg_namespace n ON n.oid = p.pronamespace
            JOIN pg_language l ON l.oid = p.prolang
            WHERE n.nspname = %s
              AND p.prokind IN ('f', 'p', 'a', 'w')
            ORDER BY p.proname;
        """
        routines = []
        with psycopg.connect(self.db_url) as conn:
            with conn.cursor() as cur:
                cur.execute(query, (schema_name,))
                for name, fdef, lang, kind in cur.fetchall():
                    routines.append({
                        "name": name,
                        "definition": fdef.strip(),
                        "language": lang,
                        "kind": kind
                    })
        return routines

    def inspect_indexes(self, schema_name: str) -> List[Dict[str, Any]]:
        query = """
            SELECT
                i.relname AS index_name,
                t.relname AS table_name,
                pg_get_indexdef(idx.indexrelid) AS index_def
            FROM pg_index idx
            JOIN pg_class i ON i.oid = idx.indexrelid
            JOIN pg_class t ON t.oid = idx.indrelid
            JOIN pg_namespace n ON n.oid = t.relnamespace
            WHERE n.nspname = %s
              AND t.relkind IN ('r', 'p', 'm')
              AND NOT idx.indisprimary
            ORDER BY i.relname;
        """
        indexes = []
        with psycopg.connect(self.db_url) as conn:
            with conn.cursor() as cur:
                cur.execute(query, (schema_name,))
                for iname, tname, idef in cur.fetchall():
                    indexes.append({
                        "name": iname,
                        "table_name": tname,
                        "definition": idef.strip()
                    })
        return indexes
