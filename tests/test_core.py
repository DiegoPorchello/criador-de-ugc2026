import pytest
import json
from ugc_forge.timing import choose_duration
from ugc_forge.storyboard import validate, generation_beats
from ugc_forge.calibration import prompt_hash

def test_supported_duration_selection():
    cfg={"words_per_minute":135,"lead_in_seconds":0.25,"tail_seconds":0.5,"supported_durations":[4,6,8,10],"pacing_warning_ratio":0.18}
    natural,d=choose_duration("Okay, I discovered something.",cfg)
    assert d in [4,6,8,10]
    assert d >= natural

def test_storyboard_full_a_roll_even_under_broll():
    beats=[
        {"id":"a","dialogue":"Hello","a_roll":True},
        {"id":"b","dialogue":"VO that will sit under B-roll","a_roll":True,"overlay":{"type":"broll","description":"product close-up"}},
    ]
    assert validate(beats)
    assert [b["id"] for b in generation_beats(beats)]==["a","b"]

def test_prompt_hash_changes():
    assert prompt_hash("a","b") != prompt_hash("a","c")

def _fake_video_client(statuses, sent, download_failures=0, errors=None):
    from types import SimpleNamespace as NS
    polls=iter(statuses); fails={"n":download_failures}
    def get(iid, include_input=True):
        st=next(polls)
        if isinstance(st, Exception): raise st
        return NS(status=st, errors=errors, output_video=NS(uri="out-uri") if st=="completed" else None,
                  usage=NS(output_tokens_by_modality=[NS(modality="text", tokens=9), NS(modality="video", tokens=7724)]))
    def download(file):
        if fails["n"]: fails["n"]-=1; raise ConnectionError("reset")
        return b"mp4"
    return NS(interactions=NS(create=lambda **kw: sent.update(kw) or NS(id="i1", status="in_progress"), get=get),
              files=NS(download=download))

def test_video_job_is_submitted_in_background_and_polled(tmp_path, monkeypatch):
    from ugc_forge.config import DEFAULTS
    from ugc_forge.providers import google
    sent={}
    monkeypatch.setattr(google, "_client", lambda pcfg: _fake_video_client(["queued", RuntimeError("blip"), "in_progress", "completed"], sent, download_failures=1))
    monkeypatch.setattr(google, "_POLL_SECONDS", 0)
    ref=tmp_path/"ref.png"; ref.write_bytes(b"\xff\xd8\xff\xe0 jpeg bytes")
    submitted=[]
    meta=google.generate_video("prompt", ref, DEFAULTS, 6, tmp_path/"out.mp4", on_submitted=submitted.append)
    assert sent["background"] is True and sent["response_format"]["duration"]=="6s"
    assert sent["input"][0]["mime_type"]=="image/jpeg" and "data" in sent["input"][0]
    assert submitted==["i1"] and meta=={"interaction_id":"i1","video_output_tokens":7724}
    assert (tmp_path/"out.mp4").read_bytes()==b"mp4"

def test_video_job_failures_say_whether_to_resubmit_or_resume(tmp_path, monkeypatch):
    import copy, pytest
    from ugc_forge.config import DEFAULTS
    from ugc_forge.providers import google
    monkeypatch.setattr(google, "_POLL_SECONDS", 0)
    cfg=copy.deepcopy(DEFAULTS); cfg["video"]["timeout"]=10
    def run(statuses, **kw):
        monkeypatch.setattr(google, "_client", lambda pcfg: _fake_video_client(statuses, {}, **kw))
        t={"now":0}
        def clock(): t["now"]+=4; return t["now"]
        with pytest.raises(google.VideoJobError) as e:
            google.await_video("i1", cfg, tmp_path/"out.mp4", sleep=lambda s: None, clock=clock)
        return e.value
    timeout=run(["in_progress"]*10)
    assert timeout.resumable and not timeout.retryable and "without paying again" in str(timeout)
    lost=run(["completed"], download_failures=3)
    assert lost.resumable and not (tmp_path/"out.mp4").exists()
    budget=run(["budget_exceeded"])
    assert not budget.retryable and not budget.resumable and "spending limit" in str(budget)
    failed=run(["failed"], errors=[type("E",(),{"message":"safety"})()])
    assert failed.retryable and "safety" in str(failed)

def test_refused_video_requests_are_not_resubmitted(tmp_path, monkeypatch):
    import pytest
    from types import SimpleNamespace as NS
    from ugc_forge.config import DEFAULTS
    from ugc_forge.providers import google
    class Refused(Exception): status_code=400
    class Busy(Exception): status_code=429
    ref=tmp_path/"ref.png"; ref.write_bytes(b"x")
    for exc, retryable in ((Refused("bad"), False), (Busy("slow down"), True)):
        def create(**kw): raise exc
        monkeypatch.setattr(google, "_client", lambda pcfg: NS(interactions=NS(create=create)))
        with pytest.raises(google.VideoJobError) as e:
            google.submit_video("p", ref, DEFAULTS, 4)
        assert e.value.retryable is retryable

