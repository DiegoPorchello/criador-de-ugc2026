from __future__ import annotations
from pathlib import Path
from . import google, kie
from .base import VideoJobError

__all__ = ["VideoJobError", "PROVIDERS", "DEFAULT_PROVIDER", "name", "active",
           "validate_video_config", "generate_video", "await_video", "generate_image", "job_state", "FINISHED_STATES"]

# The rest of Forge calls these, never a provider module directly. `provider` in config picks one.
PROVIDERS = {"google": google, "kie": kie}
DEFAULT_PROVIDER = "kie"

def name(cfg: dict) -> str:
    p = cfg.get("provider") or DEFAULT_PROVIDER
    if p not in PROVIDERS: raise ValueError(f"Unknown provider '{p}'. Use one of: {', '.join(PROVIDERS)}.")
    return p

def active(cfg: dict):
    return PROVIDERS[name(cfg)]

def validate_video_config(cfg: dict):
    active(cfg).validate_video_config(cfg)

def generate_video(prompt: str, reference: Path, cfg: dict, duration: int, output: Path, on_submitted=None) -> dict:
    job_id = active(cfg).submit_video(prompt, reference, cfg, duration)
    if on_submitted: on_submitted(job_id)
    return await_video(job_id, cfg, output)

def await_video(job_id: str, cfg: dict, output: Path, provider: str | None = None) -> dict:
    # A job is always collected from the provider that accepted it, even if config has since changed.
    meta = PROVIDERS[provider or name(cfg)].await_video(job_id, cfg, output)
    return {"provider": provider or name(cfg), **meta}

FINISHED_STATES = {"success", "completed"}

def job_state(job_id: str, cfg: dict, provider: str | None = None) -> str | None:
    """Ask the provider that holds a job for its state; None if it can't be reached."""
    try:
        return PROVIDERS[provider or name(cfg)].job_state(cfg, job_id)
    except Exception:
        return None

def generate_image(inputs: list[Path], prompt: str, cfg: dict, output: Path, aspect_ratio: str | None = None, model_key: str = "image") -> dict:
    meta = active(cfg).generate_image(inputs, prompt, cfg, output, aspect_ratio=aspect_ratio, model_key=model_key)
    return {"provider": name(cfg), **meta}
