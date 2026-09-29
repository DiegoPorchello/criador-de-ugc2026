import copy
import json
import pytest
from ugc_forge import providers
from ugc_forge.config import DEFAULTS, load_config
from ugc_forge.pricing import estimate_video_cost, reported_usd
from ugc_forge.providers import kie


@pytest.fixture
def cfg():
    c = copy.deepcopy(DEFAULTS)
    c["provider"] = "kie"; c["kie"]["api_key"] = "k"; c["kie"]["timeout"] = 10
    return c


@pytest.fixture
def api(monkeypatch):
    """A fake kie.ai: records requests and replays scripted task states."""
    calls = {"requests": [], "states": [], "downloads": 0}

    def request(cfg, method, path, body=None, timeout=120, base=kie.BASE_URL):
        assert base == (kie.UPLOAD_BASE_URL if path == "/api/file-base64-upload" else kie.BASE_URL)
        calls["requests"].append((method, path, body))
        if path == "/api/file-base64-upload":
            return {"downloadUrl": f"https://tmp/{body['fileName']}"}
        if path == "/api/v1/jobs/createTask":
            if calls.get("refuse"): raise kie.KieError(calls["refuse"], kie._explain(calls["refuse"], "no"))
            return {"taskId": "t1"}
        if path.startswith("/api/v1/jobs/recordInfo"):
            st = calls["states"].pop(0)
            if isinstance(st, Exception): raise st
            return st
        raise AssertionError(path)

    def download(cfg, url):
        calls["downloads"] += 1
        return b"\x89PNG fake" if url.endswith(".png") else b"mp4"

    monkeypatch.setattr(kie, "_request", request)
    monkeypatch.setattr(kie, "_download", download)
    monkeypatch.setattr(kie, "_POLL_SECONDS", 0)
    return calls


def done(url="https://out/v.mp4", credits=63):
    return {"state": "success", "resultJson": json.dumps({"resultUrls": [url]}), "creditsConsumed": credits}


def test_video_is_uploaded_submitted_polled_and_downloaded(cfg, api, tmp_path):
    ref = tmp_path / "ref.png"; ref.write_bytes(b"\xff\xd8\xff\xe0 jpeg")
    api["states"] = [{"state": "waiting"}, kie.KieError(500, "blip"), {"state": "generating"}, done()]
    submitted = []
    meta = providers.generate_video("Say hi", ref, cfg, 6, tmp_path / "out.mp4", on_submitted=submitted.append)
    upload, create = api["requests"][0], api["requests"][1]
    assert upload[2]["base64Data"].startswith("data:image/jpeg;base64,")
    assert create[2] == {"model": "google/gemini-omni-flash-1-1", "input": {"prompt": "Say hi", "image_urls": ["https://tmp/ref.png"],
                         "duration": "6", "aspect_ratio": "9:16", "resolution": "720p"}}
    assert submitted == ["t1"] and meta == {"provider": "kie", "interaction_id": "t1", "credits": 63}
    assert (tmp_path / "out.mp4").read_bytes() == b"mp4"


def test_failures_say_whether_to_resubmit_resume_or_stop(cfg, api, tmp_path):
    ref = tmp_path / "ref.png"; ref.write_bytes(b"x")
    api["refuse"] = 402
    with pytest.raises(kie.VideoJobError) as e:
        kie.submit_video("p", ref, cfg, 4)
    assert not e.value.retryable and "credits have run out" in str(e.value)
    api["refuse"] = 429
    with pytest.raises(kie.VideoJobError) as e:
        kie.submit_video("p", ref, cfg, 4)
    assert e.value.retryable
    api["states"] = [{"state": "fail", "failMsg": "content policy"}]
    with pytest.raises(kie.VideoJobError) as e:
        kie.await_video("t1", cfg, tmp_path / "o.mp4", sleep=lambda s: None)
    assert e.value.retryable and "content policy" in str(e.value)
    api["states"] = [{"state": "generating"}] * 5
    t = {"now": 0}
    def clock(): t["now"] += 4; return t["now"]
    with pytest.raises(kie.VideoJobError) as e:
        kie.await_video("t1", cfg, tmp_path / "o.mp4", sleep=lambda s: None, clock=clock)
    assert e.value.resumable and "without paying again" in str(e.value)


def test_images_use_nano_banana_pro_and_are_saved_as_png(cfg, api, tmp_path):
    a = tmp_path / "a.png"; a.write_bytes(b"x"); b = tmp_path / "b.png"; b.write_bytes(b"y")
    api["states"] = [done("https://out/i.png", credits=18)]
    meta = providers.generate_image([a, b], "Put him in the room.", cfg, tmp_path / "ref.png", aspect_ratio="9:16")
    create = [r for r in api["requests"] if r[1] == "/api/v1/jobs/createTask"][0][2]
    assert create == {"model": "nano-banana-pro", "input": {"prompt": "Put him in the room.", "image_input": ["https://tmp/a.png", "https://tmp/b.png"],
                      "aspect_ratio": "9:16", "resolution": "1K", "output_format": "png"}}
    assert meta == {"provider": "kie", "model": "nano-banana-pro", "credits": 18}
    assert (tmp_path / "ref.png").read_bytes().startswith(b"\x89PNG")


def test_kie_prices_are_per_clip_and_reported_from_credits(cfg):
    assert estimate_video_cost(cfg, [4, 10])["usd"] == pytest.approx((63 + 126) * 0.005)
    cfg["cost"]["kie"]["video_credits"].pop("4k")
    cfg["video"]["resolution"] = "4k"
    est = estimate_video_cost(cfg, 4)
    assert not est["priced"] and "4k" in est["reason"]  # an unconfigured price is never guessed
    assert reported_usd(cfg, {"credits": 63}, "video") == pytest.approx(0.315)
    assert reported_usd(cfg, {"video_output_tokens": 7724}, "video") == pytest.approx(0.13517)


def test_provider_comes_from_setup_and_limits_durations(tmp_path, monkeypatch):
    from ugc_forge import config
    from ugc_forge.project import init_project
    shared = tmp_path / "shared.yaml"
    monkeypatch.setattr(config, "shared_config_path", lambda: shared)
    shared.write_text("provider: google\n")
    p = tmp_path / "video"; init_project(p)
    assert "provider" not in (p / "config.yaml").read_text()
    assert load_config(p)["provider"] == "google" and 3 in load_config(p)["timing"]["supported_durations"]
    shared.write_text("provider: kie\nkie:\n  api_key: shared-kie\n")
    c = load_config(p)
    assert c["provider"] == "kie" and c["kie"]["api_key"] == "shared-kie"
    assert c["timing"]["supported_durations"] == [4, 6, 8, 10]


def test_an_interrupted_job_resumes_with_the_provider_that_took_it(tmp_path, monkeypatch, cfg):
    from ugc_forge import jobs
    seen = []
    monkeypatch.setattr(providers.google, "await_video", lambda iid, c, out: seen.append(("google", iid)) or {"interaction_id": iid})
    monkeypatch.setattr(providers.kie, "await_video", lambda iid, c, out: seen.append(("kie", iid)) or {"interaction_id": iid})
    rec = jobs.run_clip("p", tmp_path / "r.png", cfg, 4, tmp_path / "o.mp4",
                        {"status": "pending", "interaction_id": "g1", "provider": "google", "fingerprint": "f"}, lambda r: None, {"fingerprint": "f"})
    assert seen == [("google", "g1")] and rec["status"] == "success" and rec["provider"] == rec["meta"]["provider"] == "google"
