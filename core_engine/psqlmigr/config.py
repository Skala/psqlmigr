import os
from pathlib import Path
from typing import Dict, Any, Optional
import yaml
from dotenv import load_dotenv, set_key, find_dotenv

from urllib.parse import quote_plus

CONFIG_FILENAME = "psqlmigr.yaml"
ENV_FILENAME = ".env"

DEFAULT_CONFIG: Dict[str, Any] = {
    "version": "0.1.0",
    "schema_dir": "schemas",
    "migrations_dir": "migrations",
    "tracking_schema": "psqlmigr",
    "tracking_table": "schema_migrations",
    "default_schema": "public",
}

class ConfigManager:
    def __init__(self, root_dir: Optional[Path] = None):
        self.root_dir = root_dir or Path.cwd()
        self.config_path = self.root_dir / CONFIG_FILENAME
        self.env_path = self.root_dir / ENV_FILENAME
        self._load_env()

    def _load_env(self) -> None:
        if self.env_path.exists():
            load_dotenv(self.env_path, override=True)
        else:
            load_dotenv(override=True)

    def load_config(self) -> Dict[str, Any]:
        config = DEFAULT_CONFIG.copy()
        if self.config_path.exists():
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    user_cfg = yaml.safe_load(f) or {}
                    config.update(user_cfg)
            except Exception as e:
                print(f"Warning: Could not parse {self.config_path}: {e}")
        return config

    def save_config(self, config_data: Dict[str, Any]) -> None:
        with open(self.config_path, "w", encoding="utf-8") as f:
            yaml.dump(config_data, f, default_flow_style=False, sort_keys=False)

    def get_database_url(self) -> Optional[str]:
        # Priority 1: DATABASE_URL variable
        url = os.getenv("DATABASE_URL")
        if url:
            return url

        # Priority 2: Individual variables
        host = os.getenv("POSTGRES_HOST") or os.getenv("PGHOST")
        port = os.getenv("POSTGRES_PORT") or os.getenv("PGPORT") or "5432"
        user = os.getenv("POSTGRES_USER") or os.getenv("PGUSER")
        password = os.getenv("POSTGRES_PASSWORD") or os.getenv("PGPASSWORD")
        db = os.getenv("POSTGRES_DB") or os.getenv("PGDATABASE")
        sslmode = os.getenv("POSTGRES_SSLMODE") or os.getenv("PGSSLMODE")

        if host and user and db:
            user_enc = quote_plus(user)
            pass_enc = f":{quote_plus(password)}" if password else ""
            db_enc = quote_plus(db)
            ssl_str = f"?sslmode={sslmode}" if sslmode else ""
            return f"postgresql://{user_enc}{pass_enc}@{host}:{port}/{db_enc}{ssl_str}"

        return None

    def update_env(self, env_vars: Dict[str, str]) -> None:
        if not self.env_path.exists():
            self.env_path.touch()
        
        for key, value in env_vars.items():
            set_key(self.env_path, key, value)
        
        self._load_env()
