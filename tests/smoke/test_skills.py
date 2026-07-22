"""Smoke: skill frontmatter is valid.

Tolerant of a not-yet-populated skills/ dir — activates as skills land. Every
SKILL.md that DOES exist must have valid frontmatter with the required fields,
a name matching its directory, and (if present) a known model id.
"""

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
SKILLS_DIR = ROOT / "skills"

# Current Claude model ids (see plugin knowledge). Skills may omit `model`.
VALID_MODELS = {
    "claude-opus-4-8",
    "claude-sonnet-5",
    "claude-haiku-4-5-20251001",
    "claude-fable-5",
}

REQUIRED_FIELDS = {"name", "description"}


def _skill_md_files():
    if not SKILLS_DIR.is_dir():
        return []
    return sorted(SKILLS_DIR.glob("*/SKILL.md"))


def _parse_frontmatter(text: str) -> dict:
    assert text.startswith("---"), "SKILL.md must start with YAML frontmatter"
    _, fm, _body = text.split("---", 2)
    data = yaml.safe_load(fm)
    assert isinstance(data, dict), "frontmatter must parse to a mapping"
    return data


def test_no_nested_skill_dirs():
    """Skills live exactly one level deep (skills/{name}/SKILL.md). A grouping
    subdir like skills/core/{name}/SKILL.md silently fails to load."""
    if not SKILLS_DIR.is_dir():
        return
    for nested in SKILLS_DIR.glob("*/*/SKILL.md"):
        raise AssertionError(
            f"nested skill will not load: {nested.relative_to(ROOT)} "
            "(skills must be exactly one level deep)"
        )


def test_every_skill_dir_has_a_skill_md():
    if not SKILLS_DIR.is_dir():
        return
    for child in SKILLS_DIR.iterdir():
        if child.is_dir():
            assert (child / "SKILL.md").is_file(), f"{child.name}/ has no SKILL.md"


def test_skill_frontmatter_valid_and_unique():
    seen = set()
    for skill_md in _skill_md_files():
        data = _parse_frontmatter(skill_md.read_text(encoding="utf-8"))
        missing = REQUIRED_FIELDS - set(data)
        assert not missing, f"{skill_md.parent.name}: missing frontmatter {missing}"

        name = data["name"]
        assert name == skill_md.parent.name, (
            f"{skill_md}: frontmatter name '{name}' != dir '{skill_md.parent.name}'"
        )
        assert name not in seen, f"duplicate skill name '{name}'"
        seen.add(name)

        if "model" in data:
            assert data["model"] in VALID_MODELS, (
                f"{name}: unknown model id '{data['model']}'"
            )
