"""Smoke: reference/ knowledge files are parseable.

Tolerant of an empty reference/ dir — activates as design docs are migrated in.
Every .md that exists must be non-empty and lead with a level-1 heading.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REFERENCE_DIR = ROOT / "reference"


def _reference_md_files():
    if not REFERENCE_DIR.is_dir():
        return []
    return sorted(REFERENCE_DIR.glob("*.md"))


def test_reference_files_nonempty_with_title():
    for md in _reference_md_files():
        text = md.read_text(encoding="utf-8").strip()
        assert text, f"{md.name} is empty"
        first = text.splitlines()[0].strip()
        assert first.startswith("# "), f"{md.name}: first line must be a '# ' title"
