# Changelog

All notable changes to the **PsqlMigr** PostgreSQL Schema & Migration Management Extension for VS Code and Antigravity will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [0.1.1] - 2026-10-30

### Added

- **Schema Comparison & Selective Sync (`psqlmigr diff` / `psqlmigr sync`)**:
  - Added CLI command `psqlmigr diff` to compare live PostgreSQL database schemas against the local `schemas/` directory (`ADDED_IN_DB`, `MODIFIED`, `DELETED_IN_DB`) with unified SQL diff output.
  - Added CLI command `psqlmigr sync` supporting interactive per-object confirmation (`[y/n/a/q]`), selective file updates (`--file <path>`), or full synchronization (`--all`).
  - Added VS Code / Antigravity command `PsqlMigr: Compare & Sync Schema from Database` (`psqlmigr.syncSchema`) with multi-select QuickPick and native side-by-side Diff preview (*Local Project ↔ Database*).
- **Project & Database Migration Versioning**:
  - Automatically initializes project version at `0.1.0` in `psqlmigr.yaml`.
  - Supports custom version input upon generating a migration (e.g. `--version 0.2.0` or VS Code input box) or automatic patch version bumping (`0.1.0` -> `0.1.1`).
- **Graceful Error Handling & Structured JSON Output**:
  - Structured JSON error responses for `psqlmigr validate`, `psqlmigr apply`, `psqlmigr diff`, and `psqlmigr sync` to show clear error messages in VS Code without unhandled CLI tracebacks.
- **PostgreSQL Sequence Inspection & Order Resolution**:
  - Reverse-engineers database sequences (`CREATE SEQUENCE IF NOT EXISTS <schema>.<sequence_name>;`) into `schemas/<schema>/sequences/`.
  - Ensures sequence DDL statements execute prior to table DDL statements to prevent `UndefinedTable: relation "..." does not exist` errors when columns use `nextval(...)`.
- **Automatic Rollback (DOWN) DDL Generation**:
  - Automatically compiles corresponding reverse/rollback DDL statements (`DROP INDEX`, `DROP VIEW`, `DROP FUNCTION`, `DROP PROCEDURE`, `DROP TABLE ... CASCADE`, `DROP SEQUENCE ... CASCADE`, `DROP SCHEMA ... CASCADE`) into `migrations/down/` in reverse dependency execution order.
- **Unified Single-File Table DDL Generation**:
  - Combined base table definition, child partition DDL statements (`PARTITION OF`), and table-specific index DDL statements (`CREATE INDEX`) into a single self-contained SQL file per table under `schemas/<schema>/tables/<table_name>.sql`.
- **PostgreSQL Partitioning Support**:
  - Native support for Master Partitioned Tables (`PARTITION BY RANGE / LIST / HASH`).
  - Native support for Child Partition Tables (`PARTITION OF ... FOR VALUES ...`).
- **Complete Index Extraction**:
  - Full reverse-engineering of non-constraint database indexes across ordinary tables, partitioned tables, and materialized views (`indexes/` or bundled inside table DDLs).
- **Procedure & Function Separation**:
  - Routines are automatically categorized into `schemas/<schema>/functions/` and `schemas/<schema>/procedures/` based on PostgreSQL `pg_proc.prokind`.
- **Migration Directory Folder Separation**:
  - Organized migrations into clean subdirectories:
    - `migrations/up/` for forward DDL scripts.
    - `migrations/down/` for rollback DDL scripts.
  - Retained full backward compatibility with legacy `migrations/*.up.sql` root files.
- **Migration Deletion & Cleanup**:
  - Added CLI command `psqlmigr remove-migration <version>` (`psqlmigr rm-migration`).
  - Added VS Code command `PsqlMigr: Delete Migration Script` with inline trash icon button (`$(trash)`) in the **Migration History Explorer** TreeView.
- **Interactive Overwrite Prompt**:
  - Modal warning notification before executing `pullSchema` when `schemas/` directory contains existing DDL files, prompting for confirmation (`Overwrite & Pull`).
  - Automatic directory cleanup prior to dumping fresh database structure.
- **Enhanced Connection Credentials Handling**:
  - Safe percent-encoding (`quote_plus`) for passwords containing special characters (`@`, `#`, `%`, `!`, `$`).

### Changed

- Standardized declarative schema directory name from `schema/` to `schemas/` (`schemas/<schema_name>/<object_type>/<object_name>.sql`) for consistency with `migrations/` and multi-schema PostgreSQL databases.
- Improved `psqlmigr plan` (Generate Migration) to automatically compile declarative DDL scripts from `schemas/` in topological dependency order (Sequences -> Tables/Partitions/Indexes -> Functions/Procedures/Views -> Standalone Indexes).
- Optimized VS Code Extension execution host launch configuration (`.vscode/launch.json`) and fixed `preLaunchTask` to `npm: compile`.

---

## [0.1.0] - 2026-08-20

### Added

- Initial release of **PsqlMigr** for VS Code & Antigravity.
- Python CLI Core Engine (`psqlmigr-core`) using `Typer`, `psycopg3`, `rich`, and `sqlglot`.
- Visual Studio Code Extension with 3 Activity Bar TreeViews:
  - **Database Connection (.env)**
  - **Schema Objects Explorer**
  - **Migration History & Status**
- Isolated migration tracking schema `psqlmigr.schema_migrations`.
- Dry-run migration validation using `BEGIN ... ROLLBACK` transactions (`psqlmigr validate`).
- SHA256 checksum verification and integrity manifests (`psqlmigr checksum`).
- Antigravity AI Agent Skill integration (`.agents/skills/psqlmigr/SKILL.md`).
- Docker containerization (`docker/Dockerfile`) and GitHub Actions CI/CD workflow (`.github/workflows/db-migration.yml`).
