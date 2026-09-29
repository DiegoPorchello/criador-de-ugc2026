from __future__ import annotations
from pathlib import Path
from datetime import datetime, timezone
import json, re, shutil
from . import jobs

def slugify(value: str) -> str:
    # \w keeps letters from any script, so non-Latin names don't all collapse into one folder.
    s = re.sub(r"[^\w]+|_+", "-", value.lower()).strip("-")
    if not s: raise ValueError(f"'{value}' needs at least one letter or number to be used as a name.")
    return s

def ensure_workspace(workspace: Path):
    for d in ("avatars", "series"):
        (workspace / d).mkdir(parents=True, exist_ok=True)

def list_avatars(workspace: Path):
    ensure_workspace(workspace)
    result = []
    for p in sorted((workspace/"avatars").iterdir()):
        meta = p/"avatar.json"
        if p.is_dir() and meta.exists():
            result.append(json.loads(meta.read_text(encoding="utf-8")))
    return result

def save_avatar(workspace: Path, name: str, reference: Path, spec: Path, profile: dict | None = None, replace: bool = False):
    ensure_workspace(workspace)
    slug = slugify(name)
    dest = workspace/"avatars"/slug
    if (dest/"avatar.json").exists() and not replace:
        raise FileExistsError(f"An Avatar called '{slug}' already exists. Use a different name, or pass --replace to overwrite its reference and spec (its Looks are kept).")
    dest.mkdir(parents=True, exist_ok=True)
    shutil.copy2(reference, dest/"reference.png")
    shutil.copy2(spec, dest/"spec.md")
    data = {
        "id": slug, "name": name,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "reference": "reference.png", "spec": "spec.md",
        "profile": profile or {},
    }
    jobs.write_json(dest/"avatar.json", data)
    return data

def get_avatar(workspace: Path, avatar_id: str):
    p = workspace/"avatars"/slugify(avatar_id)
    meta = p/"avatar.json"
    if not meta.exists(): raise FileNotFoundError(f"Avatar not found: {avatar_id}")
    return p, json.loads(meta.read_text(encoding="utf-8"))

def create_series(workspace: Path, name: str, avatar_id: str | None = None):
    ensure_workspace(workspace)
    slug = slugify(name)
    p = workspace/"series"/slug
    if (p/"series.json").exists():
        # Recreating must never reset the episode count, or the next archive would overwrite episode 001.
        return json.loads((p/"series.json").read_text(encoding="utf-8"))
    (p/"videos").mkdir(parents=True, exist_ok=True)
    data = {
        "id": slug, "name": name, "avatar_id": avatar_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "video_count": 0,
    }
    jobs.write_json(p/"series.json", data)
    if not (p/"series.md").exists():
        (p/"series.md").write_text(encoding="utf-8", data=f"# {name}\n\n## Format\n\n_To be developed._\n\n## Established style\n\n_To be developed._\n\n## Previous videos\n")
    return data

def list_series(workspace: Path):
    ensure_workspace(workspace)
    result=[]
    for p in sorted((workspace/"series").iterdir()):
        m=p/"series.json"
        if p.is_dir() and m.exists(): result.append(json.loads(m.read_text(encoding="utf-8")))
    return result

def archive_video(workspace: Path, series_id: str, project: Path, manifest: dict):
    series = workspace/"series"/slugify(series_id)
    if not series.exists(): raise FileNotFoundError(f"Series not found: {series_id}")
    meta = json.loads((series/"series.json").read_text(encoding="utf-8"))
    number = int(meta.get("video_count",0)) + 1
    title = manifest.get("title") or f"video-{number}"
    vid_id = f"{number:03d}-{slugify(title)}"
    dest = series/"videos"/vid_id
    if dest.exists():
        raise FileExistsError(f"Episode folder {dest} already exists; nothing was archived.")
    dest.mkdir(parents=True)
    for rel in ["beats.json","job.json","costs.json","workflow.json","creative-brief.md","calibration.json","sequential.json","broll.json"]:
        src=project/rel
        if src.exists(): shutil.copy2(src,dest/rel)
    prompts=dest/"prompts"; prompts.mkdir(exist_ok=True)
    for rel in ["scene.md","fixed-rules.md"]:
        src=project/"prompts"/rel
        if src.exists(): shutil.copy2(src,prompts/rel)
    jobs.write_json(dest/"video.json", {**manifest,"id":vid_id,"number":number})
    meta["video_count"]=number
    jobs.write_json(series/"series.json", meta)
    return vid_id


def looks_dir(workspace: Path, avatar_id: str) -> Path:
    ap,_=get_avatar(workspace,avatar_id)
    d=ap/"looks"; d.mkdir(parents=True,exist_ok=True); return d

def save_look(workspace: Path, avatar_id: str, name: str, reference: Path, spec: Path, scene_profile: dict|None=None, replace: bool=False):
    ap,avatar=get_avatar(workspace,avatar_id)
    slug=slugify(name); dest=looks_dir(workspace,avatar_id)/slug
    if (dest/"look.json").exists() and not replace:
        raise FileExistsError(f"{avatar_id} already has a Look called '{slug}'. Use a different name, or pass --replace to overwrite it.")
    dest.mkdir(parents=True,exist_ok=True)
    shutil.copy2(reference,dest/"reference.png")
    shutil.copy2(spec,dest/"spec.md")
    data={
        "id":slug,"name":name,"avatar_id":avatar["id"],
        "created_at":datetime.now(timezone.utc).isoformat(),
        "reference":"reference.png","spec":"spec.md","scene_profile":scene_profile or {}
    }
    jobs.write_json(dest/"look.json", data)
    return data

def list_looks(workspace: Path, avatar_id: str):
    d=looks_dir(workspace,avatar_id); out=[]
    for p in sorted(d.iterdir()):
        m=p/"look.json"
        if p.is_dir() and m.exists(): out.append(json.loads(m.read_text(encoding="utf-8")))
    return out

def get_look(workspace: Path, avatar_id: str, look_id: str):
    d=looks_dir(workspace,avatar_id)/slugify(look_id); m=d/"look.json"
    if not m.exists(): raise FileNotFoundError(f"Look not found: {avatar_id}/{look_id}")
    return d,json.loads(m.read_text(encoding="utf-8"))
