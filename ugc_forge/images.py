from __future__ import annotations
from pathlib import Path
from datetime import datetime, timezone
import shutil
from .providers import generate_image
from . import jobs

# Versioned images (the Avatar reference, each B-roll shot). Every version is kept in a history folder;
# the "current" file is a copy of the chosen version. entry is the caller's state dict for one image.

def _now() -> str: return datetime.now(timezone.utc).isoformat()

def _rel(project: Path, p: Path) -> str:
    try: return str(p.resolve().relative_to(project.resolve()))
    except ValueError: return str(p)

def adopt_existing(project: Path, current: Path, history: Path, prefix: str, entry: dict, note: str="existing image adopted"):
    """Archive a current image Forge didn't make (or no longer records) so it is never silently overwritten."""
    if not current.exists(): return
    digest=jobs.file_sha256(current)
    if any(a.get("sha256")==digest for a in entry["attempts"]): return
    n=len(entry["attempts"])+1
    keep=history/f"{prefix}_v{n:02d}{current.suffix}"
    keep.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(current,keep)
    entry["attempts"].append({"attempt":n,"prompt":None,"inputs":[],"output":_rel(project,keep),
                              "sha256":digest,"created_at":_now(),"note":note})
    entry["current_attempt"]=n

def new_version(project: Path, cfg: dict, entry: dict, current: Path, history: Path, prefix: str,
                refs: list[str], paths: list[Path], prompt: str, aspect_ratio: str|None=None, model_key: str="image") -> dict:
    adopt_existing(project,current,history,prefix,entry)
    # Hash inputs before generating: editing the current image overwrites that file afterwards.
    records=[{"ref":r,"path":_rel(project,p),"sha256":jobs.file_sha256(p)} for r,p in zip(refs,paths)]
    n=len(entry["attempts"])+1
    attempt_file=history/f"{prefix}_v{n:02d}{current.suffix}"
    meta=generate_image(paths,prompt,cfg,attempt_file,aspect_ratio=aspect_ratio,model_key=model_key)
    current.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(attempt_file,current)
    attempt={"attempt":n,"prompt":prompt,"inputs":records,"output":_rel(project,attempt_file),
             "sha256":jobs.file_sha256(current),"created_at":_now(),"meta":meta}
    entry["attempts"].append(attempt); entry["current_attempt"]=n
    return {**attempt,"current":_rel(project,current)}

def use_version(project: Path, entry: dict, current: Path, attempt_no: int, what: str) -> dict:
    match=[a for a in entry.get("attempts",[]) if a["attempt"]==attempt_no]
    if not match:
        have=", ".join(str(a["attempt"]) for a in entry.get("attempts",[])) or "none"
        raise RuntimeError(f"{what} has no image version {attempt_no}. Versions: {have}.")
    shutil.copy2(project/match[0]["output"],current)
    entry["current_attempt"]=attempt_no
    return {**match[0],"current":_rel(project,current)}
