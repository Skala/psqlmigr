import sys
import json
from pathlib import Path
from typing import Optional, List

# Ensure UTF-8 output encoding on Windows console
if str(Path(__file__).resolve().parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
if sys.platform == "win32":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import typer
from rich import print as rprint
from rich.console import Console
from rich.table import Table

from psqlmigr import __version__
from psqlmigr.config import ConfigManager
from psqlmigr.db import DatabaseManager
from psqlmigr.dumper import SchemaDumper
from psqlmigr.generator import MigrationGenerator
from psqlmigr.checksum import ChecksumManager
from psqlmigr.executor import MigrationExecutor
from psqlmigr.linter import MigrationLinter

app = typer.Typer(
    name="psqlmigr",
    help="PostgreSQL schema versioning, reverse-engineering, and migration management CLI.",
    add_completion=False,
)
console = Console()

def get_db_url_or_exit(config_mgr: ConfigManager, json_mode: bool = False) -> str:
    db_url = config_mgr.get_database_url()
    if not db_url:
        msg = "Error: Database connection URL is not set. Use 'psqlmigr config set-env' or set DATABASE_URL in .env file."
        if json_mode:
            print(json.dumps({"success": False, "error": msg}))
        else:
            rprint(f"[bold red]{msg}[/bold red]")
        sys.exit(1)
    return db_url

@app.command()
def version():
    """Prints the psqlmigr version."""
    rprint(f"[bold green]psqlmigr-core[/bold green] version {__version__}")

@app.command()
def init(
    target_dir: Optional[Path] = typer.Option(None, "--dir", "-d", help="Target project directory"),
    json_mode: bool = typer.Option(False, "--json", help="Output result as JSON")
):
    """Initializes a new psqlmigr project structure."""
    root = target_dir or Path.cwd()
    cfg_mgr = ConfigManager(root)

    cfg_mgr.load_config()
    cfg_data = cfg_mgr.load_config()
    cfg_mgr.save_config(cfg_data)

    schema_dir = root / cfg_data["schema_dir"]
    migrations_dir = root / cfg_data["migrations_dir"]

    schema_dir.mkdir(parents=True, exist_ok=True)
    migrations_dir.mkdir(parents=True, exist_ok=True)
    (migrations_dir / "up").mkdir(parents=True, exist_ok=True)
    (migrations_dir / "down").mkdir(parents=True, exist_ok=True)

    env_path = root / ".env"
    if not env_path.exists():
        env_path.write_text(
            "# PostgreSQL Database Connection Settings\n"
            "# DATABASE_URL=postgresql://postgres:postgres@localhost:5432/my_database\n"
            "POSTGRES_HOST=localhost\n"
            "POSTGRES_PORT=5432\n"
            "POSTGRES_USER=postgres\n"
            "POSTGRES_PASSWORD=postgres\n"
            "POSTGRES_DB=my_database\n"
            "POSTGRES_SSLMODE=disable\n",
            encoding="utf-8"
        )

    res = {
        "success": True,
        "message": f"Initialized psqlmigr project in {root}",
        "config_file": str(cfg_mgr.config_path),
        "env_file": str(env_path),
        "schema_dir": str(schema_dir),
        "migrations_dir": str(migrations_dir),
    }

    if json_mode:
        print(json.dumps(res))
    else:
        rprint(f"[bold green]✓[/bold green] Initialized psqlmigr project in [cyan]{root}[/cyan]")
        rprint(f"  - Config: [yellow]{cfg_mgr.config_path.name}[/yellow]")
        rprint(f"  - Env: [yellow]{env_path.name}[/yellow]")
        rprint(f"  - Schema Dir: [yellow]{schema_dir.name}/[/yellow]")
        rprint(f"  - Migrations Dir: [yellow]{migrations_dir.name}/[/yellow]")

@app.command("test-connection")
def test_connection(
    json_mode: bool = typer.Option(False, "--json", help="Output result as JSON")
):
    """Tests connection to PostgreSQL database."""
    cfg_mgr = ConfigManager()
    db_url = get_db_url_or_exit(cfg_mgr, json_mode)

    db_mgr = DatabaseManager(db_url)
    success, msg, details = db_mgr.test_connection()

    res = {
        "success": success,
        "message": msg,
        "details": details
    }

    if json_mode:
        print(json.dumps(res))
    else:
        if success:
            rprint(f"[bold green]✓ {msg}[/bold green]")
            for k, v in details.items():
                rprint(f"  - [cyan]{k}[/cyan]: {v}")
        else:
            rprint(f"[bold red]✗ {msg}[/bold red]")
            sys.exit(1)

@app.command("set-env")
def set_env(
    host: Optional[str] = typer.Option(None, "--host"),
    port: Optional[str] = typer.Option("5432", "--port"),
    user: Optional[str] = typer.Option(None, "--user"),
    password: Optional[str] = typer.Option(None, "--password"),
    database: Optional[str] = typer.Option(None, "--database", "--db"),
    url: Optional[str] = typer.Option(None, "--url"),
    json_mode: bool = typer.Option(False, "--json")
):
    """Sets PostgreSQL connection parameters in .env file."""
    cfg_mgr = ConfigManager()
    env_vars = {}

    if url:
        env_vars["DATABASE_URL"] = url
    else:
        if host: env_vars["POSTGRES_HOST"] = host
        if port: env_vars["POSTGRES_PORT"] = port
        if user: env_vars["POSTGRES_USER"] = user
        if password: env_vars["POSTGRES_PASSWORD"] = password
        if database: env_vars["POSTGRES_DB"] = database

    cfg_mgr.update_env(env_vars)

    res = {"success": True, "message": "Updated .env configuration.", "updated_keys": list(env_vars.keys())}
    if json_mode:
        print(json.dumps(res))
    else:
        rprint("[bold green]✓ Updated .env file successfully.[/bold green]")

@app.command("pull")
@app.command("dump-schema")
def pull_schema(
    json_mode: bool = typer.Option(False, "--json", help="Output result as JSON")
):
    """Reverse-engineers PostgreSQL database and dumps DDL SQL files into schemas/<schema_name>/<object_type>/<object_name>.sql."""
    cfg_mgr = ConfigManager()
    db_url = get_db_url_or_exit(cfg_mgr, json_mode)
    cfg_data = cfg_mgr.load_config()

    try:
        schema_dir = Path.cwd() / cfg_data["schema_dir"]
        dumper = SchemaDumper(db_url, schema_dir)

        if not json_mode:
            with console.status(f"[bold cyan]Reverse-engineering PostgreSQL schema into {schema_dir.name}/ folder...[/bold cyan]"):
                written_files = dumper.dump_schema()
        else:
            written_files = dumper.dump_schema()

        file_paths = [str(f.relative_to(Path.cwd())) for f in written_files]

        res = {
            "success": True,
            "message": f"Successfully dumped {len(written_files)} schema files into {schema_dir.name}/",
            "files_written": file_paths
        }

        if json_mode:
            print(json.dumps(res))
        else:
            rprint(f"[bold green]✓ Successfully reverse-engineered schema into [cyan]{schema_dir.name}/[/cyan][/bold green]")
            for f in file_paths:
                rprint(f"  - [yellow]{f}[/yellow]")
    except Exception as e:
        if json_mode:
            print(json.dumps({"success": False, "error": str(e), "message": f"Pull schema failed: {str(e)}"}))
            raise typer.Exit(code=0)
        else:
            rprint(f"[bold red]✗ Pull schema failed:[/bold red] {str(e)}")
            raise typer.Exit(code=1)

def _print_colored_diff(diff_text: str) -> None:
    for line in diff_text.splitlines():
        if line.startswith("+++") or line.startswith("---"):
            rprint(f"    [bold]{line}[/bold]")
        elif line.startswith("@@"):
            rprint(f"    [cyan]{line}[/cyan]")
        elif line.startswith("+"):
            rprint(f"    [green]{line}[/green]")
        elif line.startswith("-"):
            rprint(f"    [red]{line}[/red]")
        else:
            rprint(f"    {line}")

@app.command("diff")
def diff_schema_cmd(
    json_mode: bool = typer.Option(False, "--json", help="Output result as JSON")
):
    """Compares live PostgreSQL database schemas against local schemas/ directory and displays differences."""
    cfg_mgr = ConfigManager()
    db_url = get_db_url_or_exit(cfg_mgr, json_mode)
    cfg_data = cfg_mgr.load_config()

    try:
        schema_dir = Path.cwd() / cfg_data["schema_dir"]
        dumper = SchemaDumper(db_url, schema_dir)

        if not json_mode:
            with console.status(f"[bold cyan]Comparing PostgreSQL database against {schema_dir.name}/ folder...[/bold cyan]"):
                diffs = dumper.diff_schema()
        else:
            diffs = dumper.diff_schema()

        res = {
            "success": True,
            "total_diffs": len(diffs),
            "diffs": diffs,
            "message": f"Found {len(diffs)} schema differences." if diffs else "No differences found. Project is in sync with database."
        }

        if json_mode:
            print(json.dumps(res))
        else:
            if not diffs:
                rprint(f"[bold green]✓ Local {schema_dir.name}/ directory is completely in sync with the database![/bold green]")
                return

            table = Table(title=f"Schema Differences (Database vs {schema_dir.name}/)")
            table.add_column("Status", style="bold")
            table.add_column("Object Path", style="cyan")
            table.add_column("Action if Synced", style="yellow")

            for d in diffs:
                st = d["status"]
                if st == "ADDED_IN_DB":
                    st_str = "[bold green]ADDED_IN_DB[/bold green]"
                    action_str = "Create local file from DB"
                elif st == "MODIFIED":
                    st_str = "[bold yellow]MODIFIED[/bold yellow]"
                    action_str = "Update local file from DB"
                else:
                    st_str = "[bold red]DELETED_IN_DB[/bold red]"
                    action_str = "Delete local file (missing in DB)"
                table.add_row(st_str, d["rel_path"], action_str)

            console.print(table)
            rprint("\n[bold]Detailed SQL Diffs:[/bold]")
            for d in diffs:
                rprint(f"\n[bold cyan]• {d['rel_path']}[/bold cyan] ({d['status']}):")
                _print_colored_diff(d["diff"])
    except Exception as e:
        if json_mode:
            print(json.dumps({"success": False, "error": str(e), "message": f"Diff schema failed: {str(e)}"}))
            raise typer.Exit(code=0)
        else:
            rprint(f"[bold red]✗ Diff schema failed:[/bold red] {str(e)}")
            raise typer.Exit(code=1)

@app.command("sync")
def sync_schema_cmd(
    files: Optional[List[str]] = typer.Option(None, "--file", "-f", help="Relative path(s) in schemas/ to update from database"),
    apply_all: bool = typer.Option(False, "--all", "-a", help="Apply all detected differences without prompting"),
    json_mode: bool = typer.Option(False, "--json", help="Output result as JSON")
):
    """Compares database schemas with local project and updates user-selected differences in schemas/."""
    cfg_mgr = ConfigManager()
    db_url = get_db_url_or_exit(cfg_mgr, json_mode)
    cfg_data = cfg_mgr.load_config()

    try:
        schema_dir = Path.cwd() / cfg_data["schema_dir"]
        dumper = SchemaDumper(db_url, schema_dir)

        if not json_mode:
            with console.status(f"[bold cyan]Comparing PostgreSQL database against {schema_dir.name}/ folder...[/bold cyan]"):
                diffs = dumper.diff_schema()
        else:
            diffs = dumper.diff_schema()

        if not diffs:
            res = {
                "success": True,
                "message": "No differences found. Project is already in sync with database.",
                "written": [],
                "deleted": []
            }
            if json_mode:
                print(json.dumps(res))
            else:
                rprint(f"[bold green]✓ Local {schema_dir.name}/ directory is already in sync with the database![/bold green]")
            return

        selected_paths: List[str] = []

        if apply_all:
            selected_paths = [d["rel_path"] for d in diffs]
        elif files:
            for f_arg in files:
                for part in f_arg.split(","):
                    cleaned = part.strip()
                    if cleaned:
                        selected_paths.append(cleaned)
        elif not json_mode:
            rprint(f"[bold cyan]Found {len(diffs)} difference(s) between database and {schema_dir.name}/.[/bold cyan]")
            auto_accept_rest = False
            for idx, d in enumerate(diffs, start=1):
                rel_path = d["rel_path"]
                status = d["status"]
                rprint(f"\n[bold]({idx}/{len(diffs)}) [{status}] [cyan]{rel_path}[/cyan][/bold]")
                _print_colored_diff(d["diff"])

                if auto_accept_rest:
                    selected_paths.append(rel_path)
                    continue

                action_desc = "Delete local file" if status == "DELETED_IN_DB" else "Update local file from DB"
                choice = typer.prompt(
                    f"{action_desc} '{rel_path}'? [y = yes, n = no, a = all remaining, q = quit]",
                    default="n"
                ).strip().lower()

                if choice == "y":
                    selected_paths.append(rel_path)
                elif choice == "a":
                    selected_paths.append(rel_path)
                    auto_accept_rest = True
                elif choice == "q":
                    break

        applied = dumper.apply_selected_diffs(selected_paths, diffs=diffs)
        total_changed = len(applied["written"]) + len(applied["deleted"])

        res = {
            "success": True,
            "message": f"Updated {len(applied['written'])} file(s) and deleted {len(applied['deleted'])} file(s) in {schema_dir.name}/.",
            "written": applied["written"],
            "deleted": applied["deleted"],
            "total_changed": total_changed
        }

        if json_mode:
            print(json.dumps(res))
        else:
            if total_changed == 0:
                rprint("[bold yellow]No changes were applied to the project.[/bold yellow]")
            else:
                rprint(f"\n[bold green]✓ Synchronized {total_changed} schema object(s) in {schema_dir.name}/:[/bold green]")
                for w in applied["written"]:
                    rprint(f"  - [green]UPDATED[/green]: [cyan]{w}[/cyan]")
                for rm in applied["deleted"]:
                    rprint(f"  - [red]DELETED[/red]: [cyan]{rm}[/cyan]")
    except Exception as e:
        if json_mode:
            print(json.dumps({"success": False, "error": str(e), "message": f"Sync schema failed: {str(e)}"}))
            raise typer.Exit(code=0)
        else:
            rprint(f"[bold red]✗ Sync schema failed:[/bold red] {str(e)}")
            raise typer.Exit(code=1)

@app.command()
def plan(
    name: str = typer.Argument(..., help="Short description for the migration"),
    version_tag: Optional[str] = typer.Option(None, "--version", "-v", help="Migration project version tag (e.g. 0.1.0 or 0.2.0)"),
    json_mode: bool = typer.Option(False, "--json", help="Output result as JSON")
):
    """Generates timestamped migration files YYYYMMDDHHMMSS_name.up.sql and .down.sql."""
    cfg_mgr = ConfigManager()
    cfg_data = cfg_mgr.load_config()
    migrations_dir = Path.cwd() / cfg_data["migrations_dir"]
    schema_dir = Path.cwd() / cfg_data["schema_dir"]

    gen = MigrationGenerator(migrations_dir)
    
    if not json_mode:
        with console.status("[bold cyan]Analyzing schema dependencies & generating migration...[/bold cyan]"):
            up_sql = MigrationGenerator.read_all_schema_sql(schema_dir)
            down_sql = MigrationGenerator.generate_down_sql_from_schema(schema_dir)
            up_path, down_path, proj_ver = gen.generate_migration(name, up_sql=up_sql, down_sql=down_sql, project_version=version_tag)
    else:
        up_sql = MigrationGenerator.read_all_schema_sql(schema_dir)
        down_sql = MigrationGenerator.generate_down_sql_from_schema(schema_dir)
        up_path, down_path, proj_ver = gen.generate_migration(name, up_sql=up_sql, down_sql=down_sql, project_version=version_tag)

    up_rel = str(up_path.relative_to(Path.cwd()))
    down_rel = str(down_path.relative_to(Path.cwd()))

    res = {
        "success": True,
        "message": f"Generated migration files: {up_rel}, {down_rel}",
        "project_version": proj_ver,
        "up_file": up_rel,
        "down_file": down_rel
    }

    if json_mode:
        print(json.dumps(res))
    else:
        rprint(f"[bold green]✓ Migration generated successfully:[/bold green]")
        rprint(f"  - UP: [cyan]{up_rel}[/cyan]")
        rprint(f"  - DOWN: [cyan]{down_rel}[/cyan]")

@app.command("remove-migration")
@app.command("rm-migration")
def remove_migration(
    version: str = typer.Argument(..., help="Version timestamp or name of migration to remove"),
    json_mode: bool = typer.Option(False, "--json", help="Output result as JSON")
):
    """Removes local UP and DOWN migration files for a given version timestamp or name."""
    cfg_mgr = ConfigManager()
    cfg_data = cfg_mgr.load_config()
    migrations_dir = Path.cwd() / cfg_data["migrations_dir"]

    gen = MigrationGenerator(migrations_dir)
    deleted = gen.delete_migration(version)

    deleted_paths = [str(f.relative_to(Path.cwd())) for f in deleted]

    res = {
        "success": True if deleted else False,
        "message": f"Deleted {len(deleted)} migration files" if deleted else f"No migration files found matching '{version}'",
        "deleted_files": deleted_paths
    }

    if json_mode:
        print(json.dumps(res))
    else:
        if deleted:
            rprint(f"[bold green]✓ Deleted migration files:[/bold green]")
            for p in deleted_paths:
                rprint(f"  - [yellow]{p}[/yellow]")
        else:
            rprint(f"[bold red]✗ No migration files found matching '{version}'[/bold red]")

@app.command()
def validate(
    json_mode: bool = typer.Option(False, "--json", help="Output result as JSON")
):
    """Performs a dry-run execution of pending migrations inside an isolated transaction (BEGIN ... ROLLBACK)."""
    cfg_mgr = ConfigManager()
    db_url = get_db_url_or_exit(cfg_mgr, json_mode)
    cfg_data = cfg_mgr.load_config()
    migrations_dir = Path.cwd() / cfg_data["migrations_dir"]

    try:
        executor = MigrationExecutor(db_url, cfg_data["tracking_schema"], cfg_data["tracking_table"])
        if not json_mode:
            with console.status("[bold cyan]Validating pending migrations in test transaction (dry-run)...[/bold cyan]"):
                results = executor.validate_migrations_dry_run(migrations_dir)
        else:
            results = executor.validate_migrations_dry_run(migrations_dir)

        failed_item = next((item for item in results if item.get("status") == "FAILED"), None)
        success = failed_item is None

        res = {
            "success": success,
            "message": "Dry-run validation complete." if success else f"Dry-run validation failed: {failed_item.get('error')}",
            "error": failed_item.get("error") if failed_item else None,
            "results": results
        }

        if json_mode:
            print(json.dumps(res))
        else:
            if success:
                rprint("[bold green]✓ Migration Dry-Run Validation Result:[/bold green]")
                for item in results:
                    status_color = "green" if "VALIDATED" in item["status"] else "yellow"
                    rprint(f"  - [{status_color}]{item['version']}_{item['name']}[/{status_color}]: {item['status']}")
            else:
                rprint(f"[bold red]✗ Migration Dry-Run Validation Failed:[/bold red] {failed_item.get('error')}")
                raise typer.Exit(code=1)
    except Exception as e:
        if json_mode:
            print(json.dumps({"success": False, "error": str(e), "message": f"Dry-Run Validation Failed: {str(e)}"}))
            raise typer.Exit(code=0)
        else:
            rprint(f"[bold red]✗ Dry-Run Validation Failed:[/bold red] {str(e)}")
            raise typer.Exit(code=1)

@app.command()
def apply(
    json_mode: bool = typer.Option(False, "--json", help="Output result as JSON")
):
    """Applies all pending migrations to PostgreSQL database."""
    cfg_mgr = ConfigManager()
    db_url = get_db_url_or_exit(cfg_mgr, json_mode)
    cfg_data = cfg_mgr.load_config()
    migrations_dir = Path.cwd() / cfg_data["migrations_dir"]

    try:
        executor = MigrationExecutor(db_url, cfg_data["tracking_schema"], cfg_data["tracking_table"])
        executed = executor.apply_pending_migrations(migrations_dir)

        res = {
            "success": True,
            "message": f"Applied {len(executed)} migrations.",
            "executed_migrations": executed
        }

        if json_mode:
            print(json.dumps(res))
        else:
            if not executed:
                rprint("[bold yellow]No pending migrations to apply. Database is up-to-date.[/bold yellow]")
            else:
                rprint(f"[bold green]✓ Successfully applied {len(executed)} migrations:[/bold green]")
                for item in executed:
                    rprint(f"  - [cyan]{item['version']}_{item['name']}[/cyan] ({item['execution_time_ms']} ms)")
    except Exception as e:
        if json_mode:
            print(json.dumps({"success": False, "error": str(e), "message": f"Apply migrations failed: {str(e)}"}))
            raise typer.Exit(code=0)
        else:
            rprint(f"[bold red]✗ Apply migrations failed:[/bold red] {str(e)}")
            raise typer.Exit(code=1)

@app.command()
def status(
    json_mode: bool = typer.Option(False, "--json", help="Output result as JSON")
):
    """Displays status of applied and pending migrations."""
    cfg_mgr = ConfigManager()
    db_url = get_db_url_or_exit(cfg_mgr, json_mode)
    cfg_data = cfg_mgr.load_config()
    migrations_dir = Path.cwd() / cfg_data["migrations_dir"]

    manifest = ChecksumManager.get_migrations_manifest(migrations_dir)
    
    try:
        executor = MigrationExecutor(db_url, cfg_data["tracking_schema"], cfg_data["tracking_table"])
        applied = executor.get_applied_migrations()
    except Exception as e:
        res = {
            "success": False,
            "error": f"Could not connect to PostgreSQL database to check migration status: {str(e)}",
            "migrations": [
                {
                    "version": item["version"],
                    "name": item["name"],
                    "status": "UNKNOWN (DB Offline)",
                    "applied_at": None,
                    "up_checksum": item["up_checksum"]
                } for item in manifest
            ]
        }
        if json_mode:
            print(json.dumps(res))
        else:
            rprint(f"[bold yellow]Warning: Could not connect to PostgreSQL ({e})[/bold yellow]")
            rprint("[bold cyan]Local migrations found:[/bold cyan]")
            for item in manifest:
                rprint(f"  - {item['version']}_{item['name']} (Local file present)")
        return

    status_list = []
    for item in manifest:
        is_applied = item["version"] in applied
        status_list.append({
            "version": item["version"],
            "name": item["name"],
            "status": "APPLIED" if is_applied else "PENDING",
            "applied_at": applied[item["version"]]["applied_at"] if is_applied else None,
            "up_checksum": item["up_checksum"]
        })

    res = {
        "success": True,
        "total_migrations": len(manifest),
        "applied_count": len(applied),
        "pending_count": len([s for s in status_list if s["status"] == "PENDING"]),
        "migrations": status_list
    }

    if json_mode:
        print(json.dumps(res))
    else:
        table = Table(title="psqlmigr Migration Status")
        table.add_column("Version", style="cyan")
        table.add_column("Name", style="magenta")
        table.add_column("Status", style="bold")
        table.add_column("Applied At", style="green")

        for item in status_list:
            status_str = f"[bold green]APPLIED[/bold green]" if item["status"] == "APPLIED" else f"[bold yellow]PENDING[/bold yellow]"
            table.add_row(item["version"], item["name"], status_str, item["applied_at"] or "-")

        console.print(table)

@app.command()
def checksum(
    json_mode: bool = typer.Option(False, "--json", help="Output result as JSON")
):
    """Recalculates and displays SHA256 checksums for all migration files."""
    cfg_mgr = ConfigManager()
    cfg_data = cfg_mgr.load_config()
    migrations_dir = Path.cwd() / cfg_data["migrations_dir"]

    manifest = ChecksumManager.get_migrations_manifest(migrations_dir)

    res = {
        "success": True,
        "migrations": manifest
    }

    if json_mode:
        print(json.dumps(res))
    else:
        rprint("[bold green]✓ Calculated migration SHA256 checksums:[/bold green]")
        for item in manifest:
            rprint(f"  - [cyan]{item['version']}_{item['name']}[/cyan]")
            rprint(f"    UP Checksum:   [yellow]{item['up_checksum']}[/yellow]")
            if item["down_checksum"]:
                rprint(f"    DOWN Checksum: [yellow]{item['down_checksum']}[/yellow]")

if __name__ == "__main__":
    app()
