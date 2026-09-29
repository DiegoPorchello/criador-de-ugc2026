import json
from argparse import Namespace
import pytest
from ugc_forge import aroll, cli, images, workflow
from ugc_forge.config import load_config
from ugc_forge.project import init_project


@pytest.fixture
def project(tmp_path, monkeypatch):
    p = tmp_path / "video"
    init_project(p)
    (p / "source/frame.jpg").write_bytes(b"frame")
    made = []

    def fake_image(inputs, prompt, cfg, output, aspect_ratio=None, model_key="image"):
        made.append([i.read_bytes() for i in inputs])
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(f"face {len(made)}".encode())
        return {"model": "gemini-3-pro-image", "image_output_tokens": 1120}

    monkeypatch.setattr(images, "generate_image", fake_image)
    monkeypatch.setattr(cli, "workspace_path", lambda cfg: tmp_path / "ws")
    return p, made


def args(p, **kw):
    base = dict(project=str(p), yes=True, max_cost=None, prompt=None, inputs=None, name=None, replace=False, plan=False,
                resolution=None, aspect_ratio=None, concurrency=None, max_retries=None)
    base.update(kw)
    return Namespace(**base)


def test_avatar_refuses_the_template_spec_and_keeps_every_version(project):
    p, made = project
    with pytest.raises(RuntimeError, match="template text"):
        cli.cmd_avatar(args(p))
    (p / "avatar/spec.md").write_text("A man in his thirties with glasses.")
    cli.cmd_avatar(args(p))
    cli.cmd_avatar(args(p, inputs=["avatar", "source"], prompt="Same man, in a kitchen."))  # a new Look
    assert made == [[b"frame"], [b"face 1", b"frame"]]
    cli.cmd_avatar_use(Namespace(project=str(p), version=1))
    assert (p / "avatar/reference.png").read_bytes() == b"face 1"
    costs = json.loads((p / "costs.json").read_text())
    assert costs["images"]["images"] == 2 and costs["images"]["reported_cost"]["display"] == "$0.27"


def test_max_cost_binds_yes_to_the_approved_amount(project):
    p, made = project
    (p / "config.yaml").write_text("provider: google\n")  # Google image prices are known
    (p / "avatar/spec.md").write_text("A man.")
    with pytest.raises(RuntimeError, match="more than the approved maximum \\$0.10"):
        cli.cmd_avatar(args(p, max_cost=0.10))
    assert made == []
    cli.cmd_avatar(args(p, max_cost=0.20))
    assert len(made) == 1


def test_stages_have_one_definition_and_old_files_migrate(project):
    p, _ = project
    assert workflow.load(p) == workflow.default()
    (p / "workflow.json").write_text(json.dumps({"focus": "creative_setup", "approved": {"concept": True, "creative_setup": True}}))
    assert workflow.load(p)["approved"]["concept"] is True and workflow.load(p)["stage"] == "source"
    cli.cmd_stage(Namespace(project=str(p), stage="beats"))
    cli.cmd_approve(Namespace(project=str(p), stage="beats", undo=False))
    st = workflow.load(p)
    assert st["stage"] == "beats" and st["approved"]["beats"] is True
    with pytest.raises(ValueError):
        workflow.set_stage(p, "focus")


def test_status_and_check_explain_the_project(project, capsys, monkeypatch):
    p, _ = project
    cli.cmd_status(Namespace(project=str(p)))
    out = capsys.readouterr().out
    assert "Stage: source" in out and "A-roll: 2 clip(s): 2 to generate" in out
    monkeypatch.setattr(cli.kie, "resolve_api_key", lambda kcfg: (_ for _ in ()).throw(RuntimeError("Missing kie.ai API key.")))
    with pytest.raises(RuntimeError, match="Setup is incomplete"):
        cli.cmd_check(Namespace(project=str(p), online=False))
    assert "kie.ai API key: MISSING" in capsys.readouterr().out


