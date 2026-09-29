"""Fixes for problems found in the first full video run (2026-09-29)."""
import json
import threading
import time
from argparse import Namespace
import pytest
from ugc_forge import aroll, broll, calibration, cli, costs, images, jobs, sequential
from ugc_forge.config import load_config
from ugc_forge.project import init_project


@pytest.fixture
def project(tmp_path, monkeypatch):
    p = tmp_path / "video"; init_project(p)
    (p / "avatar/reference.png").write_bytes(b"avatar")
    (p / "source/frame.jpg").write_bytes(b"frame")
    (p / "config.yaml").write_text((p / "config.yaml").read_text().replace("retry_delay_seconds: 5", "retry_delay_seconds: 0"))
    calls = {"video": [], "fail": 0}

    def fake_image(inputs, prompt, cfg, output, aspect_ratio=None, model_key="image"):
        time.sleep(0.05)  # long enough for parallel commands to overlap
        output.parent.mkdir(parents=True, exist_ok=True); output.write_bytes(prompt.encode())
        return {"model": "nano-banana-pro", "credits": 18}

    def fake_video(prompt, reference, cfg, duration, output, on_submitted=None):
        calls["video"].append(prompt)
        if on_submitted: on_submitted(f"j{len(calls['video'])}")
        if calls["fail"]:
            calls["fail"] -= 1
            raise jobs.VideoJobError("kie.ai task failed (Internal Error); kie.ai doesn't charge failed tasks.", "j", retryable=True)
        output.parent.mkdir(parents=True, exist_ok=True); output.write_bytes(prompt.encode())
        return {"interaction_id": "j", "credits": 63}

    monkeypatch.setattr(images, "generate_image", fake_image)
    monkeypatch.setattr(jobs, "generate_video", fake_video)
    return p, calls


def shots(p, extra=None):
    beats = [{"id": "hook", "dialogue": "Hello there."},
             {"id": "a", "a_roll": False, "overlay": {"type": "scene_broll", "description": "Room A.", "inputs": []}},
             {"id": "b", "a_roll": False, "overlay": {"type": "scene_broll", "description": "Room B.", "inputs": []}},
             {"id": "c", "a_roll": False, "overlay": {"type": "scene_broll", "description": "Room C.", "inputs": [], "animate": False}}]
    (p / "beats.json").write_text(json.dumps(beats + (extra or [])))


def test_parallel_image_commands_keep_every_record(project):
    p, _ = project; shots(p); cfg = load_config(p)
    threads = [threading.Thread(target=broll.make_image, args=(p, cfg, bid)) for bid in ("a", "b", "c")]
    for t in threads: t.start()
    for t in threads: t.join()
    assert sorted(broll.load(p)["references"]) == ["a", "b", "c"]
    assert not list(p.glob("*.lock"))


def test_a_held_lock_times_out_with_a_plain_message(tmp_path):
    f = tmp_path / "state.json"
    with jobs.file_lock(f):
        with pytest.raises(RuntimeError, match="Another Forge command is still using state.json"):
            with jobs.file_lock(f, timeout=0.2): pass


def test_stills_are_listed_but_never_animated(project):
    p, calls = project; shots(p); cfg = load_config(p)
    for bid in ("a", "b", "c"): broll.make_image(p, cfg, bid)
    pl = broll.plan(p, cfg)
    assert [r["id"] for r in pl["rows"]] == ["a", "b"] and pl["stills"] == [{"id": "c", "has_image": True}]
    broll.animate(p, cfg)
    assert len(calls["video"]) == 2


def test_a_resubmission_after_a_provider_failure_is_reported(project):
    p, calls = project; shots(p); cfg = load_config(p)
    broll.make_image(p, cfg, "a"); calls["fail"] = 1
    events = []
    broll.animate(p, cfg, only=["a"], on_result=lambda bid, r: events.append((bid, r["status"], r.get("error") or "")))
    retry = [e for e in events if e[1] == "retrying"]
    assert retry and "doesn't charge failed tasks" in retry[0][2] and "Submitting a new job" in retry[0][2]
    assert events[-1][:2] == ("a", "success")


