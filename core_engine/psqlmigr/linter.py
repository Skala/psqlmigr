import re
from typing import List, Dict, Any

DESTRUCTIVE_PATTERNS = [
    (r"\bDROP\s+TABLE\b", "HIGH", "DROP TABLE statement detected. Data will be permanently lost."),
    (r"\bDROP\s+COLUMN\b", "HIGH", "DROP COLUMN statement detected. Column data will be permanently lost."),
    (r"\bTRUNCATE\b", "CRITICAL", "TRUNCATE statement detected. All table rows will be cleared."),
    (r"\bDROP\s+SCHEMA\b", "CRITICAL", "DROP SCHEMA statement detected."),
    (r"\bALTER\s+TABLE\b.*\bDROP\b", "HIGH", "ALTER TABLE ... DROP constraint or column statement detected."),
]

class MigrationLinter:
    @staticmethod
    def lint_sql(sql_content: str) -> List[Dict[str, Any]]:
        warnings = []
        lines = sql_content.splitlines()

        for idx, line in enumerate(lines, 1):
            # Skip full line comments
            if line.strip().startswith("--") or line.strip().startswith("/*"):
                continue

            for pattern, severity, message in DESTRUCTIVE_PATTERNS:
                if re.search(pattern, line, re.IGNORECASE):
                    warnings.append({
                        "line": idx,
                        "content": line.strip(),
                        "severity": severity,
                        "message": message
                    })

        return warnings
