from __future__ import annotations
from pathlib import Path
import io, mimetypes, os, re, time

# Pieces shared by every provider.

class VideoJobError(RuntimeError):
    """A video job that did not produce a file.

    retryable: submitting a new paid job may succeed.
    resumable: the job may still complete; poll interaction_id again instead of paying for a new one.
    """
    def __init__(self, message: str, interaction_id: str|None=None, retryable: bool=False, resumable: bool=False):
        super().__init__(message)
        self.interaction_id=interaction_id; self.retryable=retryable; self.resumable=resumable

def resolve_key(provider_cfg: dict, service: str) -> str:
    """The API key from config, or from the environment variable named by api_key_env."""
    direct = provider_cfg.get("api_key")
    if isinstance(direct, str) and direct.strip():
        return direct.strip()
    env = provider_cfg.get("api_key_env")
    if env and (not isinstance(env, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", env)):
        raise RuntimeError("api_key_env must name an environment variable; put the key value in api_key.")
    key = os.getenv(env) if env else None
    if not key:
        raise RuntimeError(f"Missing {service} API key. Run `ugc-forge setup` to add it.")
    return key

def fetch_with_retry(fetch, attempts: int = 3, pause: float = 4, sleep=time.sleep) -> bytes:
    """Download a finished (already paid-for) result, retrying transient failures before giving up."""
    for n in range(1, attempts + 1):
        try:
            return fetch()
        except Exception:
            if n == attempts: raise
            sleep(pause)

def save_video(data: bytes, output: Path):
    output.parent.mkdir(parents=True, exist_ok=True)
    tmp = output.with_name(output.name + ".part"); tmp.write_bytes(data); tmp.replace(output)

SUFFIX_FORMATS={".png":"PNG",".jpg":"JPEG",".jpeg":"JPEG",".webp":"WEBP"}

def _sniff_format(data: bytes) -> str|None:
    if data.startswith(b"\x89PNG"): return "PNG"
    if data.startswith(b"\xff\xd8\xff"): return "JPEG"
    if data[:4]==b"RIFF" and data[8:12]==b"WEBP": return "WEBP"
    return None

def image_mime_type(path: Path) -> str:
    # Trust the bytes over the extension: a user-supplied file may be misnamed.
    fmt=_sniff_format(path.read_bytes()[:12])
    return f"image/{fmt.lower()}" if fmt else (mimetypes.guess_type(path.name)[0] or "image/jpeg")

def _write_image(data: bytes, output: Path):
    # The model chooses its own encoding (JPEG as of 2026-09-28), so convert to match the file name.
    output.parent.mkdir(parents=True,exist_ok=True)
    want=SUFFIX_FORMATS.get(output.suffix.lower())
    if want is None or _sniff_format(data)==want:
        output.write_bytes(data); return
    from PIL import Image
    img=Image.open(io.BytesIO(data))
    if want=="JPEG" and img.mode not in ("RGB","L"): img=img.convert("RGB")
    img.save(output,format=want)