def test_the_approved_calibration_take_is_reused_not_paid_for_again(project, capsys):
    p, calls = project
    (p / "beats.json").write_text(json.dumps([{"id": "hook", "dialogue": "Hello there."}, {"id": "close", "dialogue": "Bye now."}]))
    cfg = load_config(p)
    calibration.generate(p, cfg, "hook"); calibration.lock(p, cfg)
    pl = aroll.plan(p, cfg)
    assert [(r["id"], r["status"]) for r in pl["rows"]] == [("hook", "from calibration"), ("close", "to generate")]
    assert pl["cost"]["usd"] == pytest.approx(63 * 0.005)  # only the new line is priced
    cli.cmd_generate(Namespace(project=str(p), yes=True, max_cost=None, resolution=None, aspect_ratio=None, concurrency=1, max_retries=None, redo=None))
    assert "[FROM CALIBRATION] hook" in capsys.readouterr().out
    assert len(calls["video"]) == 2  # the calibration take and "close"; hook was not generated again
    report = json.loads((p / "costs.json").read_text())
    assert report["calibration"]["clips"] == 1 and report["a_roll"]["clips"] == 1


def test_one_at_a_time_mode_also_skips_the_calibrated_line(project):
    p, calls = project
    (p / "beats.json").write_text(json.dumps([{"id": "hook", "dialogue": "Hello there."}, {"id": "close", "dialogue": "Bye now."}]))
    cfg = load_config(p)
    calibration.generate(p, cfg, "hook"); calibration.lock(p, cfg)
    item, _ = sequential.current(p, cfg)
    assert item["id"] == "close" and aroll.load(p)["clips"]["hook"]["source"] == "calibration"


def test_set_frame_imports_any_image_as_the_source_frame(project, tmp_path):
    from PIL import Image
    p, _ = project
    png = tmp_path / "Desktop shot.png"; Image.new("RGB", (8, 8), "blue").save(png)
    cli.cmd_set_frame(Namespace(project=str(p), image=str(png)))
    assert (p / "source/frame.jpg").read_bytes()[:3] == b"\xff\xd8\xff" and png.exists()
    bad = tmp_path / "notes.txt"; bad.write_text("hello")
    with pytest.raises(RuntimeError, match="isn't an image"):
        cli.cmd_set_frame(Namespace(project=str(p), image=str(bad)))


def test_check_fails_when_the_balance_cannot_pay_for_a_clip(project, monkeypatch, capsys):
    p, _ = project
    monkeypatch.setattr(cli.kie, "resolve_api_key", lambda kcfg: "k")
    monkeypatch.setattr(cli.kie, "credits", lambda cfg: 20)
    with pytest.raises(RuntimeError, match="Setup is incomplete"):
        cli.cmd_check(Namespace(project=str(p), online=True))
    assert "isn't enough for one video clip" in capsys.readouterr().out
    monkeypatch.setattr(cli.kie, "credits", lambda cfg: 700)
    cli.cmd_check(Namespace(project=str(p), online=True))
    assert "Enough for about 11 short 720p clips or 38 images" in capsys.readouterr().out


def test_costs_include_jobs_still_in_progress(project):
    p, _ = project
    (p / "broll.json").write_text(json.dumps({"references": {}, "clips": {"a": {"status": "pending", "duration": 4, "interaction_id": "j"}}}))
    report = costs.refresh(p, load_config(p))
    assert report["in_flight"]["clips"] == 1 and report["in_flight"]["estimated_cost"]["usd"] == pytest.approx(0.315)


def test_plan_shows_the_cost_without_generating(project, capsys):
    p, _ = project
    (p / "avatar/spec.md").write_text("A man.")
    cli.cmd_avatar(Namespace(project=str(p), yes=False, max_cost=None, prompt=None, inputs=None, name=None, replace=False, plan=True,
                             resolution=None, aspect_ratio=None, concurrency=None, max_retries=None))
    out = capsys.readouterr().out
    assert "Estimated image cost: $0.09" in out and "Plan only" in out and not (p / "avatar/versions.json").exists()