def test_supported_durations_accept_subsets_only():
    import copy, pytest
    from ugc_forge.config import DEFAULTS
    from ugc_forge.providers.google import validate_video_config
    for ok in ([4,5,6,8,10],[4,6,8,10]):
        cfg=copy.deepcopy(DEFAULTS); cfg["timing"]["supported_durations"]=ok; validate_video_config(cfg)
    for bad in ([2,4],[4,11]):
        cfg=copy.deepcopy(DEFAULTS); cfg["timing"]["supported_durations"]=bad
        with pytest.raises(ValueError): validate_video_config(cfg)

def test_video_cost_from_reported_tokens():
    from ugc_forge.config import DEFAULTS
    from ugc_forge.pricing import video_cost_from_tokens, estimate_video_cost
    import copy
    cfg=copy.deepcopy(DEFAULTS); cfg["video"]["resolution"]="360p"; cfg["provider"]="google"
    # 4s at 360p came back as 7724 video tokens in the 2026-09-28 live check.
    assert round(video_cost_from_tokens(cfg,7724)["usd"],4)==round(estimate_video_cost(cfg,4)["usd"],4)==0.1352

def test_generated_images_are_saved_in_the_format_their_name_says(tmp_path):
    import io
    from PIL import Image
    from ugc_forge.providers.google import _write_image, image_mime_type
    buf=io.BytesIO(); Image.new("RGB",(4,4),"red").save(buf,format="JPEG"); jpeg=buf.getvalue()
    _write_image(jpeg, tmp_path/"reference.png")
    assert (tmp_path/"reference.png").read_bytes().startswith(b"\x89PNG")
    assert image_mime_type(tmp_path/"reference.png")=="image/png"
    _write_image(jpeg, tmp_path/"frame.jpg")
    assert (tmp_path/"frame.jpg").read_bytes()==jpeg  # already the right format: written untouched



@pytest.fixture
def a_roll(tmp_path, monkeypatch):
    from ugc_forge import jobs
    from ugc_forge.project import init_project
    p=tmp_path/"video"; init_project(p)
    (p/"avatar/reference.png").write_bytes(b"avatar")
    cfg=(p/"config.yaml").read_text().replace("require_calibration: true","require_calibration: false").replace("retry_delay_seconds: 5","retry_delay_seconds: 0")
    (p/"config.yaml").write_text(cfg)
    calls={"submitted":[],"awaited":[],"fail":0}
    def fake_video(prompt, reference, cfg, duration, output, on_submitted=None):
        calls["submitted"].append(prompt); iid=f"i{len(calls['submitted'])}"
        if calls["fail"]: calls["fail"]-=1; raise RuntimeError("provider refused the request")  # before any job exists
        if on_submitted: on_submitted(iid)
        output.parent.mkdir(parents=True,exist_ok=True); output.write_bytes(prompt.encode())
        return {"interaction_id":iid,"video_output_tokens":1000}
    def fake_await(iid, cfg, output, provider=None):
        calls["awaited"].append(iid); output.write_bytes(b"collected"); return {"interaction_id":iid,"video_output_tokens":1000}
    monkeypatch.setattr(jobs,"generate_video",fake_video); monkeypatch.setattr(jobs,"await_video",fake_await)
    def run(**kw):
        from argparse import Namespace
        from ugc_forge import cli
        args=dict(project=str(p),yes=True,resolution=None,aspect_ratio=None,concurrency=1,max_retries=None,redo=None); args.update(kw)
        cli.cmd_generate(Namespace(**args))
        return json.loads((p/"job.json").read_text())["clips"]
    def beats(items): (p/"beats.json").write_text(json.dumps(items))
    return p, calls, run, beats

def test_a_roll_rerun_retries_failed_clips_and_reports_failure(a_roll):
    import pytest
    p, calls, run, _ = a_roll
    calls["fail"]=4
    with pytest.raises(RuntimeError, match="1 clip\\(s\\) failed: hook"):
        run()
    clips=run()
    assert {k:(c["status"],c["attempts"]) for k,c in clips.items()}=={"hook":("success",4),"example":("success",2)}
    costs=json.loads((p/"costs.json").read_text())
    assert costs["a_roll"]["reported_video_output_tokens"]==2000 and costs["b_roll"]["clips"]==0

def test_a_roll_regenerates_only_what_changed(a_roll):
    p, calls, run, beats = a_roll
    run(); assert len(calls["submitted"])==2
    run(); assert len(calls["submitted"])==2  # nothing changed: nothing paid for
    beats([{"id":"intro","dialogue":"New first line."},{"id":"hook","dialogue":"Okay... I discovered something."},
           {"id":"example","dialogue":"Rewritten second line."}])
    clips=run()
    # intro is new and example's line changed; hook is kept and renamed for its new position.
    assert ["New first line." in x for x in calls["submitted"][2:]]==[True,False] and "Rewritten second line." in calls["submitted"][3]
    assert clips["hook"]["output"]=="output/a-roll/02_hook.mp4" and (p/"output/a-roll/02_hook.mp4").exists()
    assert not (p/"output/a-roll/01_hook.mp4").exists()
    run(redo=["hook"]); assert len(calls["submitted"])==5

