"""Read-only parsers for per-plugin skill-eval state.

All state lives in Markdown/JSON under {skillEvalsDir}/{plugin}/ — this module
reads it, never writes it. Tolerant by design: a half-written STATUS.md or a
missing file returns a structured "not there yet" result, never an exception,
so the calling skill can decide what to do.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from tools.shared.config import resolve_config

# STATUS.md status markers (see {skillEvalsDir}/schema.md).
_DONE = "✅"
_NA = "🟦"
_NOT_STARTED = "⬜"


def _plugin_dir(plugin: str) -> Path:
    """Return {skillEvalsDir}/{plugin} as an absolute Path."""
    return Path(resolve_config()["skillEvalsDir"]) / plugin


def _is_fully_done(simulated: str, live: str) -> bool:
    """A skill is fully done when simulated is ✅ AND live is ✅ or a verified N/A."""
    sim_done = _DONE in simulated
    live_done = _DONE in live or _NA in live
    return sim_done and live_done


def _parse_status_table(text: str) -> list[dict[str, Any]]:
    """Extract skill rows from a STATUS.md markdown table.

    Table shape: | Skill | Simulated | Live | Notes |. The header row and the
    |---|---| separator are skipped; anything that isn't a 4-column data row is
    ignored, so surrounding prose doesn't confuse the parser.
    """
    rows: list[dict[str, Any]] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        # Split on |, dropping the empty leading/trailing cells.
        cells = [c.strip() for c in stripped.strip("|").split("|")]
        if len(cells) < 4:
            continue
        name, simulated, live, notes = cells[0], cells[1], cells[2], cells[3]
        # Skip header + separator rows.
        if name.lower() == "skill" or set(name) <= {"-", ":"}:
            continue
        rows.append(
            {
                "name": name,
                "simulated": simulated,
                "live": live,
                "notes": notes,
                "fullyDone": _is_fully_done(simulated, live),
            }
        )
    return rows


def list_evals(plugin: str) -> dict[str, Any]:
    """List the eval status of every skill for a plugin from its STATUS.md."""
    status_file = _plugin_dir(plugin) / "STATUS.md"
    if not status_file.exists():
        return {
            "plugin": plugin,
            "exists": False,
            "statusFile": status_file.as_posix(),
            "skills": [],
            "message": (
                f"No STATUS.md for '{plugin}' — plugin not onboarded yet "
                f"(expected at {status_file.as_posix()})."
            ),
        }
    text = status_file.read_text(encoding="utf-8")
    skills = _parse_status_table(text)
    return {
        "plugin": plugin,
        "exists": True,
        "statusFile": status_file.as_posix(),
        "skills": skills,
        "counts": {
            "total": len(skills),
            "fullyDone": sum(1 for s in skills if s["fullyDone"]),
            "notDone": sum(1 for s in skills if not s["fullyDone"]),
        },
    }


def get_batch_status(plugin: str) -> dict[str, Any]:
    """Return the running batch digest (batch-digest.md) for a plugin verbatim."""
    digest_file = _plugin_dir(plugin) / "batch-digest.md"
    if not digest_file.exists():
        return {
            "plugin": plugin,
            "exists": False,
            "digestFile": digest_file.as_posix(),
            "content": "",
            "message": f"No batch-digest.md yet for '{plugin}' — no batch has run.",
        }
    return {
        "plugin": plugin,
        "exists": True,
        "digestFile": digest_file.as_posix(),
        "content": digest_file.read_text(encoding="utf-8"),
    }


def get_eval_state(plugin: str, skill: str, log_tail_lines: int = 60) -> dict[str, Any]:
    """Return loop-state.json (parsed) + the tail of loop-log.md for one skill."""
    skill_dir = _plugin_dir(plugin) / skill
    state_file = skill_dir / "loop-state.json"
    log_file = skill_dir / "loop-log.md"

    result: dict[str, Any] = {
        "plugin": plugin,
        "skill": skill,
        "skillDir": skill_dir.as_posix(),
        "loopStateExists": state_file.exists(),
        "loopLogExists": log_file.exists(),
        "loopState": None,
        "loopLogTail": "",
    }

    if state_file.exists():
        try:
            result["loopState"] = json.loads(state_file.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            result["loopState"] = None
            result["loopStateError"] = f"loop-state.json is not valid JSON: {exc}"

    if log_file.exists():
        lines = log_file.read_text(encoding="utf-8").splitlines()
        result["loopLogTail"] = "\n".join(lines[-log_tail_lines:])

    if not state_file.exists() and not log_file.exists():
        result["message"] = (
            f"No prior loop state for '{skill}' in '{plugin}' — fresh start."
        )

    return result
