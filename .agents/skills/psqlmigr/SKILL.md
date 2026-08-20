---
name: psqlmigr
description: Declarative PostgreSQL schema management, reverse-engineering (pull), diffing, timestamped migration generation, checksum verification, and DevOps deployment tool.
---

# psqlmigr - Antigravity Skill Guide

This skill enables the Antigravity AI Agent to autonomously manage PostgreSQL database schemas, generate migrations, reverse-engineer existing databases, test database connections, and execute database deployments.

## Core Capabilities & CLI Commands

All commands can be run via shell or `psqlmigr-core` Python binary (`core_engine/.venv/Scripts/psqlmigr.exe` or `python -m psqlmigr.cli`).

### 1. Initialize Project Structure
```bash
psqlmigr init
```
Creates `psqlmigr.yaml`, `.env`, `schema/` folder, and `migrations/` folder.

### 2. Configure Database Connection & Test `.env`
```bash
psqlmigr config set-env --host localhost --port 5432 --user postgres --password secret --database my_db
psqlmigr test-connection --json
```

### 3. Pull / Reverse-Engineer Schema from PostgreSQL
```bash
psqlmigr pull --json
```
Inspects live PostgreSQL database and dumps structured DDL SQL files into:
`schema/<schema_name>/<object_type>/<object_name>.sql`
(e.g., `schema/public/tables/users.sql`, `schema/public/functions/calculate_total.sql`).

### 4. Plan & Generate Timestamped Migration Files
```bash
psqlmigr plan "add_user_roles_table" --json
```
Generates timestamped migration files in `migrations/`:
- `migrations/YYYYMMDDHHMMSS_add_user_roles_table.up.sql`
- `migrations/YYYYMMDDHHMMSS_add_user_roles_table.down.sql`

### 5. Validate / Debug Migrations (Dry-Run)
```bash
psqlmigr validate --json
```
Executes all pending migrations inside a PostgreSQL transaction with `ROLLBACK` to verify syntax and foreign key integrity without mutating database state.

### 6. Apply Pending Migrations
```bash
psqlmigr apply --json
```
Applies pending migrations in transactions and records history in `psqlmigr.schema_migrations`.

### 7. Recalculate & Sync SHA256 Checksums
```bash
psqlmigr checksum --json
```
Recalculates SHA256 checksums for manually edited or created migration files.

### 8. Migration Status
```bash
psqlmigr status --json
```
Lists all applied and pending migrations along with timestamps and checksum audit logs.

## Workspace Layout
- `schema/` - Declarative SQL state organized by schema and object type.
- `migrations/` - Timestamped migration scripts (`YYYYMMDDHHMMSS_name.up.sql` / `.down.sql`).
- `psqlmigr.yaml` - Project configuration (tracking schema: `psqlmigr`).
- `.env` - Database connection environment variables.
