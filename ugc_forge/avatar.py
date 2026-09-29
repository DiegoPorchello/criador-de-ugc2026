from __future__ import annotations
from pathlib import Path
import json
from . import images, jobs

# The project's presenter image. Every version is kept in avatar/history/ and recorded in
# avatar/versions.json, so the user can go back to an earlier candidate.

TEMPLATE_MARKER="Describe appearance, approximate age, hair, clothing and presentation here."

def path(project: Path) -> Path: return project/"avatar"/"versions.json"

def load(project: Path) -> dict:
    p=path(project)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {"attempts":[]}

def save(project: Path, state: dict):
    path(project).parent.mkdir(parents=True,exist_ok=True); jobs.write_json(path(project),state)

def _locked(project: Path):
    # One Avatar image operation at a time: each one reads and rewrites the version list.
    path(project).parent.mkdir(parents=True,exist_ok=True)
    return jobs.file_lock(path(project),name="avatar",stale_after=jobs.IMAGE_LOCK_STALE_AFTER)

def current_path(project: Path, cfg: dict) -> Path: return project/cfg["paths"]["avatar_reference"]

def history_dir(project: Path, cfg: dict) -> Path: return current_path(project,cfg).parent/"history"

def resolve_input(project: Path, cfg: dict, ref: str) -> Path:
    if ref=="source": p=project/cfg["paths"]["source_frame"]
    elif ref=="avatar": p=current_path(project,cfg)
    else: p=Path(ref).expanduser() if Path(ref).expanduser().is_absolute() else project/ref
    if not p.exists():
        hint={"source":"Add the reference frame there first.","avatar":"Make or choose an Avatar first."}.get(ref,"")
        raise FileNotFoundError(f"Avatar input '{ref}' not found at {p}. {hint}".strip())
    return p

def request(project: Path, cfg: dict, prompt: str|None=None, inputs: list[str]|None=None) -> dict:
    if prompt: text=prompt.strip()
    else:
        spec=project/cfg["paths"]["avatar_spec"]
        if not spec.exists(): raise FileNotFoundError(f"Missing Avatar spec: {spec}")
        text=spec.read_text(encoding="utf-8").strip()
        if TEMPLATE_MARKER in text:
            raise RuntimeError(f"{spec} still contains the template text. Describe the Avatar there first.")
    refs=inputs or ["source"]
    return {"prompt":text,"inputs":refs,"paths":[resolve_input(project,cfg,r) for r in refs]}

def make(project: Path, cfg: dict, prompt: str|None=None, inputs: list[str]|None=None) -> dict:
    req=request(project,cfg,prompt,inputs)
    with _locked(project):
        state=load(project)
        result=images.new_version(project,cfg,state,current_path(project,cfg),history_dir(project,cfg),"reference",
                                  req["inputs"],req["paths"],req["prompt"],aspect_ratio=cfg["video"]["aspect_ratio"])
        save(project,state)
    return result

def use(project: Path, cfg: dict, attempt_no: int) -> dict:
    with _locked(project):
        state=load(project)
        result=images.use_version(project,state,current_path(project,cfg),attempt_no,"The Avatar")
        save(project,state)
    return result

def record_copy(project: Path, cfg: dict, copy_in, note: str):
    """Keep the current image, run copy_in() to replace it (e.g. from the library), and record the result."""
    with _locked(project):
        state=load(project); cur=current_path(project,cfg)
        images.adopt_existing(project,cur,history_dir(project,cfg),"reference",state)
        copy_in()
        images.adopt_existing(project,cur,history_dir(project,cfg),"reference",state,note=note)
        save(project,state)
