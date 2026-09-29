"""Fixes for the 2026-09-30 code review."""
import copy
import json
import threading
import time
from argparse import Namespace
import pytest
from ugc_forge import aroll, calibration, cli, costs, jobs
from ugc_forge.config import DEFAULTS, load_config
from ugc_forge.project import init_project


@pytest.fixture
def project(tmp_path, monkeypatch):
    p = tmp_path / "video"; init_project(p)
    (p / "avatar/reference.png").write_bytes(b"avatar")
    (p / "config.yaml").write_text((p / "config.yaml").read_text().replace("retry_delay_seconds: 5", "retry_delay_seconds: 0"))
    calls = {"video": [], "hook": None}
    def fake_video(prompt, reference, cfg, duration, output, on_submitted=None):
        calls["video"].append(prompt)
        if on_submitted: on_submitted(f"j{len(calls['video'])}")
        if calls["hook"]: calls["hook"]()
        output.parent.mkdir(parents=True, exist_ok=True); output.write_bytes(prompt.encode())
        return {"interaction_id": "j", "credits": 63}
    monkeypatch.setattr(jobs, "generate_video", fake_video)
    return p, calls


def gen(p, **kw):
    args = dict(project=str(p), yes=True, max_cost=None, resolution=None, aspect_ratio=None, concurrency=1, max_retries=None, redo=None)
    args.update(kw); cli.cmd_generate(Namespace(**args))


def test_a_paid_kie_image_survives_a_flaky_download(monkeypatch, tmp_path):
    from ugc_forge.providers import kie
    cfg = copy.deepcopy(DEFAULTS); cfg["kie"]["api_key"] = "k"
    replies = iter([{"downloadUrl": "https://tmp/a"}, {"taskId": "t"}, {"state": "success", "resultJson": '{"resultUrls":["u"]}', "creditsConsumed": 18}])
    monkeypatch.setattr(kie, "_request", lambda *a, **k: next(replies))
    tries = {"n": 0}
    def flaky(cfg, url):
        tries["n"] += 1
        if tries["n"] < 3: raise ConnectionError("reset")
        return b"\x89PNG ok"
    monkeypatch.setattr(kie, "_download", flaky); monkeypatch.setattr(kie, "_POLL_SECONDS", 0)
    src = tmp_path / "in.png"; src.write_bytes(b"x")
    kie.generate_image([src], "p", cfg, tmp_path / "out.png", sleep=lambda s: None)
    assert tries["n"] == 3 and (tmp_path / "out.png").read_bytes().startswith(b"\x89PNG")


def test_a_lock_taken_over_as_stale_is_not_removed_by_its_old_holder(tmp_path):
    f = tmp_path / "broll.json"; lock = tmp_path / "broll.json.lock"
    with jobs.file_lock(f, stale_after=0.1):
        time.sleep(0.2)
        taken = threading.Event(); release = threading.Event()
        def second():
            with jobs.file_lock(f, stale_after=0.1):
                taken.set(); release.wait(2)
        t = threading.Thread(target=second); t.start(); taken.wait(2)
    assert lock.exists()  # the first holder left without deleting the second holder's lock
    release.set(); t.join()
    assert not lock.exists()


def test_parallel_writes_to_one_state_file_never_clash(tmp_path):
    f = tmp_path / "costs.json"; errors = []
    def write(n):
        try:
            for i in range(50): jobs.write_json(f, {"n": n, "i": i})
        except Exception as e: errors.append(e)
    threads = [threading.Thread(target=write, args=(n,)) for n in range(4)]
    for t in threads: t.start()
    for t in threads: t.join()
    assert not errors and json.loads(f.read_text())["i"] == 49


def test_costs_keep_clips_that_were_replaced_or_abandoned(project):
    p, calls = project
    (p / "config.yaml").write_text((p / "config.yaml").read_text().replace("require_calibration: true", "require_calibration: false"))
    (p / "beats.json").write_text(json.dumps([{"id": "hook", "dialogue": "Hello there."}]))
    gen(p); gen(p, redo=["hook"])
    report = costs.refresh(p, load_config(p))
    assert report["a_roll"]["clips"] == 2 and report["a_roll"]["reported_cost"]["usd"] == pytest.approx(0.63)
    aroll.update(p, lambda st: st["clips"]["hook"].update(status="abandoned"))
    report = costs.refresh(p, load_config(p))
    assert report["abandoned"]["jobs"] == 1


def test_a_lock_prompt_made_during_a_calibration_run_survives(project):
    p, calls = project
    cfg = load_config(p)
    calibration.generate(p, cfg, "hook")
    calls["hook"] = lambda: calibration.lock(p, cfg, attempt=1)  # the user locks take 1 while take 2 is generating
    calibration.generate(p, cfg, "hook")
    state = calibration.load(p)
    assert state["locked"] and state["accepted_attempt"] == 1 and len(state["attempts"]) == 2


def test_beats_without_ids_can_be_calibrated_and_reused(project):
    p, calls = project
    (p / "beats.json").write_text(json.dumps([{"dialogue": "Hello there."}, {"dialogue": "Bye now."}]))
    cfg = load_config(p)
    calibration.generate(p, cfg, "01"); calibration.lock(p, cfg)
    assert calibration.load(p)["attempts"][0]["beat_id"] == "01"
    assert [r["status"] for r in aroll.plan(p, cfg)["rows"]] == ["from calibration", "to generate"]


def test_max_retries_zero_still_submits_one_job(project):
    p, calls = project
    (p / "config.yaml").write_text((p / "config.yaml").read_text().replace("require_calibration: true", "require_calibration: false"))
    (p / "beats.json").write_text(json.dumps([{"id": "hook", "dialogue": "Hello there."}]))
    gen(p, max_retries=0)
    assert len(calls["video"]) == 1 and aroll.load(p)["clips"]["hook"]["status"] == "success"


def test_archive_recognises_the_same_series_however_it_is_typed(project, tmp_path, monkeypatch):
    from ugc_forge.library import create_series
    p, _ = project
    monkeypatch.setattr(cli, "workspace_path", lambda cfg: tmp_path / "ws")
    create_series(tmp_path / "ws", "My Series")
    cli.cmd_archive(Namespace(project=str(p), series="My Series", title="One"))
    cli.cmd_attach_series(Namespace(project=str(p), series="my-series"))
    with pytest.raises(RuntimeError, match="already archived"):
        cli.cmd_archive(Namespace(project=str(p), series=None, title="One"))
