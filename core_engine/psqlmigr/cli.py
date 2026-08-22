import sys
import json
from pathlib import Path
from typing import Optional

# Ensure UTF-8 output encoding on Windows console
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
    """Reverse-engineers PostgreSQL database and dumps DDL SQL files into schema/<schema_name>/<object_type>/<object_name>.sql."""
    cfg_mgr = ConfigManager()
    db_url = get_db_url_or_exit(cfg_mgr, json_mode)
    cfg_data = cfg_mgr.load_config()

    schema_dir = Path.cwd() / cfg_data["schema_dir"]
    dumper = SchemaDumper(db_url, schema_dir)
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

@app.command()
def plan(
    name: str = typer.Argument(..., help="Short description for the migration"),
    json_mode: bool = typer.Option(False, "--json", help="Output result as JSON")
):
    """Generates timestamped migration files YYYYMMDDHHMMSS_name.up.sql and .down.sql."""
    cfg_mgr = ConfigManager()
    cfg_data = cfg_mgr.load_config()
    migrations_dir = Path.cwd() / cfg_data["migrations_dir"]
    schema_dir = Path.cwd() / cfg_data["schema_dir"]

    gen = MigrationGenerator(migrations_dir)
    up_sql = MigrationGenerator.read_all_schema_sql(schema_dir)
    up_path, down_path = gen.generate_migration(name, up_sql=up_sql)

    up_rel = str(up_path.relative_to(Path.cwd()))
    down_rel = str(down_path.relative_to(Path.cwd()))

    res = {
        "success": True,
        "message": f"Generated migration files: {up_rel}, {down_rel}",
        "up_file": up_rel,
        "down_file": down_rel
    }

    if json_mode:
        print(json.dumps(res))
    else:
        rprint(f"[bold green]✓ Migration generated successfully:[/bold green]")
        rprint(f"  - UP: [cyan]{up_rel}[/cyan]")
        rprint(f"  - DOWN: [cyan]{down_rel}[/cyan]")

@app.command()
def validate(
    json_mode: bool = typer.Option(False, "--json", help="Output result as JSON")
):
    """Performs a dry-run execution of pending migrations inside an isolated transaction (BEGIN ... ROLLBACK)."""
    cfg_mgr = ConfigManager()
    db_url = get_db_url_or_exit(cfg_mgr, json_mode)
    cfg_data = cfg_mgr.load_config()
    migrations_dir = Path.cwd() / cfg_data["migrations_dir"]

    executor = MigrationExecutor(db_url, cfg_data["tracking_schema"], cfg_data["tracking_table"])
    results = executor.validate_migrations_dry_run(migrations_dir)

    res = {
        "success": True,
        "message": "Dry-run validation complete.",
        "results": results
    }

    if json_mode:
        print(json.dumps(res))
    else:
        rprint("[bold green]✓ Migration Dry-Run Validation Result:[/bold green]")
        for item in results:
            status_color = "green" if "VALIDATED" in item["status"] else "yellow"
            rprint(f"  - [{status_color}]{item['version']}_{item['name']}[/{status_color}]: {item['status']}")

@app.command()
def apply(
    json_mode: bool = typer.Option(False, "--json", help="Output result as JSON")
):
    """Applies all pending migrations to PostgreSQL database."""
    cfg_mgr = ConfigManager()
    db_url = get_db_url_or_exit(cfg_mgr, json_mode)
    cfg_data = cfg_mgr.load_config()
    migrations_dir = Path.cwd() / cfg_data["migrations_dir"]

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
