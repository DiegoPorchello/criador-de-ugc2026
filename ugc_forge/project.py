from __future__ import annotations
from pathlib import Path
import json
from .config import DEFAULTS, save_config
from . import workflow

DEFAULT_PRE = """Static phone camera. The avatar speaks directly to camera with natural, subtle movement and steady eye contact.

The avatar says:
"""

DEFAULT_POST = """Keep the established delivery, framing and camera behaviour. One continuous take, no jump cuts.
"""

DEFAULT_SPEC = """Replace the person in the supplied source frame with a new fictional avatar.

Avatar:
- Describe appearance, approximate age, hair, clothing and presentation here.

Preserve:
- camera position and framing
- room/environment geometry
- lighting direction and exposure character
- smartphone/real-world photographic characteristics
- natural background detail and incidental imperfections
- body position where practical

Change:
- the person's identity and appearance
- clothing as specified above

Important:
- Do not preserve or imitate the original person's identity.
- The result should look like a genuine frame captured from ordinary smartphone social footage.
"""

def _write(path: Path, text: str): path.write_text(text, encoding="utf-8")

def init_project(project: Path, template_root: Path | None = None):
    if (project/"ugc_forge").is_dir() or (project/"pyproject.toml").exists():
        raise FileExistsError(f"{project} is the Forge installation folder. Create video projects in their own folder, e.g. `ugc-forge init my-video`.")
    existing=[n for n in ("project.json","beats.json","config.yaml") if (project/n).exists()]
    if existing:
        raise FileExistsError(f"A Forge project already exists at {project} ({', '.join(existing)}). Nothing was changed.")
    project.mkdir(parents=True, exist_ok=True)
    for d in ["source","avatar","prompts","output","output/a-roll","output/b-roll","output/calibration"]:
        (project/d).mkdir(exist_ok=True)
    save_config(project,{k:v for k,v in DEFAULTS.items() if k!="provider"})

    _write(project/"creative-brief.md", """# Creative Brief

## Message / premise

## Why this person should deliver it

## Desired setting and framing

## Audio capture logic

## Notes
""")
    _write(project/"source/reference-notes.md", """# Reference Review

## Framing
- Intentional body position and camera angle?
- Useful distance/composition for this video?

## Lighting
- Natural/credible?
- Avoid materially clipped skin highlights where image data is lost?

## Background
- Real visual interest without excessive complexity?
- Useful depth behind subject?

## Pose
- Natural hands/body position?

## Contamination
- Prefer no captions, overlays or unnecessary foreground objects.

## Provenance
- Genuine captured footage rather than an already AI-generated source?
- User entitled to use the frame?
""")
    _write(project/"avatar/spec.md", DEFAULT_SPEC)
    _write(project/"prompts/scene.md", DEFAULT_PRE)
    _write(project/"prompts/fixed-rules.md", DEFAULT_POST)
    _write(project/"beats.json", json.dumps([
        {
            "id":"hook",
            "dialogue":"Okay... I discovered something.",
            "a_roll":True,
            "overlay":None,
            "prompt_override":None
        },
        {
            "id":"example",
            "dialogue":"Let me show you what I mean.",
            "a_roll":True,
            "overlay":{
                "type":"broll",
                "description":"Existing or supplied B-roll layered over the A-roll",
                "asset":None
            }
        }
    ],indent=2))
    workflow.save(project,workflow.default())
    _write(project/"project.json", json.dumps({
        "title":project.name,"avatar_id":None,"look_id":None,"series_id":None
    },indent=2))
