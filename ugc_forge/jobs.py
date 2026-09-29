from __future__ import annotations
from pathlib import Path
import hashlib, json, os, threading, time, uuid
from contextlib import contextmanager
from . import providers
from .providers import generate_video, await_video, VideoJobError

def write_json(path: Path, data):
    """Write state atomically so a killed run never leaves a half-written file."""
    # A temp name unique to this process and thread, so two writers never clash over the same temp file.
    tmp = path.with_name(f".{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    tmp.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
    tmp.replace(path)

@contextmanager
def file_lock(path: Path, name: str = "", timeout: float = 120, stale_after: float = 900):
    """Cross-process lock beside a state file, so parallel Forge commands never overwrite each other's records."""
    lock = path.with_name(path.name + (f".{name}" if name else "") + ".lock")
    token = uuid.uuid4().hex; start = time.monotonic()
    while True:
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, token.encode()); os.close(fd)
            break
        except FileExistsError:
            try:
                if time.time() - lock.stat().st_mtime > stale_after:  # left behind by a killed command
                    lock.unlink(missing_ok=True); continue
            except FileNotFoundError:
                continue
            if time.monotonic() - start > timeout:
                raise RuntimeError(f"Another Forge command is still using {path.name}{' for ' + name if name else ''}. "
                                   "Wait for it to finish, then run this again.")
            time.sleep(0.05)
    try:
        yield
    finally:
        # Only remove our own lock: if ours was taken over as stale, the new holder's must survive.
        try:
            if lock.read_text() == token: lock.unlink()
        except FileNotFoundError:
            pass

# An image job can wait in a provider's queue for up to kie.timeout (30 minutes), so a lock held around one
# must not be treated as abandoned before then.
IMAGE_LOCK_STALE_AFTER = 7200

def update_json(path: Path, change, default) -> dict:
    """Load, change and save a state file under its lock; change(data) edits data in place."""
    with file_lock(path):
        data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else default()
        change(data)
        write_json(path, data)
        return data

def file_sha256(p: Path) -> str: return hashlib.sha256(p.read_bytes()).hexdigest()

def fingerprint(**parts) -> str:
    """Everything that shapes a generated clip. A clip is only reused while this is unchanged."""
    return hashlib.sha256(json.dumps(parts, sort_keys=True, default=str).encode()).hexdigest()

def video_fingerprint(cfg: dict, prompt: str, reference_sha256: str|None, duration: int) -> str:
    return fingerprint(prompt=prompt, reference=reference_sha256, duration=int(duration),
                       resolution=str(cfg["video"]["resolution"]).lower(), aspect_ratio=cfg["video"]["aspect_ratio"],
                       model=cfg["generation_models"]["video"]["model"])

def content_fingerprint(cfg: dict, prompt: str, reference_sha256: str|None) -> str:
    """Like video_fingerprint but without duration: which clip lengths are offered depends on the provider."""
    return fingerprint(prompt=prompt, reference=reference_sha256,
                       resolution=str(cfg["video"]["resolution"]).lower(), aspect_ratio=cfg["video"]["aspect_ratio"],
                       model=cfg["generation_models"]["video"]["model"])

def is_done(project: Path, record: dict, fp: str, content_fp: str|None=None, min_seconds: float|None=None) -> bool:
    if not (record.get("status") == "success" and record.get("output") and (project / record["output"]).exists()):
        return False
    if record.get("fingerprint") == fp:
        return True
    # A clip made at another length (e.g. before switching provider) still serves if nothing else changed and it's long enough.
    return bool(content_fp and min_seconds is not None and record.get("content_fingerprint") == content_fp
                and float(record.get("duration", 0)) >= min_seconds)

def place_output(project: Path, record: dict, expected: Path):
    """Move a finished clip to its current name (beats may have been reordered) instead of regenerating it."""
    current = project / record["output"]
    if current.resolve() != expected.resolve():
        expected.parent.mkdir(parents=True, exist_ok=True)
        current.replace(expected)
        record["output"] = str(expected.relative_to(project))

def _previous_paid(record: dict) -> list[dict]:
    """Earlier jobs for this clip that were, or may have been, paid for; kept so costs.json never forgets them."""
    history = list(record.get("paid_before", []))
    if record.get("status") in ("success", "abandoned"):
        history.append({k: record.get(k) for k in ("status", "source", "provider", "duration", "interaction_id", "meta") if record.get(k) is not None})
    return history

def run_clip(prompt: str, reference: Path, cfg: dict, duration: int, output: Path, record: dict,
             persist, extra: dict, on_retry=None) -> dict:
    """Generate one clip, resuming a saved in-flight job instead of paying for a new one.

    record is this clip's previous state; persist(record) saves an updated record straight away so a
    killed run can collect jobs it already paid for. Returns the final record.

    Once a job has an id it has been paid for, so only the provider reporting that the job failed justifies
    submitting another one. Any other error while waiting leaves the job recorded as in flight for a rerun.
    """
    # generation.max_retries is the number of jobs one run may submit for a clip (at least one).
    attempts = max(1, int(cfg["generation"]["max_retries"])); delay = float(cfg["generation"]["retry_delay_seconds"])
    prev = int(record.get("attempts", 0))
    base = {**extra, "duration": int(duration)}
    history = _previous_paid(record)
    if history: base["paid_before"] = history
    pending = record.get("interaction_id") if record.get("status") == "pending" and record.get("fingerprint") == extra.get("fingerprint") else None
    job = {"id": pending, "provider": (record.get("provider") or providers.name(cfg)) if pending else providers.name(cfg)}
    submitted = 0; err = None

    def in_flight(message):
        return {**base, "provider": job["provider"], "status": "pending", "interaction_id": job["id"], "attempts": prev + submitted, "error": message}

    def on_submitted(iid):
        job["id"] = iid
        persist(in_flight(None))

    while True:
        try:
            if job["id"]:
                meta = await_video(job["id"], cfg, output, job["provider"])
            else:
                if submitted >= attempts: break
                submitted += 1; job["provider"] = providers.name(cfg)
                meta = generate_video(prompt, reference, cfg, duration, output, on_submitted=on_submitted)
            return {**base, "provider": job["provider"], "status": "success", "attempts": prev + submitted, "meta": meta}
        except VideoJobError as e:
            err = str(e)
            if e.interaction_id: job["id"] = job["id"] or e.interaction_id
            if e.resumable or (job["id"] and not e.retryable):
                return in_flight(err)  # the job exists and may still finish; never pay for another
            if not e.retryable: break   # refused before any job existed
            job["id"] = None             # the provider says the job failed: a new one is needed
        except Exception as e:
            err = f"{type(e).__name__}: {e}"
            if job["id"]:
                return in_flight(err)
        if submitted < attempts:
            if on_retry: on_retry(f"{err} Submitting a new job ({submitted + 1} of {attempts}).")
            time.sleep(delay)
    return {**base, "status": "failed", "attempts": prev + submitted, "error": err}
