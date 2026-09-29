import json
import pytest
from ugc_forge import broll, images, jobs
from ugc_forge.config import load_config
from ugc_forge.project import init_project
from ugc_forge.storyboard import validate


@pytest.fixture
def project(tmp_path, monkeypatch):
    p = tmp_path / "video"
    init_project(p)
    (p / "avatar/reference.png").write_bytes(b"avatar")
    (p / "source/frame.jpg").write_bytes(b"frame")
    (p / "beats.json").write_text(json.dumps([
        {"id": "hook", "dialogue": "Hello there."},
        {"id": "room", "dialogue": "Look at this room.",
         "overlay": {"type": "scene_broll", "description": "Remove the person.", "duration": 4}},
        {"id": "sofa", "dialogue": "Every evening.",
         "overlay": {"type": "avatar_broll", "description": "He sits on the sofa.", "inputs": ["avatar", "room"],
                     "animation_prompt": "He looks up.", "duration": 6}},
    ]))
    calls = {"image": [], "video": []}

    def fake_image(inputs, prompt, cfg, output, aspect_ratio=None, model_key="image"):
        calls["image"].append({"inputs": [i.read_bytes() for i in inputs], "prompt": prompt, "aspect_ratio": aspect_ratio})
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(f"image {len(calls['image'])}".encode())
        return {"image_output_tokens": 1120}

    def fake_video(prompt, reference, cfg, duration, output, on_submitted=None):
        calls["video"].append({"prompt": prompt, "reference": reference.read_bytes(), "duration": duration})
        if calls.get("fail", 0):
            calls["fail"] -= 1
            raise RuntimeError("provider hiccup")
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(b"mp4")
        return {"interaction_id": "i", "video_output_tokens": 1931 * duration}

    monkeypatch.setattr(images, "generate_image", fake_image)
    monkeypatch.setattr(jobs, "generate_video", fake_video)
    cfg = load_config(p)
    cfg["generation"]["retry_delay_seconds"] = 0
    return p, cfg, calls


def test_images_use_declared_inputs_and_keep_every_version(project):
    p, cfg, calls = project
    broll.make_image(p, cfg, "room")
    assert calls["image"][0]["inputs"] == [b"frame"]  # scene_broll defaults to the source frame
    assert calls["image"][0]["aspect_ratio"] == "9:16"
    broll.make_image(p, cfg, "sofa")
    assert calls["image"][1]["inputs"] == [b"avatar", b"image 1"]
    # Editing a shot's own image feeds the current version back in and keeps the old one.
    r = broll.make_image(p, cfg, "sofa", prompt="Lower the TV.", inputs=["sofa"])
    assert calls["image"][2]["inputs"] == [b"image 2"]
    assert r["attempt"] == 2 and (p / r["current"]).read_bytes() == b"image 3"
    broll.use_image(p, cfg, "sofa", 1)
    assert (p / r["current"]).read_bytes() == b"image 2"
    with pytest.raises(RuntimeError, match="no image version 9"):
        broll.use_image(p, cfg, "sofa", 9)


def test_existing_untracked_image_is_archived_not_overwritten(project):
    p, cfg, calls = project
    ref = broll.reference_path(p, cfg, "room")
    ref.parent.mkdir(parents=True)
    ref.write_bytes(b"approved by hand")
    r = broll.make_image(p, cfg, "room", inputs=["room"])
    assert calls["image"][0]["inputs"] == [b"approved by hand"]
    assert r["attempt"] == 2
    assert broll.use_image(p, cfg, "room", 1) and ref.read_bytes() == b"approved by hand"


def test_missing_inputs_and_unknown_beats_explain_the_fix(project):
    p, cfg, _ = project
    with pytest.raises(FileNotFoundError, match="broll-image .* room"):
        broll.make_image(p, cfg, "sofa")
    with pytest.raises(RuntimeError, match="not a generated B-roll beat"):
        broll.make_image(p, cfg, "hook")
    with pytest.raises(RuntimeError, match="no image yet: room, sofa"):
        broll.animate(p, cfg)


