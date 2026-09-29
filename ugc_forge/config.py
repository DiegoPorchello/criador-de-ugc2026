from __future__ import annotations
from pathlib import Path
import copy, os, yaml

DEFAULTS = {
    # Which service generates images and video: "kie" (kie.ai) or "google" (Gemini API). Usually set once by
    # `ugc-forge setup` in the shared settings; a project's own config.yaml can override it.
    "provider": "kie",
    "workspace": {"root": "~/.ugc-forge"},
    # kie.ai's queue can take a long time, so its jobs get a longer wait than video.timeout.
    "kie": {"api_key_env": "UGC_FORGE_KIE_API_KEY", "timeout": 1800},
    "generation_models": {
        "image": {"model": "gemini-3-pro-image", "api_key_env": "UGC_FORGE_IMAGE_API_KEY"},
        "video": {"model": "gemini-omni-1.1-flash", "api_key_env": "UGC_FORGE_VIDEO_API_KEY"},
        # B-roll image edits; gemini-3.1-flash-image is half the price but follows instructions less closely.
        "broll_image": {"model": "gemini-3-pro-image", "api_key_env": "UGC_FORGE_IMAGE_API_KEY"},
    },
    "video": {"resolution": "720p", "aspect_ratio": "9:16", "timeout": 600},
    "generation": {"mode": "batch", "concurrency": 3, "max_retries": 3, "retry_delay_seconds": 5, "resume": True, "require_calibration": True, "calibration_beat_id": None},
    "timing": {"words_per_minute": 135, "lead_in_seconds": 0.25, "tail_seconds": 0.50, "supported_durations": [3, 4, 5, 6, 7, 8, 9, 10], "pacing_warning_ratio": 0.18},
    "cost": {
        "currency": "USD", "pricing_date": "2026-09-28",
        # Standard video output with audio: $17.50 per million tokens.
        "usd_per_second_720p": 0.10136,
        "usd_per_million_video_output_tokens": 17.50,
        # Image output at 1K/2K; 1120 tokens per image = $0.134 (Gemini API pricing, 2026-09-24).
        # flash: $0.067 per 1K image at the same ~1120 tokens (derived from the per-image price).
        "image_usd_per_million_output_tokens": {"gemini-3-pro-image": 120.0, "gemini-3.1-flash-image": 60.0},
        "estimated_image_output_tokens": 1120,
        # kie.ai bills credits per task ($0.005 each). Video credits per clip for Gemini Omni 1.1 Flash, from
        # kie.ai's listed prices on 2026-09-28. 360p and image prices aren't published: a 4s 360p clip and one
        # Nano Banana Pro image were measured live on 2026-09-28 (63 and 18 credits); longer 360p clips are
        # assumed to match 720p. creditsConsumed records the real charge either way.
        "kie": {
            "usd_per_credit": 0.005,
            "video_credits": {
                "360p": {4: 63, 6: 84, 8: 105, 10: 126},
                "720p": {4: 63, 6: 84, 8: 105, 10: 126},
                "1080p": {4: 63, 6: 84, 8: 105, 10: 126},
                "4k": {4: 147, 6: 168, 8: 189, 10: 210},
            },
            "image_credits": 18,
        },
        "resolution_multipliers": {"720p": 1.0, "360p": 1931 / 5792, "1080p": 1.5, "4k": 3.0},
    },
    "broll": {"default_duration": 4, "default_animation_prompt": "Subtle, natural movement. No dialogue."},
    "paths": {
        "source_frame": "source/frame.jpg", "avatar_spec": "avatar/spec.md",
        "avatar_reference": "avatar/reference.png", "scene_prompt": "prompts/scene.md",
        "fixed_rules_prompt": "prompts/fixed-rules.md", "beats": "beats.json", "output": "output",
        "a_roll_output": "output/a-roll", "b_roll_output": "output/b-roll",
    },
}

def deep_merge(base, override):
    result = copy.deepcopy(base)
    for k, v in (override or {}).items():
        result[k] = deep_merge(result[k], v) if isinstance(v, dict) and isinstance(result.get(k), dict) else v
    return result

def shared_config_candidates() -> list[Path]:
    """Where the shared settings (API keys) may live, in order of preference."""
    out = []
    if os.environ.get("UGC_FORGE_CONFIG"): out.append(Path(os.environ["UGC_FORGE_CONFIG"]).expanduser())
    checkout = Path(__file__).resolve().parent.parent
    if (checkout / "pyproject.toml").exists(): out.append(checkout / "config.yaml")  # a source checkout
    out.append(Path("~/.ugc-forge/config.yaml").expanduser())          # works for any install
    return out

def shared_config_path() -> Path | None:
    return next((c for c in shared_config_candidates() if c.exists()), None)

def load_config(project: Path) -> dict:
    user = {}
    p = project / "config.yaml"
    if p.exists():
        user = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    cfg = deep_merge(DEFAULTS, user)
    # Shared credentials and the chosen provider belong to the user's Forge setup, not each video folder.
    shared_path = shared_config_path()
    shared = {}
    if shared_path and shared_path.resolve() != p.resolve():
        shared = yaml.safe_load(shared_path.read_text(encoding="utf-8")) or {}
        for kind in ("image", "video", "broll_image"):
            local = (user.get("generation_models") or {}).get(kind) or {}
            shared_provider = (shared.get("generation_models") or {}).get(kind) or {}
            if not local.get("api_key"):
                # An explicitly different environment variable opts out of inheritance.
                env = local.get("api_key_env")
                if env in (None, DEFAULTS["generation_models"][kind]["api_key_env"]):
                    if shared_provider.get("api_key"):
                        cfg["generation_models"][kind]["api_key"] = shared_provider["api_key"]
    if "provider" not in user and shared.get("provider"):
        cfg["provider"] = shared["provider"]
    local_kie = user.get("kie") or {}
    if not local_kie.get("api_key") and local_kie.get("api_key_env") in (None, DEFAULTS["kie"]["api_key_env"]):
        if (shared.get("kie") or {}).get("api_key"):
            cfg["kie"]["api_key"] = shared["kie"]["api_key"]
    # Offer only the durations the chosen provider accepts.
    from .providers import PROVIDERS
    allowed = getattr(PROVIDERS.get(cfg["provider"]), "SUPPORTED_VIDEO_DURATIONS", None)
    if allowed:
        cfg["timing"]["supported_durations"] = [d for d in cfg["timing"]["supported_durations"] if int(d) in allowed] or sorted(allowed)
    # B-roll images use the image key unless given their own.
    if not cfg["generation_models"]["broll_image"].get("api_key") and cfg["generation_models"]["image"].get("api_key"):
        cfg["generation_models"]["broll_image"]["api_key"] = cfg["generation_models"]["image"]["api_key"]
    return cfg

def save_config(project: Path, cfg: dict):
    (project / "config.yaml").write_text(yaml.safe_dump(cfg, sort_keys=False, allow_unicode=True), encoding="utf-8")

def workspace_path(cfg: dict) -> Path:
    return Path(os.path.expanduser(cfg["workspace"]["root"])).resolve()

def apply_overrides(cfg: dict, args) -> dict:
    out = copy.deepcopy(cfg)
    pairs = {
        "resolution": ("video","resolution"),
        "aspect_ratio": ("video","aspect_ratio"),
        "concurrency": ("generation","concurrency"),
        "max_retries": ("generation","max_retries"),
    }
    for attr, path in pairs.items():
        val = getattr(args, attr, None)
        if val is not None:
            cur = out
            for key in path[:-1]: cur = cur[key]
            cur[path[-1]] = val
    return out
