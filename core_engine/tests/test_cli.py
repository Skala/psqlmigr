import pytest
from pathlib import Path
from typer.testing import CliRunner
from psqlmigr.cli import app

runner = CliRunner()

def test_version_command():
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert "psqlmigr-core" in result.stdout

def test_init_command(tmp_path: Path):
    result = runner.invoke(app, ["init", "--dir", str(tmp_path)])
    assert result.exit_code == 0
    assert (tmp_path / "psqlmigr.yaml").exists()
    assert (tmp_path / ".env").exists()
    assert (tmp_path / "schema").exists()
    assert (tmp_path / "migrations").exists()

def test_plan_command(tmp_path: Path, monkeypatch):
    # Initialize project first
    runner.invoke(app, ["init", "--dir", str(tmp_path)])
    monkeypatch.chdir(tmp_path)
    
    result = runner.invoke(app, ["plan", "create_users_table"])
    assert result.exit_code == 0
    
    migrations = list((tmp_path / "migrations").glob("*.sql"))
    assert len(migrations) == 2  # .up.sql and .down.sql
