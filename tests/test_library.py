import pytest
from ugc_forge.library import slugify, save_avatar, save_look, create_series, archive_video
from ugc_forge.project import init_project


def test_init_never_overwrites_a_project_or_the_forge_folder(tmp_path):
    p = tmp_path / "video"
    init_project(p)
    (p / "beats.json").write_text("[]")
    with pytest.raises(FileExistsError, match="Nothing was changed"):
        init_project(p)
    assert (p / "beats.json").read_text() == "[]"
    forge = tmp_path / "forge"; (forge / "ugc_forge").mkdir(parents=True)
    with pytest.raises(FileExistsError, match="installation folder"):
        init_project(forge)


def test_library_refuses_to_overwrite_saved_work(tmp_path):
    ws = tmp_path / "ws"
    ref = tmp_path / "ref.png"; ref.write_bytes(b"face A")
    spec = tmp_path / "spec.md"; spec.write_text("spec")
    save_avatar(ws, "Marco", ref, spec)
    save_look(ws, "marco", "Living room", ref, spec)
    ref.write_bytes(b"face B")
    with pytest.raises(FileExistsError, match="--replace"):
        save_avatar(ws, "marco", ref, spec)
    assert (ws / "avatars/marco/reference.png").read_bytes() == b"face A"
    save_avatar(ws, "Marco", ref, spec, replace=True)
    assert (ws / "avatars/marco/looks/living-room/look.json").exists()  # Looks survive a replace
    with pytest.raises(FileExistsError):
        save_look(ws, "marco", "Living room", ref, spec)


def test_recreating_a_series_keeps_its_episodes(tmp_path):
    ws = tmp_path / "ws"; project = tmp_path / "video"; project.mkdir()
    (project / "creative-brief.md").write_text("episode one")
    create_series(ws, "TV Talk")
    assert archive_video(ws, "tv-talk", project, {"title": "One"}) == "001-one"
    assert create_series(ws, "TV Talk")["video_count"] == 1
    (project / "creative-brief.md").write_text("episode two")
    assert archive_video(ws, "tv-talk", project, {"title": "Two"}) == "002-two"
    assert (ws / "series/tv-talk/videos/001-one/creative-brief.md").read_text() == "episode one"


def test_names_in_any_script_get_distinct_folders():
    assert slugify("Marco Rossi") == "marco-rossi"
    assert slugify("玛丽") != slugify("李明")
    with pytest.raises(ValueError):
        slugify("!!!")