def test_kie_waits_longer_and_says_where_the_job_is(monkeypatch, tmp_path):
    import copy
    from ugc_forge.config import DEFAULTS
    from ugc_forge.providers import kie
    cfg = copy.deepcopy(DEFAULTS); cfg["kie"]["api_key"] = "k"
    assert kie.timeout(cfg) == 1800
    cfg["kie"]["timeout"] = 8
    monkeypatch.setattr(kie, "_request", lambda *a, **k: {"state": "waiting"})
    t = {"now": 0}
    def clock(): t["now"] += 4; return t["now"]
    with pytest.raises(kie.VideoJobError, match="still waiting in kie.ai's queue") as e:
        kie.await_video("t1", cfg, tmp_path / "o.mp4", sleep=lambda s: None, clock=clock)
    assert e.value.resumable


def test_an_in_flight_job_can_be_abandoned_and_regenerated_elsewhere(project, monkeypatch):
    from ugc_forge import inflight, providers
    p, calls = project; shots(p); cfg = load_config(p)
    broll.make_image(p, cfg, "a")
    rec = {"status": "pending", "interaction_id": "d6b1", "provider": "kie", "duration": 4, "attempts": 1,
           "fingerprint": broll.plan(p, cfg)["rows"][0]["fingerprint"]}
    jobs.update_json(broll.path(p), lambda st: st["clips"].__setitem__("a", rec), dict)
    with pytest.raises(RuntimeError, match="abandon"):
        broll.plan(p, cfg, redo=["a"])  # --redo never pays twice for a job still running
    monkeypatch.setattr(providers, "job_state", lambda job, c, prov=None: "success")
    with pytest.raises(RuntimeError, match="already finished at kie.ai and is paid for"):
        inflight.abandon(p, cfg, "a")
    monkeypatch.setattr(providers, "job_state", lambda job, c, prov=None: "waiting")
    hit = inflight.abandon(p, cfg, "a")[0]
    assert (hit["kind"], hit["provider"], hit["state"]) == ("B-roll", "kie.ai", "waiting")
    saved = broll.load(p)["clips"]["a"]
    assert saved["status"] == "abandoned" and saved["interaction_id"] == "d6b1"
    assert broll.plan(p, cfg, only=["a"])["rows"][0]["status"] == "to generate"
    cfg["provider"] = "google"
    state = broll.animate(p, cfg, only=["a"])
    assert state["clips"]["a"]["status"] == "success" and state["clips"]["a"]["provider"] == "google"
    assert state["clips"]["a"]["attempts"] == 2  # the abandoned attempt stays on record
    with pytest.raises(RuntimeError, match="Nothing is in progress for 'a'"):
        inflight.abandon(p, cfg, "a")


def test_an_abandoned_calibration_attempt_starts_a_new_one(project, monkeypatch):
    from ugc_forge import inflight, providers
    p, calls = project; cfg = load_config(p)
    calibration.generate(p, cfg, "hook")
    jobs.update_json(calibration.path(p), lambda st: st["attempts"][-1].update(status="pending", interaction_id="x"), dict)
    monkeypatch.setattr(providers, "job_state", lambda job, c, prov=None: None)  # provider unreachable
    inflight.abandon(p, cfg, "hook")
    assert calibration.generate(p, cfg, "hook")["attempt"] == 2


def test_switching_provider_does_not_redo_finished_lines(project):
    p, calls = project
    (p / "beats.json").write_text(json.dumps([
        {"id": "long", "dialogue": "Gemini is built into every Android phone, so billions already use it daily."},
        {"id": "fixed", "dialogue": "Bye now.", "duration": 4}]))
    (p / "config.yaml").write_text((p / "config.yaml").read_text().replace("require_calibration: true", "require_calibration: false"))
    cli.cmd_generate(Namespace(project=str(p), yes=True, max_cost=None, resolution=None, aspect_ratio=None, concurrency=1, max_retries=None, redo=None))
    kie_rows = {r["id"]: r["duration"] for r in aroll.plan(p, load_config(p))["rows"]}
    cfg = load_config(p); cfg["provider"] = "google"; cfg["timing"]["supported_durations"] = list(range(3, 11))
    rows = {r["id"]: (r["duration"], r["status"]) for r in aroll.plan(p, cfg)["rows"]}
    assert kie_rows["long"] != rows["long"][0]  # Google would pick a different length...
    assert rows == {"long": (rows["long"][0], "done"), "fixed": (4, "done")}  # ...but the finished clips still count