def test_series_attach_and_archive_guard_against_mistakes(project, tmp_path):
    p, _ = project
    with pytest.raises(RuntimeError, match="No series 'TV Talk'"):
        cli.cmd_attach_series(Namespace(project=str(p), series="TV Talk"))
    from ugc_forge.library import create_series
    create_series(tmp_path / "ws", "TV Talk")
    cli.cmd_attach_series(Namespace(project=str(p), series="TV Talk"))
    cli.cmd_archive(Namespace(project=str(p), series=None, title="One"))
    with pytest.raises(RuntimeError, match="already archived"):
        cli.cmd_archive(Namespace(project=str(p), series=None, title="One"))


def test_errors_name_the_beat_or_file_and_dialogue_can_be_any_language(project):
    p, _ = project
    cfg = load_config(p)
    (p / "beats.json").write_text('[{"id": "hook", "dialogue": "Hi"},]')
    with pytest.raises(ValueError, match="beats.json is not valid JSON \\(line 1"):
        aroll.plan(p, cfg)
    long_line = " ".join(["word"] * 40)
    (p / "beats.json").write_text(json.dumps([{"id": "rant", "dialogue": long_line}]))
    with pytest.raises(ValueError, match="^rant: Estimated speech"):
        aroll.plan(p, cfg)
    (p / "beats.json").write_text(json.dumps([{"id": "hola", "dialogue": "¿Por qué está tan alta la tele? 为什么"}], ensure_ascii=False), encoding="utf-8")
    assert aroll.plan(p, cfg)["rows"][0]["dialogue"].endswith("为什么")


def test_setup_saves_the_key_privately_and_it_is_used(tmp_path, monkeypatch):
    import getpass, os, stat
    cfg_file = tmp_path / "home/.ugc-forge/config.yaml"
    monkeypatch.setattr(cli, "shared_config_path", lambda: None)
    monkeypatch.setattr(cli, "shared_config_candidates", lambda: [cfg_file])
    monkeypatch.setattr(getpass, "getpass", lambda prompt: "  secret-key \n")
    checked = []
    monkeypatch.setattr(cli, "cmd_check", lambda a: checked.append(a.online))
    cli.cmd_setup(Namespace(provider="google", from_clipboard=False))
    import yaml
    data = yaml.safe_load(cfg_file.read_text())
    assert data["provider"] == "google"
    assert data["generation_models"]["video"]["api_key"] == "secret-key" == data["generation_models"]["image"]["api_key"]
    import builtins
    monkeypatch.setattr(builtins, "input", lambda prompt: "")  # Enter picks the recommended option
    cli.cmd_setup(Namespace(provider=None, from_clipboard=False))
    data = yaml.safe_load(cfg_file.read_text())
    assert data["provider"] == "kie" and data["kie"]["api_key"] == "secret-key"
    assert data["generation_models"]["video"]["api_key"] == "secret-key"  # the Google key is kept
    if os.name == "posix":
        assert stat.S_IMODE(cfg_file.stat().st_mode) == 0o600
    assert checked == [True, True]


def test_setup_can_take_the_key_from_the_clipboard_when_typing_is_impossible(tmp_path, monkeypatch):
    import getpass, yaml
    cfg_file = tmp_path / "config.yaml"
    monkeypatch.setattr(cli, "shared_config_path", lambda: None)
    monkeypatch.setattr(cli, "shared_config_candidates", lambda: [cfg_file])
    monkeypatch.setattr(cli, "cmd_check", lambda a: None)
    def no_tty(prompt): raise EOFError
    monkeypatch.setattr(getpass, "getpass", no_tty)
    with pytest.raises(RuntimeError, match="--from-clipboard"):
        cli.cmd_setup(Namespace(provider="kie", from_clipboard=False))
    assert not cfg_file.exists()
    board = {"text": "not a key"}
    monkeypatch.setattr(cli, "_clipboard", lambda clear=False: board.update(text="") or "" if clear else board["text"])
    with pytest.raises(RuntimeError, match="doesn't hold an API key"):
        cli.cmd_setup(Namespace(provider="kie", from_clipboard=True))
    board["text"] = "kie-abcdef0123456789\n"
    cli.cmd_setup(Namespace(provider="kie", from_clipboard=True))
    assert yaml.safe_load(cfg_file.read_text())["kie"]["api_key"] == "kie-abcdef0123456789" and board["text"] == ""
