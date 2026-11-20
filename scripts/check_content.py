"""Fail (exit 1) if any content entry is unverified or lacks a real source link.

Usage: python scripts/check_content.py [data_dir]
"""

import json
import sys
from pathlib import Path

from pydantic import BaseModel, ConfigDict, ValidationError, field_validator

CONTENT_FILES = ["jobs.json", "finance.json", "stories.json", "courses.json"]


class ContentEntry(BaseModel):
    """Every content entry needs these two fields. Other fields are checked per file."""

    model_config = ConfigDict(extra="allow")

    verified: bool
    source_url: str

    @field_validator("source_url")
    @classmethod
    def must_be_https(cls, value: str) -> str:
        if not value.startswith("https://"):
            raise ValueError(f"source_url must start with https:// (got {value!r})")
        return value


def check_file(path: Path) -> list[str]:
    """Return a list of problems for one content file. An empty list means it passes."""
    problems: list[str] = []
    try:
        entries = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [f"{path.name}: cannot read file ({exc})"]
    if not isinstance(entries, list):
        return [f"{path.name}: top level must be a list"]

    for index, entry in enumerate(entries, start=1):
        label = f"{path.name} entry {index} ({entry.get('title', '?') if isinstance(entry, dict) else '?'})"
        try:
            ContentEntry.model_validate(entry)
        except ValidationError as exc:
            for err in exc.errors():
                loc = ".".join(str(part) for part in err["loc"]) or "entry"
                problems.append(f"{label}: {loc}: {err['msg']}")
        # Report unverified entries even when the schema check also failed.
        if isinstance(entry, dict) and entry.get("verified") is False:
            problems.append(f"{label}: verified is false")
    return problems


def check_all(data_dir: Path) -> list[str]:
    problems: list[str] = []
    for name in CONTENT_FILES:
        path = data_dir / name
        if path.exists():
            problems.extend(check_file(path))
    return problems


def main(argv: list[str]) -> int:
    root = Path(__file__).resolve().parent.parent
    data_dir = Path(argv[1]) if len(argv) > 1 else root / "data"
    problems = check_all(data_dir)
    if problems:
        print(f"Content check FAILED: {len(problems)} problem(s)")
        for problem in problems:
            print(f"  - {problem}")
        return 1
    print("Content check passed: every entry is verified with a source link.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
