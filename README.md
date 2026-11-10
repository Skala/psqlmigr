# PsqlMigr - PostgreSQL Schema & Migration Manager

**PsqlMigr** is a modern tool for declarative schema versioning, diff analysis, reverse-engineering, and database migration management for PostgreSQL across DevOps pipelines and Visual Studio Code / Antigravity IDE.

## Key Features

- **Declarative Schema Structure (`schemas/`)**: Store your database state in clean, human-readable DDL files organized by schema and object type: `schemas/<schema>/<object_type>/<name>.sql` (`tables`, `views`, `functions`, `procedures`, `sequences`, `indexes`).
- **Reverse-Engineering (`psqlmigr pull`)**: Inspect and automatically split an existing PostgreSQL database structure into modular DDL files (including full support for partitioned tables, `IDENTITY` columns, `NUMERIC(p,s)` precision/scale, indexes, and `nextval` sequences).
- **Schema Comparison & Selective Sync (`psqlmigr diff` / `psqlmigr sync`)**: Compare live database schemas against your local `schemas/` directory, detect new (`ADDED_IN_DB`), modified (`MODIFIED`), and removed (`DELETED_IN_DB`) objects, preview unified SQL diffs, and choose exactly which changes to apply to your local project.
- **Versioned Migration Scripts (`psqlmigr plan`)**: Automatically resolve topological dependencies (sequences → tables → functions/procedures/views → standalone indexes) and generate paired `migrations/up/` and `migrations/down/` scripts with semantic versioning and timestamps (`v0.1.0_YYYYMMDDHHMMSS_name.sql`).
- **Dry-Run Validation (`psqlmigr validate`)**: Test pending migration scripts inside an isolated PostgreSQL transaction (`BEGIN ... ROLLBACK`) without mutating database state.
- **SHA256 Checksum Management (`psqlmigr checksum`)**: Track and verify SHA256 checksums for migration files to guarantee deployment integrity.
- **`.env` Integration**: Secure connection configuration (including special-character password encoding) and instant database connectivity testing.
- **VS Code & Antigravity IDE Extension**: Dedicated sidebar TreeViews (*Database Connection*, *Schema Objects Explorer*, *Migration History & Status*), interactive multi-select schema synchronization, and native **Side-by-Side Diff** preview (`Local Project ↔ Database`).
- **DevOps Ready**: Built-in Docker image (`docker/Dockerfile`) and GitHub Actions CI/CD workflow (`.github/workflows/db-migration.yml`).

---

## Project Structure

Running `psqlmigr init` creates the following project layout:

```text
.
├── psqlmigr.yaml          # Project configuration (version, schemas/ and migrations/ paths)
├── .env                   # PostgreSQL database connection parameters
├── schemas/               # Declarative state of database schemas
│   └── public/
│       ├── sequences/
│       ├── tables/
│       ├── views/
│       ├── functions/
│       ├── procedures/
│       └── indexes/
└── migrations/            # Versioned migration scripts
    ├── up/                # Forward migration scripts (UP)
    └── down/              # Rollback migration scripts (DOWN)
```

---

## Quick Start (CLI)

```bash
# 1. Initialize project structure (creates psqlmigr.yaml, .env, schemas/, migrations/)
psqlmigr init

# 2. Configure connection in .env and test connectivity to PostgreSQL
psqlmigr set-env --host localhost --port 5432 --user postgres --password secret --database my_db
psqlmigr test-connection

# 3. Pull all schemas from the database into schemas/
psqlmigr pull

# 4. Compare live database against local schemas/ directory (displays summary table and SQL diff)
psqlmigr diff

# 5. Selectively synchronize local project with the database:
# a) Interactive mode (prompts for each object: [y = yes, n = no, a = all remaining, q = quit])
psqlmigr sync

# b) Update only specific files in schemas/
psqlmigr sync --file public/tables/users.sql --file public/views/v_active_users.sql

# c) Apply all detected differences without prompting
psqlmigr sync --all

# 6. Generate a migration (auto-bumps version or accepts a custom --version tag)
psqlmigr plan "create_users_table"
psqlmigr plan "add_audit_views" --version 0.2.0

# 7. Validate pending migrations in a test transaction (Dry-Run with ROLLBACK)
psqlmigr validate

# 8. Apply pending migrations to the PostgreSQL database
psqlmigr apply

# 9. Check migration status and recalculate SHA256 checksums
psqlmigr status
psqlmigr checksum

# 10. Remove a local migration (deletes both UP and DOWN files)
psqlmigr remove-migration v0.2.0
```

> All CLI commands also support the `--json` flag for seamless CI/CD and VS Code extension integration.

---

## VS Code / Antigravity IDE Extension

The **PsqlMigr** sidebar provides three dedicated views with quick-action toolbar buttons:

1. **Database Connection (.env)**
   - **Configure Connection & Save .env** – interactive step-by-step connection setup (persists across window switches and pre-fills existing `.env` values).
   - **Test PostgreSQL Connection** – verifies database connectivity and server version.
2. **Schema Objects Explorer**
   - **Pull Schema from Database** (`$(cloud-download)`) – full reverse-engineering of database objects into `schemas/`.
   - **Compare & Sync Schema from Database** (`$(diff)`) – compares the database against `schemas/`, displays detected differences (`ADDED_IN_DB`, `MODIFIED`, `DELETED_IN_DB`) in a multi-select picker, and lets you open a native **Side-by-Side Diff** view (*Local Project ↔ Database*) before applying selected updates.
3. **Migration History & Status**
   - **Generate Migration (Plan)** (`$(add)`) – generates a new `up`/`down` migration pair.
   - **Validate Migrations (Debug Dry-Run)** (`$(bug)`) – validates pending migrations inside a rolled-back transaction.
   - **Apply Pending Migrations** (`$(play)`) – executes pending migrations against the target database.
   - **Delete Migration Script** (`$(trash)`) – removes a migration from disk.

---

## Development & Testing

### Python Core Engine (`core_engine`)
```powershell
cd core_engine
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
pytest -v
```

### VS Code Extension
```powershell
npm install
npm run compile
npm run lint
npm run package
```
To launch the extension in a development host window, press **`F5`** in VS Code / Antigravity IDE (*Run Extension*).

## License

MIT