def test_animate_resumes_and_redoes_clips_whose_image_changed(project):
    p, cfg, calls = project
    broll.make_image(p, cfg, "room"); broll.make_image(p, cfg, "sofa")
    broll.animate(p, cfg)
    assert sorted((c["duration"], c["prompt"]) for c in calls["video"]) == [
        (4, "Subtle, natural movement. No dialogue."), (6, "He looks up.")]
    assert broll.plan(p, cfg)["pending"] == []
    broll.make_image(p, cfg, "room", prompt="Warmer light.", inputs=["room"])
    pl = broll.plan(p, cfg)
    assert [r["id"] for r in pl["pending"]] == ["room"] and pl["seconds"] == 4
    # sofa was built from the old room image, so it is flagged but not silently regenerated.
    assert [r["stale_inputs"] for r in pl["rows"] if r["id"] == "sofa"] == [["room"]]
    broll.animate(p, cfg)
    assert len(calls["video"]) == 3 and calls["video"][-1]["reference"] == b"image 3"


def test_failed_clips_get_fresh_retries_on_rerun_and_costs_cover_images(project):
    p, cfg, calls = project
    broll.make_image(p, cfg, "room"); broll.make_image(p, cfg, "sofa")
    calls["fail"] = 4
    state = broll.animate(p, cfg, only=["room"])
    assert state["clips"]["room"]["status"] == "failed" and state["clips"]["room"]["attempts"] == 3
    state = broll.animate(p, cfg, only=["room"])
    assert state["clips"]["room"] == {**state["clips"]["room"], "status": "success", "attempts": 5}
    from ugc_forge import costs
    report = costs.refresh(p, cfg)
    assert report["b_roll"]["reported_video_output_tokens"] == 1931 * 4
    assert report["images"]["images"] == 2 and round(report["images"]["reported_cost"]["usd"], 4) == 0.2688  # 2 x 1120 tokens at $120/M
    assert report["total"]["complete"] and json.loads((p / "costs.json").read_text())["total"] == report["total"]


def test_a_new_scene_can_be_made_from_the_description_alone(project):
    p, cfg, calls = project
    beats = json.loads((p / "beats.json").read_text())
    beats[1]["overlay"]["inputs"] = []
    (p / "beats.json").write_text(json.dumps(beats))
    r = broll.make_image(p, cfg, "room")
    assert calls["image"][0]["inputs"] == [] and r["inputs"] == []


def test_generated_broll_validation():
    ok = {"id": "a", "dialogue": "x", "overlay": {"type": "scene_broll", "description": "d", "inputs": ["source"]}}
    assert validate([ok])
    for bad in ({"type": "scene_broll"}, {"type": "avatar_broll", "description": "d", "inputs": [""]},
                {"type": "avatar_broll", "description": "d", "duration": "4s"}):
        with pytest.raises(ValueError):
            validate([{"id": "a", "dialogue": "x", "overlay": bad}])


def test_editing_motion_or_reordering_beats_behaves_sensibly(project):
    p, cfg, calls = project
    broll.make_image(p, cfg, "room"); broll.make_image(p, cfg, "sofa")
    broll.animate(p, cfg)
    beats = json.loads((p / "beats.json").read_text())
    beats[2]["overlay"]["animation_prompt"] = "He sighs."
    beats.insert(0, {"id": "intro", "dialogue": "First."})
    (p / "beats.json").write_text(json.dumps(beats))
    pl = broll.plan(p, cfg)
    # Images are found by beat id after the insert; only the shot whose motion changed is regenerated.
    assert pl["missing"] == [] and [r["id"] for r in pl["pending"]] == ["sofa"]
    state = broll.animate(p, cfg)
    assert state["clips"]["room"]["output"] == "output/b-roll/03_room.mp4" and (p / "output/b-roll/03_room.mp4").exists()
    assert calls["video"][-1]["prompt"] == "He sighs." and len(calls["video"]) == 3
    broll.animate(p, cfg, redo=["room"])
    assert len(calls["video"]) == 4
