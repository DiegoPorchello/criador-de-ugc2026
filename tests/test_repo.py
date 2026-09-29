from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_every_copy_of_the_skill_matches_the_root_file():
    # Agents load the skill from these folders; a stale copy would give them outdated instructions.
    root = (ROOT / "SKILL.md").read_text(encoding="utf-8")
    for copy in (".claude/skills/ugc-forge/SKILL.md", ".agents/skills/ugc-forge/SKILL.md", "ugc_forge/skill/SKILL.md"):
        path = ROOT / copy
        assert not path.is_symlink(), f"{copy} must be a real file: symlinks break on Windows checkouts"
        assert path.read_text(encoding="utf-8") == root, f"{copy} is out of date; copy SKILL.md over it"


def test_skill_plugin_and_package_versions_agree():
    import json
    from ugc_forge import __version__
    assert f"ugc-forge {__version__}" in (ROOT / "SKILL.md").read_text(encoding="utf-8")
    assert json.loads((ROOT / ".claude-plugin/plugin.json").read_text())["version"] == __version__
    assert f'version = "{__version__}"' in (ROOT / "pyproject.toml").read_text()


def test_install_skill_writes_the_bundled_skill(tmp_path, monkeypatch):
    from argparse import Namespace
    from ugc_forge import cli
    monkeypatch.setattr(cli, "SKILL_TARGETS", (("Claude Code", str(tmp_path / "claude/SKILL.md")), ("Codex", str(tmp_path / "agents/SKILL.md"))))
    cli.cmd_install_skill(Namespace())
    root = (ROOT / "SKILL.md").read_text(encoding="utf-8")
    assert (tmp_path / "claude/SKILL.md").read_text(encoding="utf-8") == root == (tmp_path / "agents/SKILL.md").read_text(encoding="utf-8")