def test_a_roll_collects_an_interrupted_job_instead_of_paying_again(a_roll):
    p, calls, run, _ = a_roll
    run()
    clips=json.loads((p/"job.json").read_text())["clips"]
    clips["hook"].update(status="pending",interaction_id="i-lost")  # as if the run was killed mid-generation
    (p/"job.json").write_text(json.dumps({"clips":clips}))
    run()
    assert calls["awaited"]==["i-lost"] and len(calls["submitted"])==2

def test_lock_prompt_refuses_prompts_or_images_nobody_has_seen(a_roll, monkeypatch):
    import pytest
    from ugc_forge import calibration
    from ugc_forge.config import load_config
    p, calls, _, _ = a_roll
    cfg=load_config(p)
    first=calibration.generate(p,cfg); second=calibration.generate(p,cfg)
    assert (first["attempt"],second["attempt"],len(calls["submitted"]))==(1,2,2)
    scene=p/"prompts/scene.md"; original=scene.read_text()
    scene.write_text(original+"\nSlower delivery.")
    with pytest.raises(RuntimeError, match="prompt files changed after calibration attempt 2"):
        calibration.lock(p,cfg)
    scene.write_text(original)
    assert calibration.lock(p,cfg,attempt=1)["accepted_attempt"]==1
    (p/"avatar/reference.png").write_bytes(b"new face")
    with pytest.raises(RuntimeError, match="reference image changed after calibration lock"):
        calibration.assert_locked_current(p,{**cfg,"generation":{**cfg["generation"],"require_calibration":True}})
    calibration.unlock(p)
    with pytest.raises(RuntimeError, match="reference image changed after calibration attempt 1"):
        calibration.lock(p,cfg,attempt=1)

def test_sequential_collects_an_interrupted_attempt(a_roll):
    from ugc_forge import sequential
    from ugc_forge.config import load_config
    p, calls, _, _ = a_roll
    cfg=load_config(p)
    item,rec=sequential.generate_current(p,cfg)
    assert (item["id"],rec["attempt"],rec["status"])==("hook",1,"success")
    state=sequential.load_session(p); state["clips"]["hook"]["attempts"][-1].update(status="pending",interaction_id="i-lost")
    sequential.save_session(p,state)
    item,rec=sequential.generate_current(p,cfg)
    assert rec["attempt"]==1 and calls["awaited"]==["i-lost"] and len(calls["submitted"])==1

def test_sequential_follows_the_storyboard_and_shares_finished_clips_with_batch(a_roll):
    import pytest
    from ugc_forge import sequential
    from ugc_forge.config import load_config
    p, calls, run, beats = a_roll
    cfg=load_config(p)
    beats([{"id":"hook","dialogue":"First."},{"id":"title","a_roll":False,"overlay":{"type":"graphic","description":"Title card"}},
           {"id":"cover","dialogue":"Under B-roll.","a_roll":False},{"id":"close","dialogue":"Last."}])
    with pytest.raises(RuntimeError, match="Generate it first"):
        sequential.accept_current(p,cfg)
    sequential.generate_current(p,cfg); sequential.generate_current(p,cfg)
    nxt,_=sequential.accept_current(p,cfg,attempt_no=1)
    assert nxt["id"]=="close"  # beats without A-roll are skipped, not generated
    assert (p/"output/a-roll/01_hook.mp4").read_bytes()==(p/"output/a-roll/attempts/01_hook_attempt-01.mp4").read_bytes()
    beats([{"id":"intro","dialogue":"Inserted."},{"id":"hook","dialogue":"First."},{"id":"close","dialogue":"Last."}])
    item,_=sequential.current(p,cfg)
    assert item["id"]=="intro"  # an inserted beat is picked up, not skipped
    run()  # batch mode generates only what one-at-a-time mode hasn't finished
    assert len(calls["submitted"])==4


def test_an_error_while_waiting_never_pays_for_a_second_job(a_roll, monkeypatch):
    from ugc_forge import jobs
    p, calls, run, _ = a_roll
    def flaky_video(prompt, reference, cfg, duration, output, on_submitted=None):
        calls["submitted"].append(prompt)
        on_submitted("paid-job")
        raise ValueError("garbled reply while polling")  # not a VideoJobError
    monkeypatch.setattr(jobs, "generate_video", flaky_video)
    with pytest.raises(RuntimeError, match="still generating or downloading"):
        run()
    clips=json.loads((p/"job.json").read_text())["clips"]
    assert (clips["hook"]["status"], clips["hook"]["interaction_id"]) == ("pending", "paid-job")
    assert len(calls["submitted"]) == 2  # one job per line, no resubmission
    run()  # the rerun collects the paid job instead of submitting another
    assert calls["awaited"][:2] == ["paid-job", "paid-job"] and len(calls["submitted"]) == 2
