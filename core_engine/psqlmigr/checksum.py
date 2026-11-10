import hashlib
from pathlib import Path
from typing import Dict, List, Tuple, Any

def parse_version_and_name(version_name: str) -> Tuple[str, str, str]:
    parts = version_name.split("_")
    if len(parts) >= 3 and parts[0].startswith("v") and parts[1].isdigit():
        version = f"{parts[0]}_{parts[1]}"
        project_ver = parts[0].lstrip("v")
        name = "_".join(parts[2:])
        return version, name or version_name, project_ver
    version, _, name = version_name.partition("_")
    return version, name or version_name, ""

class ChecksumManager:
    @staticmethod
    def calculate_file_checksum(file_path: Path) -> str:
        if not file_path.exists():
            raise FileNotFoundError(f"Migration file not found: {file_path}")
        
        hasher = hashlib.sha256()
        with open(file_path, "rb") as f:
            while chunk := f.read(8192):
                hasher.update(chunk)
        return hasher.hexdigest()

    @staticmethod
    def calculate_string_checksum(content: str) -> str:
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    @classmethod
    def get_migrations_manifest(cls, migrations_dir: Path) -> List[Dict[str, Any]]:
        """
        Scans migrations directory (both migrations/up/ & migrations/down/ subfolders,
        as well as legacy root files) and returns list of migration metadata.
        """
        if not migrations_dir.exists():
            return []

        migrations_by_version: Dict[str, Dict[str, Any]] = {}

        # 1. Scan migrations/up/
        up_dir = migrations_dir / "up"
        if up_dir.exists():
            for file_path in sorted(up_dir.glob("*.sql")):
                filename = file_path.name
                version_name = filename[:-4] if filename.endswith(".sql") else filename
                version, name, proj_ver = parse_version_and_name(version_name)
                entry = migrations_by_version.setdefault(version, {
                    "version": version,
                    "name": name,
                    "project_version": proj_ver,
                    "up_file": file_path,
                    "down_file": None,
                    "up_checksum": "",
                    "down_checksum": ""
                })
                entry["up_file"] = file_path
                entry["up_checksum"] = cls.calculate_file_checksum(file_path)

        # 2. Scan migrations/down/
        down_dir = migrations_dir / "down"
        if down_dir.exists():
            for file_path in sorted(down_dir.glob("*.sql")):
                filename = file_path.name
                version_name = filename[:-4] if filename.endswith(".sql") else filename
                version, name, proj_ver = parse_version_and_name(version_name)
                entry = migrations_by_version.setdefault(version, {
                    "version": version,
                    "name": name,
                    "project_version": proj_ver,
                    "up_file": None,
                    "down_file": file_path,
                    "up_checksum": "",
                    "down_checksum": ""
                })
                entry["down_file"] = file_path
                entry["down_checksum"] = cls.calculate_file_checksum(file_path)

        # 3. Fallback scan root migrations/ directory for legacy .up.sql / .down.sql files
        for file_path in sorted(migrations_dir.glob("*.sql")):
            filename = file_path.name
            if filename.endswith(".up.sql"):
                version_name = filename[:-7]
                version, name, proj_ver = parse_version_and_name(version_name)
                entry = migrations_by_version.setdefault(version, {
                    "version": version,
                    "name": name,
                    "project_version": proj_ver,
                    "up_file": file_path,
                    "down_file": None,
                    "up_checksum": "",
                    "down_checksum": ""
                })
                if not entry["up_file"]:
                    entry["up_file"] = file_path
                    entry["up_checksum"] = cls.calculate_file_checksum(file_path)

            elif filename.endswith(".down.sql"):
                version_name = filename[:-9]
                version, name, proj_ver = parse_version_and_name(version_name)
                entry = migrations_by_version.setdefault(version, {
                    "version": version,
                    "name": name,
                    "project_version": proj_ver,
                    "up_file": None,
                    "down_file": file_path,
                    "up_checksum": "",
                    "down_checksum": ""
                })
                if not entry["down_file"]:
                    entry["down_file"] = file_path
                    entry["down_checksum"] = cls.calculate_file_checksum(file_path)

        result = []
        for ver in sorted(migrations_by_version.keys()):
            item = migrations_by_version[ver]
            up_rel = str(item["up_file"].relative_to(migrations_dir)) if item["up_file"] else ""
            down_rel = str(item["down_file"].relative_to(migrations_dir)) if item["down_file"] else ""
            result.append({
                "version": item["version"],
                "name": item["name"],
                "project_version": item.get("project_version", ""),
                "up_file": up_rel,
                "down_file": down_rel,
                "up_checksum": item["up_checksum"],
                "down_checksum": item["down_checksum"]
            })
        return result
