"""Smoke: config resolution + eval-state parsers (CRUD-read roundtrips)."""

import pytest

from tools.shared import config as config_mod
from tools.state import parsers

REQUIRED_CONFIG_KEYS = {
    "docsBase",
    "skillEvalsDir",
    "workflowScriptPath",
    "referenceDir",
    "pluginRoot",
    "configFile",
    "configExists",
}

STATUS_FIXTURE = """# demo rollout status

Some prose that should be ignored by the parser.

| Skill | Simulated | Live | Notes |
|---|---|---|---|
| alpha | ✅ 47/47 (1.0) | 🟦 N/A | fully done via N/A live |
| beta | ✅ 30/30 (1.0) | ✅ 12/12 | fully done, live passed |
| gamma | ✅ 20/20 | ⬜ | simulated done, live open |
| delta | ⬜ | 🟦 N/A | not started |

**4 skills total.**
"""


def test_resolve_config_has_all_keys_and_forward_slashes():
    cfg = config_mod.resolve_config()
    assert REQUIRED_CONFIG_KEYS <= set(cfg)
    # Every path is forward-slash, never a Windows backslash.
    for key in ("docsBase", "skillEvalsDir", "workflowScriptPath", "pluginRoot"):
        assert "\\" not in cfg[key], f"{key} must be forward-slash: {cfg[key]}"
    assert cfg["workflowScriptPath"].endswith("/workflows/skill-rollout.js")
    assert cfg["configExists"] in ("true", "false")


def _point_parsers_at(tmp_path, monkeypatch):
    """Redirect the parsers' skillEvalsDir to a temp dir."""
    resolved = config_mod.resolve_config()
    resolved["skillEvalsDir"] = str(tmp_path)
    monkeypatch.setattr(parsers, "resolve_config", lambda: resolved)


def test_list_evals_parses_table_and_derives_fully_done(tmp_path, monkeypatch):
    _point_parsers_at(tmp_path, monkeypatch)
    plugin_dir = tmp_path / "demo"
    plugin_dir.mkdir()
    (plugin_dir / "STATUS.md").write_text(STATUS_FIXTURE, encoding="utf-8")

    res = parsers.list_evals("demo")
    assert res["exists"] is True
    by_name = {s["name"]: s for s in res["skills"]}
    assert set(by_name) == {"alpha", "beta", "gamma", "delta"}
    # fullyDone: ✅ simulated AND (✅ or N/A live)
    assert by_name["alpha"]["fullyDone"] is True
    assert by_name["beta"]["fullyDone"] is True
    assert by_name["gamma"]["fullyDone"] is False  # live still ⬜
    assert by_name["delta"]["fullyDone"] is False  # simulated ⬜
    assert res["counts"] == {"total": 4, "fullyDone": 2, "notDone": 2}


def test_list_evals_missing_plugin_returns_not_onboarded(tmp_path, monkeypatch):
    _point_parsers_at(tmp_path, monkeypatch)
    res = parsers.list_evals("never-onboarded")
    assert res["exists"] is False
    assert res["skills"] == []
    assert "message" in res


def test_get_batch_status_roundtrip(tmp_path, monkeypatch):
    _point_parsers_at(tmp_path, monkeypatch)
    plugin_dir = tmp_path / "demo"
    plugin_dir.mkdir()
    (plugin_dir / "batch-digest.md").write_text(
        "## Batch started\nhello", encoding="utf-8"
    )

    res = parsers.get_batch_status("demo")
    assert res["exists"] is True
    assert "Batch started" in res["content"]

    missing = parsers.get_batch_status("demo-none")
    assert missing["exists"] is False
    assert missing["content"] == ""


def test_get_eval_state_roundtrip(tmp_path, monkeypatch):
    _point_parsers_at(tmp_path, monkeypatch)
    skill_dir = tmp_path / "demo" / "alpha"
    skill_dir.mkdir(parents=True)
    (skill_dir / "loop-state.json").write_text('{"iteration": 3}', encoding="utf-8")
    (skill_dir / "loop-log.md").write_text("line1\nline2\nline3\n", encoding="utf-8")

    res = parsers.get_eval_state("demo", "alpha")
    assert res["loopStateExists"] is True
    assert res["loopState"] == {"iteration": 3}
    assert "line3" in res["loopLogTail"]

    fresh = parsers.get_eval_state("demo", "unseen")
    assert fresh["loopStateExists"] is False
    assert fresh["loopLogExists"] is False
    assert "message" in fresh


@pytest.mark.parametrize("bad", ["../evil", "a/b", "..", "Upper", "with space", ""])
def test_parsers_reject_path_traversal_slugs(tmp_path, monkeypatch, bad):
    _point_parsers_at(tmp_path, monkeypatch)
    with pytest.raises(ValueError):
        parsers.list_evals(bad)
    with pytest.raises(ValueError):
        parsers.get_eval_state("demo", bad)


def test_load_config_tolerates_malformed_yaml(tmp_path, monkeypatch):
    bad_cfg = tmp_path / "config.yaml"
    bad_cfg.write_text("paths: [unclosed\n", encoding="utf-8")
    monkeypatch.setattr(config_mod, "CONFIG_FILE", bad_cfg)
    # Must fall back to {} (→ defaults), never raise.
    assert config_mod.load_config() == {}


def test_get_eval_state_tolerates_corrupt_json(tmp_path, monkeypatch):
    _point_parsers_at(tmp_path, monkeypatch)
    skill_dir = tmp_path / "demo" / "broken"
    skill_dir.mkdir(parents=True)
    (skill_dir / "loop-state.json").write_text("{ not valid json ", encoding="utf-8")

    res = parsers.get_eval_state("demo", "broken")
    assert res["loopState"] is None
    assert "loopStateError" in res
