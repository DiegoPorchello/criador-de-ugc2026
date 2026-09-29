from __future__ import annotations
from pathlib import Path
import argparse, concurrent.futures, json, os, sys, threading, shutil
from . import __version__
from .config import load_config, apply_overrides, workspace_path, shared_config_path, shared_config_candidates
from .project import init_project
from .timing import choose_duration
from .pricing import estimate_video_cost, estimate_image_cost
from . import providers
from .providers import google, kie
from .library import slugify, list_avatars, save_avatar, get_avatar, list_series, create_series, archive_video, save_look, list_looks, get_look
from .sequential import current as sequential_current, generate_current as sequential_generate, accept_current as sequential_accept
from .storyboard import storyboard_rows
from .calibration import generate as calibrate_generate, lock as calibrate_lock, unlock as calibrate_unlock, assert_locked_current, compose as compose_calibrated
from . import aroll, avatar, broll, calibration, costs, jobs, workflow


def compose_prompt(pre,beat,post):
    return compose_calibrated(pre,beat,post)

def print_plan(cfg,pl):
    rows=pl["rows"]
    print("\nUGC FORGE PREFLIGHT\n"+"="*70)
    print(f"Video model: {cfg['generation_models']['video']['model']}")
    print(f"Resolution:  {cfg['video']['resolution']} | Aspect: {cfg['video']['aspect_ratio']} | Clips: {len(rows)}\n")
    for r in rows:
        s=r["dialogue"].replace("\n"," ")
        print(f"{r['id']:<18} {r['estimated_natural_seconds']:>4.1f}s -> {r['duration']:>2}s  {r['status']:<12} {s[:34]}")
        if r.get("pacing_warning") and r["status"]!="done": print(f"{'':18} WARNING: {r['pacing_warning']}")
    print("-"*70)
    reuse=sum(1 for r in pl["pending"] if r["status"]=="from calibration")
    print(f"Clips to generate: {sum(1 for r in pl['pending'] if r['status']=='to generate')} | Generated seconds: {pl['seconds']} | Estimated cost: {pl['cost']['display']}"
          +(f" | {reuse} line(s) reuse the approved calibration take (free)" if reuse else ""))
    if not pl["cost"]["priced"]: print(f"Pricing note: {pl['cost']['reason']}")
    print("="*70)

def update_project(p: Path, change) -> dict:
    """Change project.json under its lock."""
    return jobs.update_json(p/"project.json",change,dict)

def approved(a,cfg,cost,question):
    """The cost gate. --max-cost binds a non-interactive --yes to the amount the user actually approved."""
    cap=getattr(a,"max_cost",None)
    if cap is not None:
        if not cost.get("priced"):
            raise RuntimeError(f"Cannot check this against --max-cost: {cost.get('reason','cost unknown').rstrip('.')}. Nothing was generated.")
        if cost["usd"]>cap+1e-9:
            raise RuntimeError(f"Estimated cost {cost['display']} is more than the approved maximum ${cap:.2f}. Nothing was generated; ask the user to approve the new amount.")
    if getattr(a,"yes",False): return True
    if input(f"{question} [y/N]: ").strip().lower() in {"y","yes"}: return True
    print("Cancelled. Nothing was generated."); return False

def add_cost_cap(x):
    x.add_argument("--max-cost",type=float,metavar="USD",help="Refuse if the estimated cost is above this amount (the amount the user approved).")

def common_cfg(project,args):
    return apply_overrides(load_config(project),args)

def cmd_init(a):
    p=Path(a.project).resolve(); init_project(p); print(f"Created: {p}")


def cmd_avatars(a):
    cfg=load_config(Path.cwd()); ws=workspace_path(cfg)
    av=list_avatars(ws)
    if not av: print("No saved avatars.")
    for x in av: print(f"{x['id']:<24} {x['name']}")

def cmd_avatar(a):
    p=Path(a.project).resolve(); cfg=common_cfg(p,a)
    req=avatar.request(p,cfg,a.prompt,a.inputs)
    print(f"Avatar image from: {', '.join(req['inputs'])}")
    print(f"Instruction: {req['prompt'][:160]}{'...' if len(req['prompt'])>160 else ''}")
    print(f"Estimated image cost: {estimate_image_cost(cfg)['display']}")
    if a.plan: print("Plan only: nothing was generated."); return
    if not approved(a,cfg,estimate_image_cost(cfg),"Generate this image?"): return
    try: r=avatar.make(p,cfg,a.prompt,a.inputs)
    finally: costs.refresh(p,cfg)
    print(f"Saved Avatar version {r['attempt']}: {r['current']}")
    print(f"Review it. Generate again to try another version, or go back with `ugc-forge avatar-use {p} VERSION`.")
    if a.name:
        saved=save_avatar(workspace_path(cfg),a.name,p/cfg["paths"]["avatar_reference"],p/cfg["paths"]["avatar_spec"],{},replace=a.replace)
        update_project(p,lambda m: m.__setitem__("avatar_id",saved["id"]))
        print(f"Saved reusable avatar: {saved['name']} ({saved['id']})")

def cmd_set_frame(a):
    """Copy the user's reference frame into the project, in the format its file name expects."""
    from .providers.base import _write_image
    p=Path(a.project).resolve(); cfg=load_config(p)
    src=Path(a.image).expanduser()
    if not src.is_file(): raise FileNotFoundError(f"No image at {src}.")
    try:
        from PIL import Image
        with Image.open(src) as im: im.verify()
    except Exception as e:
        raise RuntimeError(f"{src} isn't an image Forge can read ({type(e).__name__}). Use a JPEG, PNG or WebP still.") from e
    dest=p/cfg["paths"]["source_frame"]; dest.parent.mkdir(parents=True,exist_ok=True)
    _write_image(src.read_bytes(),dest)
    print(f"Reference frame saved: {dest.relative_to(p)} (the original at {src} is untouched)")

def cmd_abandon(a):
    from . import inflight
    p=Path(a.project).resolve(); cfg=load_config(p)
    for h in inflight.abandon(p,cfg,a.beat,a.force):
        seen=f" (its state there: {h['state']})" if h["state"] else ""
        print(f"Abandoned the {h['kind']} job for {a.beat} at {h['provider']}{seen}.")
    print("Forge won't wait for it any more; the next run submits a new job. A job can't be cancelled at the provider: "
          "kie.ai charges when a job starts and refunds it if the job fails, so if it still finishes, that charge stands.")

def cmd_avatar_use(a):
    p=Path(a.project).resolve(); cfg=load_config(p)
    r=avatar.use(p,cfg,a.version); print(f"The Avatar now uses version {r['attempt']}: {r['current']}")

def cmd_save_avatar(a):
    p=Path(a.project).resolve(); cfg=load_config(p)
    ref=p/cfg["paths"]["avatar_reference"]; spec=p/cfg["paths"]["avatar_spec"]
    saved=save_avatar(workspace_path(cfg),a.name,ref,spec,{},replace=a.replace)
    update_project(p,lambda m: m.__setitem__("avatar_id",saved["id"]))
    print(f"Saved avatar: {saved['name']}")

def cmd_use_avatar(a):
    p=Path(a.project).resolve(); cfg=load_config(p); ws=workspace_path(cfg)
    ap,data=get_avatar(ws,a.avatar)
    dst=p/cfg["paths"]["avatar_reference"]; dst.parent.mkdir(parents=True,exist_ok=True)
    avatar.record_copy(p,cfg,lambda: shutil.copy2(ap/"reference.png",dst),f"saved Avatar {data['id']}")
    shutil.copy2(ap/"spec.md",p/cfg["paths"]["avatar_spec"])
    update_project(p,lambda m: m.__setitem__("avatar_id",data["id"]))
    print(f"Using avatar: {data['name']}")

def cmd_series(a):
    cfg=load_config(Path.cwd()); ws=workspace_path(cfg)
    ss=list_series(ws)
    if not ss: print("No series.")
    for x in ss: print(f"{x['id']:<24} {x['name']} ({x.get('video_count',0)} videos)")

def cmd_series_create(a):
    cfg=load_config(Path.cwd()); ws=workspace_path(cfg); existed=(ws/"series"/slugify(a.name)/"series.json").exists()
    data=create_series(ws,a.name,a.avatar)
    print(f"{'Series already exists' if existed else 'Created series'}: {data['name']} ({data['id']}, {data.get('video_count',0)} videos)")

def cmd_attach_series(a):
    p=Path(a.project).resolve(); cfg=load_config(p)
    known=[x["id"] for x in list_series(workspace_path(cfg))]
    if slugify(a.series) not in known:
        raise RuntimeError(f"No series '{a.series}'. Existing series: {', '.join(known) or 'none'}. Create it with `ugc-forge series-create NAME`.")
    update_project(p,lambda m: m.__setitem__("series_id",slugify(a.series)))
    print(f"Attached series: {a.series}")

def cmd_preflight(a):
    p=Path(a.project).resolve(); cfg=common_cfg(p,a); print_plan(cfg,aroll.plan(p,cfg))


def cmd_status(a):
    p=Path(a.project).resolve(); cfg=load_config(p)
    wf=workflow.load(p)
    print(f"Project: {p}")
    print(f"Stage: {wf['stage']} | Approved: {', '.join(k for k,v in wf['approved'].items() if v) or 'nothing yet'}")
    av=avatar.load(p)
    print(f"Avatar image: {'version '+str(av.get('current_attempt')) if av['attempts'] else ('present' if (p/cfg['paths']['avatar_reference']).exists() else 'not made yet')}")
    cal=calibration.load(p)
    print(f"Calibration: {'locked at attempt '+str(cal.get('accepted_attempt')) if cal.get('locked') else str(len(cal['attempts']))+' attempt(s), not locked'}")
    for name,fn in (("A-roll",lambda: aroll.plan(p,cfg)),("B-roll",lambda: broll.plan(p,cfg))):
        try: pl=fn()
        except Exception as e: print(f"{name}: cannot plan yet ({e})"); continue
        if not pl["rows"]: print(f"{name}: nothing to generate"); continue
        counts={}
        for r in pl["rows"]: counts[r["status"]]=counts.get(r["status"],0)+1
        print(f"{name}: {len(pl['rows'])} clip(s): "+", ".join(f"{v} {k}" for k,v in counts.items()))
        for r in pl["rows"]:
            if r["status"]!="done": print(f"  {r['id']:<18} {r['status']}")
    try:
        stills=broll.plan(p,cfg)["stills"]
        if stills: print(f"B-roll stills (not animated): {', '.join(x['id']+('' if x['has_image'] else ' (no image yet)') for x in stills)}")
    except Exception: pass
    c=p/"costs.json"
    if c.exists():
        data=json.loads(c.read_text(encoding="utf-8")); t=data.get("total",{}); fl=data.get("in_flight") or {}
        print(f"Spent so far (estimate): {t.get('cost',{}).get('display','?')}{'' if t.get('complete',True) else ' (some items unpriced)'}"
              +(f", plus about {fl['estimated_cost']['display']} for {fl['clips']} clip(s) still in progress" if fl.get("clips") else ""))
        ab=data.get("abandoned") or {}
        if ab.get("jobs"):
            print(f"Abandoned jobs: {ab['jobs']} (up to about {ab['possible_cost']['display']} if the provider still charged them; kie.ai refunds failed jobs)")

def cmd_stage(a):
    p=Path(a.project).resolve()
    st=workflow.set_stage(p,a.stage) if a.stage else workflow.load(p)
    print(f"Stage: {st['stage']}")

def cmd_approve(a):
    p=Path(a.project).resolve(); st=workflow.approve(p,a.stage,not a.undo)
    print(f"{a.stage}: {'approved' if st['approved'][a.stage] else 'not approved'}")

PROVIDER_CHOICES={"1":"kie","2":"google","kie":"kie","google":"google"}

def _clipboard(clear: bool=False) -> str:
    """Read (or clear) the clipboard, so a key can be entered where hidden typing isn't possible."""
    import platform, subprocess
    system=platform.system()
    if system=="Darwin": read,wipe=["pbpaste"],["pbcopy"]
    elif system=="Windows": read,wipe=["powershell","-NoProfile","-Command","Get-Clipboard"],["powershell","-NoProfile","-Command","Set-Clipboard -Value $null"]
    else: read,wipe=["wl-paste","--no-newline"],None
    try:
        if clear:
            if wipe: subprocess.run(wipe,input="",text=True,check=False,timeout=10)
            return ""
        return subprocess.run(read,capture_output=True,text=True,check=True,timeout=10).stdout
    except (OSError,subprocess.SubprocessError):
        if clear: return ""
        raise RuntimeError("Could not read the clipboard on this computer. Run `ugc-forge setup` in a terminal window instead.")

def _ask(prompt_fn, text: str) -> str:
    try: return prompt_fn(text)
    except (EOFError, OSError) as e:
        # e.g. an agent's shell that can't take typed input
        raise RuntimeError("This window can't take typed input. Copy your API key, then run: "
                           "ugc-forge setup --provider kie --from-clipboard (or --provider google). Nothing was changed.") from e

def cmd_setup(a):
    import getpass, yaml
    target=shared_config_path() or shared_config_candidates()[-1]
    choice=a.provider or PROVIDER_CHOICES.get(_ask(input,
        "Which service should make your images and videos?\n"
        "  1) kie.ai: quick sign-up, prepaid credits, lower prices (recommended)\n"
        "  2) Google AI Studio: needs a Google Cloud billing account\n"
        "Choose 1 or 2 [1]: ").strip().lower() or "1")
    if choice not in ("kie","google"): raise RuntimeError("Please choose 1 (kie.ai) or 2 (Google). Nothing was changed.")
    where={"kie":"https://kie.ai/api-key","google":"https://aistudio.google.com/apikey"}[choice]
    print(f"Your key will be saved in {target} (readable only by you).")
    if a.from_clipboard:
        key=_clipboard().strip()
        if not key or any(c.isspace() for c in key) or len(key)<16:
            raise RuntimeError(f"The clipboard doesn't hold an API key. Copy your key from {where}, then run this again. Nothing was changed.")
        _clipboard(clear=True)
        print("Read the key from the clipboard (not shown) and cleared the clipboard.")
    else:
        print(f"Get a key at {where} if you don't have one. Paste it below; it will not be shown.")
        key=_ask(getpass.getpass,"API key: ").strip()
    if not key: raise RuntimeError("No key entered; nothing was changed.")
    data=(yaml.safe_load(target.read_text(encoding="utf-8")) if target.exists() else {}) or {}
    data["provider"]=choice
    if choice=="kie": data.setdefault("kie",{})["api_key"]=key
    else:
        for kind in ("image","video"):
            data.setdefault("generation_models",{}).setdefault(kind,{})["api_key"]=key
    target.parent.mkdir(parents=True,exist_ok=True)
    # Create the file owner-only before the key is written to it.
    fd=os.open(target,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
    with os.fdopen(fd,"w",encoding="utf-8") as f: yaml.safe_dump(data,f,sort_keys=False)
    os.chmod(target,0o600)
    print("Saved. Checking it (free)...")
    cmd_check(argparse.Namespace(project=None,online=True))

SKILL_TARGETS=(("Claude Code","~/.claude/skills/ugc-forge/SKILL.md"),("Codex and other agents","~/.agents/skills/ugc-forge/SKILL.md"))

def cmd_install_skill(a):
    """Install the skill that ships with this version of the command, so the two always match."""
    from importlib.resources import files
    text=files("ugc_forge").joinpath("skill/SKILL.md").read_text(encoding="utf-8")
    for agent,target in SKILL_TARGETS:
        dest=Path(target).expanduser(); dest.parent.mkdir(parents=True,exist_ok=True)
        dest.write_text(text,encoding="utf-8")
        print(f"Installed the UGC Forge skill for {agent}: {dest}")
    print("Start a new agent session to load it.")

def cmd_check(a):
    ok=True
    print(f"UGC Forge {__version__} on Python {sys.version.split()[0]}")
    p=Path(a.project).resolve() if a.project else Path.cwd()
    cfg=load_config(p); prov=providers.name(cfg)
    src=shared_config_path()
    print(f"Shared settings file: {src if src else 'none found (looked in '+', '.join(str(x) for x in shared_config_candidates())+')'}")
    print(f"Provider: {'kie.ai' if prov=='kie' else 'Google'}")
    if prov=="kie":
        try: kie.resolve_api_key(cfg["kie"]); print("kie.ai API key: found")
        except RuntimeError as e: ok=False; print(f"kie.ai API key: MISSING. {e}")
        if ok and a.online:
            try:
                bal=kie.credits(cfg); kc=cfg["cost"]["kie"]; rate=kc["usd_per_credit"]
                print(f"kie.ai accepted the key. Balance: {bal:g} credits (about ${bal*rate:.2f}).")
                res=str(cfg["video"]["resolution"]).lower()
                clip=min((kc.get("video_credits") or {}).get(res,{}).values() or [63]); img=kc.get("image_credits") or 18
                if bal<clip:
                    ok=False; print(f"That isn't enough for one video clip ({clip} credits at {res}). Add credits at https://kie.ai before generating.")
                else:
                    print(f"Enough for about {int(bal//clip)} short {res} clips or {int(bal//img)} images.")
            except kie.KieError as e: ok=False; print(f"kie.ai check failed: {e}")
    else:
        for kind in ("image","video"):
            pcfg=cfg["generation_models"][kind]
            try: google.resolve_api_key(pcfg); print(f"{kind.capitalize()} API key: found ({pcfg['model']})")
            except RuntimeError as e: ok=False; print(f"{kind.capitalize()} API key: MISSING. {e}")
        if ok and a.online:
            try:
                client=google._client(cfg["generation_models"]["video"])  # keep a reference: the pager needs the client open
                names={m.name.split('/')[-1] for m in client.models.list()}
                for kind in ("image","video"):
                    m=cfg["generation_models"][kind]["model"]
                    print(f"{m}: {'available' if m in names else 'NOT available to this key'}"); ok&=m in names
            except Exception as e:
                ok=False; print(f"Could not reach Google with this key: {type(e).__name__}: {e}")
    if not ok: raise RuntimeError("Setup is incomplete; see above.")
    print("Setup looks good." if a.online else "Keys found. Run with --online to confirm them (free).")

def cmd_generate(a):
    p=Path(a.project).resolve(); cfg=common_cfg(p,a)
    if cfg["generation"].get("mode","batch") == "sequential":
        raise RuntimeError("Project is in sequential mode. Use `ugc-forge next PROJECT`, then `ugc-forge generate-next PROJECT` and `ugc-forge accept PROJECT`.")
    assert_locked_current(p,cfg)
    pl=aroll.plan(p,cfg,a.redo); print_plan(cfg,pl)
    for r in [r for r in pl["pending"] if r["status"]=="from calibration"]:
        aroll.adopt_calibration(p,r); print(f"[FROM CALIBRATION] {r['id']}: using the approved calibration take (no charge)")
    pl["pending"]=[r for r in pl["pending"] if r["status"]!="from calibration"]
    if not pl["pending"]:
        costs.refresh(p,cfg); print("All A-roll clips are up to date."); return
    if not approved(a,cfg,pl["cost"],"\nProceed with chargeable generation?"): return
    ref=p/cfg["paths"]["avatar_reference"]
    if not ref.exists(): raise FileNotFoundError(f"Missing avatar reference image: {ref}")
    s=aroll.update(p,lambda st: st.__setitem__("preflight",{"seconds":pl["seconds"],"estimated_cost":pl["cost"]}))
    lock=threading.Lock()
    def persist(bid,record):
        with lock:
            if record.get("status")=="pending" and s["clips"].get(bid,{}).get("interaction_id")!=record.get("interaction_id"):
                print(f"[SUBMITTED] {bid}",flush=True)
            s["clips"][bid]=record
            aroll.update(p,lambda st: st["clips"].__setitem__(bid,record))
    print(f"Generating {len(pl['pending'])} clip(s), {int(cfg['generation']['concurrency'])} at a time; each usually takes one to two minutes. "
          "If this is interrupted, rerun the same command: clips already paid for are collected, not paid for again.",flush=True)
    def worker(r):
        extra={"fingerprint":r["fingerprint"],"content_fingerprint":r["content_fingerprint"],"output":str(r["output"].relative_to(p))}
        return r["id"],jobs.run_clip(r["prompt"],ref,cfg,r["duration"],r["output"],s["clips"].get(r["id"],{}),
                                     lambda rec: persist(r["id"],rec),extra,on_retry=lambda msg: print(f"[RETRYING] {r['id']}: {msg}"))
    done=[r for r in pl["rows"] if r["status"]=="done"]
    for r in done: jobs.place_output(p,s["clips"][r["id"]],r["output"])
    if done: aroll.update(p,lambda st: st["clips"].update({r["id"]:s["clips"][r["id"]] for r in done}))
    with concurrent.futures.ThreadPoolExecutor(max_workers=int(cfg["generation"]["concurrency"])) as ex:
        for fut in concurrent.futures.as_completed([ex.submit(worker,r) for r in pl["pending"]]):
            bid,cs=fut.result(); persist(bid,cs)
            print(f"[{cs['status'].upper()}] {bid}"+(f": {cs['error']}" if cs.get("error") else ""))
    costs.refresh(p,cfg)
    unfinished={k:c["status"] for k,c in s["clips"].items() if k in {r["id"] for r in pl["pending"]} and c.get("status")!="success"}
    if unfinished:
        waiting=[k for k,v in unfinished.items() if v=="pending"]; failed=[k for k,v in unfinished.items() if v=="failed"]
        msg=[]
        if failed: msg.append(f"{len(failed)} clip(s) failed: {', '.join(failed)}")
        if waiting: msg.append(f"{len(waiting)} clip(s) are still generating or downloading at the provider: {', '.join(waiting)}")
        raise RuntimeError("; ".join(msg)+f". Rerun `ugc-forge generate {p} --yes` to collect or retry them; clips already paid for are not paid for again.")
    print(f"A-roll clips saved in {p/cfg['paths'].get('a_roll_output',cfg['paths']['output'])}")

def cmd_archive(a):
    p=Path(a.project).resolve(); cfg=load_config(p); meta=json.loads((p/"project.json").read_text(encoding="utf-8"))
    sid=a.series or meta.get("series_id")
    if not sid: raise RuntimeError("No series attached. Pass --series.")
    sid=slugify(sid)  # the same series however it was typed ("My Series" and "my-series")
    beats=aroll.load_beats(p,cfg)
    manifest={"title":a.title or meta.get("title") or p.name,"avatar_id":meta.get("avatar_id"),
              "series_id":sid,"beats":beats}
    if meta.get("archived_as",{}).get(sid):
        raise RuntimeError(f"This project is already archived in '{sid}' as {meta['archived_as'][sid]}.")
    vid=archive_video(workspace_path(cfg),sid,p,manifest)
    update_project(p,lambda m: m.setdefault("archived_as",{}).__setitem__(sid,vid))
    print(f"Archived as {vid}")


def cmd_next(a):
    p=Path(a.project).resolve(); cfg=common_cfg(p,a)
    item,state=sequential_current(p,cfg)
    if item is None:
        print("Sequential generation complete."); return
    b=item["beat"]
    print(f"Beat {item['index']}: {item['id']}")
    print(f"Dialogue: {b['dialogue']}")
    if b.get("direction"): print(f"Direction: {b['direction']}")
    print(f"Natural estimate: {item['estimated_natural_seconds']}s -> generation: {item['duration']}s")
    print(f"Estimated next-generation cost: {item['estimated_cost']['display']}")
    attempts=[x for x in state["clips"].get(item["id"],{}).get("attempts",[]) if x.get("status")=="success" and x.get("fingerprint")==item["fingerprint"]]
    if attempts: print(f"Attempts to review: {', '.join(str(x['attempt'])+': '+x['output'] for x in attempts)} (accept one with `ugc-forge accept {p}`, or `--attempt N`)")

def cmd_generate_next(a):
    p=Path(a.project).resolve(); cfg=common_cfg(p,a)
    item,state=sequential_current(p,cfg)
    if item is None:
        print("Sequential generation complete."); return
    print(f"Next: {item['id']} | {item['duration']}s | estimated {item['estimated_cost']['display']}")
    if not approved(a,cfg,item["estimated_cost"],"Generate this clip?"): return
    try: item,attempt=sequential_generate(p,cfg)
    finally: costs.refresh(p,cfg)
    print(f"Generated {item['id']} attempt {attempt['attempt']}: {attempt['output']}")
    print(f"Review it. Then generate this line again, or accept it with `ugc-forge accept {p}`.")

def cmd_accept(a):
    p=Path(a.project).resolve(); cfg=common_cfg(p,a)
    nxt,state=sequential_accept(p,cfg,a.attempt)
    if nxt is None:
        print("Accepted. Sequential generation complete.")
    else:
        print(f"Accepted. Next beat: {nxt['id']}")



def cmd_storyboard(a):
    p=Path(a.project).resolve(); cfg=load_config(p)
    beats=aroll.load_beats(p,cfg)
    print(f"{'ID':<18} {'A-ROLL':<8} {'OVERLAY':<14} SPOKEN / ON SCREEN")
    print("-"*96)
    for r in storyboard_rows(beats):
        print(f"{r['id']:<18} {str(r['a_roll']):<8} {r['overlay']:<14} {r['spoken'][:40]}")
        if r["on_screen"]: print(f"{'':42} -> {r['on_screen']}")

def cmd_save_look(a):
    p=Path(a.project).resolve(); cfg=load_config(p); meta=json.loads((p/"project.json").read_text(encoding="utf-8"))
    aid=a.avatar or meta.get("avatar_id")
    if not aid: raise RuntimeError("No avatar selected. Pass --avatar.")
    data=save_look(workspace_path(cfg),aid,a.name,p/cfg["paths"]["avatar_reference"],p/cfg["paths"]["avatar_spec"],{},replace=a.replace)
    update_project(p,lambda m: m.update(avatar_id=aid,look_id=data["id"]))
    print(f"Saved look: {aid}/{data['id']}")

def cmd_looks(a):
    cfg=load_config(Path.cwd())
    items=list_looks(workspace_path(cfg),a.avatar)
    if not items: print("No looks.")
    for x in items: print(f"{x['id']:<24} {x['name']}")

def cmd_use_look(a):
    p=Path(a.project).resolve(); cfg=load_config(p); ws=workspace_path(cfg)
    lp,data=get_look(ws,a.avatar,a.look)
    avatar.record_copy(p,cfg,lambda: shutil.copy2(lp/"reference.png",p/cfg["paths"]["avatar_reference"]),f"saved Look {a.avatar}/{data['id']}")
    shutil.copy2(lp/"spec.md",p/cfg["paths"]["avatar_spec"])
    update_project(p,lambda m: m.update(avatar_id=a.avatar,look_id=data["id"]))
    print(f"Using look: {a.avatar}/{data['id']}")

def cmd_calibrate(a):
    p=Path(a.project).resolve(); cfg=common_cfg(p,a)
    bid,beat=calibration.select_beat(p,cfg,a.beat)
    natural,duration=choose_duration(beat["dialogue"],cfg["timing"],beat.get("duration"))
    cost=estimate_video_cost(cfg,duration)
    print(f"Calibration: {bid} | {duration}s | estimated {cost['display']}")
    if a.plan: print("Plan only: nothing was generated."); return
    if not approved(a,cfg,cost,"Generate this chargeable calibration clip?"): return
    try: item=calibrate_generate(p,cfg,a.beat)
    finally: costs.refresh(p,cfg)
    print(f"Calibration attempt {item['attempt']}: {item['output']}")
    print("Review realism, voice, cadence, energy, expression, eye contact, camera stability and framing. Revise scene/fixed rules and regenerate until satisfied.")

def cmd_lock_prompt(a):
    p=Path(a.project).resolve(); cfg=load_config(p); state=calibrate_lock(p,cfg,a.attempt)
    print(f"Prompt locked at calibration attempt {state['accepted_attempt']}.")

def cmd_unlock_prompt(a):
    p=Path(a.project).resolve(); calibrate_unlock(p); print("Prompt calibration unlocked.")


def cmd_broll(a):
    p=Path(a.project).resolve(); cfg=common_cfg(p,a)
    if not broll.items(p,cfg):
        print("No generated B-roll (avatar_broll or scene_broll) in the storyboard."); return
    pl=broll.plan(p,cfg,a.only,a.redo)
    print("\nUGC FORGE B-ROLL\n"+"="*70)
    print(f"Resolution: {cfg['video']['resolution']} | Aspect: {cfg['video']['aspect_ratio']}\n")
    for r in pl["rows"]:
        print(f"{r['id']:<18} {r['duration']:>2}s  {r['status']:<12} {r['animation_prompt'][:44]}")
        if r["stale_inputs"]:
            print(f"{'':18} WARNING: made from an older version of {', '.join(r['stale_inputs'])}; remake it with broll-image if that matters.")
    if pl["stills"]:
        print(f"Stills, not animated: {', '.join(x['id']+('' if x['has_image'] else ' (no image yet)') for x in pl['stills'])}")
    print("-"*70)
    print(f"Clips to generate: {len(pl['pending'])} | Generated seconds: {pl['seconds']} | Estimated video cost: {pl['cost']['display']}")
    print("="*70)
    need=("Make these B-roll images first: "+", ".join(pl["missing"])+f". Use: ugc-forge broll-image {p} BEAT_ID") if pl["missing"] else None
    if a.plan:
        if need: print(need)
        return
    if need: raise RuntimeError(need)
    if not pl["pending"]:
        print("All B-roll clips are up to date."); return
    if not approved(a,cfg,pl["cost"],"\nProceed with chargeable B-roll generation?"): return
    try: state=broll.animate(p,cfg,a.only,lambda bid,r: print(f"[{r['status'].upper()}] {bid}"+(f": {r['error']}" if r.get("error") else "")),a.redo)
    finally: costs.refresh(p,cfg)
    ran=[r["id"] for r in pl["pending"]]
    failed=[k for k in ran if state["clips"].get(k,{}).get("status")=="failed"]
    waiting=[k for k in ran if state["clips"].get(k,{}).get("status")=="pending"]
    if failed or waiting:
        msg=([f"{len(failed)} B-roll clip(s) failed: {', '.join(failed)}"] if failed else [])+([f"{len(waiting)} still generating or downloading at the provider: {', '.join(waiting)}"] if waiting else [])
        raise RuntimeError("; ".join(msg)+f". Rerun `ugc-forge broll {p} --yes` to collect or retry them; clips already paid for are not paid for again.")
    print(f"B-roll clips saved in {broll.out_dir(p,cfg)}")

def cmd_broll_image(a):
    p=Path(a.project).resolve(); cfg=common_cfg(p,a)
    if a.model:
        if providers.name(cfg)!="google": raise RuntimeError("--model only applies with the Google provider; kie.ai uses Nano Banana Pro (gemini-3-pro-image).")
        cfg["generation_models"]["broll_image"]["model"]=a.model
    if a.inputs==["none"]: a.inputs=[]
    req=broll.image_request(p,cfg,a.beat,a.prompt,a.inputs)
    print(f"B-roll image for {req['id']}")
    print(f"Inputs: {', '.join(req['inputs']) or 'none (made from the description alone)'}")
    print(f"Prompt: {req['prompt']}")
    cost=estimate_image_cost(cfg,"broll_image")
    model=kie.IMAGE_MODEL if providers.name(cfg)=="kie" else cfg['generation_models']['broll_image']['model']
    print(f"Image model: {model} | Estimated image cost: {cost['display']}")
    if a.plan: print("Plan only: nothing was generated."); return
    if not approved(a,cfg,cost,"Generate this image?"): return
    try: r=broll.make_image(p,cfg,a.beat,a.prompt,a.inputs)
    finally: costs.refresh(p,cfg)
    print(f"Saved version {r['attempt']}: {r['current']}")
    print(f"Review it. To edit this image: ugc-forge broll-image {p} {a.beat} --from {a.beat} --prompt \"...\". To go back: ugc-forge broll-use {p} {a.beat} VERSION")

def cmd_broll_use(a):
    p=Path(a.project).resolve(); cfg=load_config(p)
    r=broll.use_image(p,cfg,a.beat,a.version)
    print(f"{a.beat} now uses image version {r['attempt']}: {r['current']}")


def add_common(x):
    x.add_argument("--resolution",choices=["360p","720p","1080p","4k"])
    x.add_argument("--aspect-ratio",dest="aspect_ratio",choices=["9:16","16:9"])
    x.add_argument("--concurrency",type=int); x.add_argument("--max-retries",dest="max_retries",type=int)

def main():
    ap=argparse.ArgumentParser(prog="ugc-forge"); ap.add_argument("--version",action="version",version=f"ugc-forge {__version__}")
    sp=ap.add_subparsers(dest="command",required=True)
    x=sp.add_parser("init"); x.add_argument("project"); x.set_defaults(func=cmd_init)
    x=sp.add_parser("avatars"); x.set_defaults(func=cmd_avatars)
    x=sp.add_parser("storyboard"); x.add_argument("project"); x.set_defaults(func=cmd_storyboard)
    x=sp.add_parser("looks"); x.add_argument("avatar"); x.set_defaults(func=cmd_looks)
    x=sp.add_parser("save-look"); x.add_argument("project"); x.add_argument("name"); x.add_argument("--avatar"); x.add_argument("--replace",action="store_true"); x.set_defaults(func=cmd_save_look)
    x=sp.add_parser("use-look"); x.add_argument("project"); x.add_argument("avatar"); x.add_argument("look"); x.set_defaults(func=cmd_use_look)
    x=sp.add_parser("calibrate"); x.add_argument("project"); x.add_argument("--beat"); x.add_argument("--yes",action="store_true"); add_common(x); add_cost_cap(x)
    x.add_argument("--plan",action="store_true",help="Show what would be generated and its cost, without generating."); x.set_defaults(func=cmd_calibrate)
    x=sp.add_parser("lock-prompt"); x.add_argument("project")
    x.add_argument("--attempt",type=int,help="Lock this calibration attempt instead of the latest."); x.set_defaults(func=cmd_lock_prompt)
    x=sp.add_parser("unlock-prompt"); x.add_argument("project"); x.set_defaults(func=cmd_unlock_prompt)
    x=sp.add_parser("avatar"); x.add_argument("project"); x.add_argument("--name"); x.add_argument("--replace",action="store_true"); add_common(x)
    x.add_argument("--prompt",help="Image instruction; defaults to avatar/spec.md.")
    x.add_argument("--from",dest="inputs",nargs="+",metavar="INPUT",help="Input images: source (default), avatar (the current Avatar image, e.g. for a new Look), or a project file path.")
    x.add_argument("--yes",action="store_true"); add_cost_cap(x); x.add_argument("--plan",action="store_true",help="Show what would be generated and its cost, without generating."); x.set_defaults(func=cmd_avatar)
    x=sp.add_parser("abandon",help="Stop waiting for a job in progress, so the next run submits a new one."); x.add_argument("project"); x.add_argument("beat")
    x.add_argument("--force",action="store_true",help="Abandon even if the provider says the job has finished."); x.set_defaults(func=cmd_abandon)
    x=sp.add_parser("set-frame",help="Copy your reference frame into the project."); x.add_argument("project"); x.add_argument("image"); x.set_defaults(func=cmd_set_frame)
    x=sp.add_parser("avatar-use"); x.add_argument("project"); x.add_argument("version",type=int); x.set_defaults(func=cmd_avatar_use)
    x=sp.add_parser("save-avatar"); x.add_argument("project"); x.add_argument("name"); x.add_argument("--replace",action="store_true"); x.set_defaults(func=cmd_save_avatar)
    x=sp.add_parser("use-avatar"); x.add_argument("project"); x.add_argument("avatar"); x.set_defaults(func=cmd_use_avatar)
    x=sp.add_parser("series"); x.set_defaults(func=cmd_series)
    x=sp.add_parser("series-create"); x.add_argument("name"); x.add_argument("--avatar"); x.set_defaults(func=cmd_series_create)
    x=sp.add_parser("attach-series"); x.add_argument("project"); x.add_argument("series"); x.set_defaults(func=cmd_attach_series)
    x=sp.add_parser("preflight"); x.add_argument("project"); add_common(x); x.set_defaults(func=cmd_preflight)
    x=sp.add_parser("generate"); x.add_argument("project"); add_common(x); x.add_argument("--yes",action="store_true"); add_cost_cap(x)
    x.add_argument("--redo",nargs="+",metavar="BEAT_ID",help="Regenerate only these beats, even if their clips are done."); x.set_defaults(func=cmd_generate)
    x=sp.add_parser("broll"); x.add_argument("project"); add_common(x); x.add_argument("--yes",action="store_true"); add_cost_cap(x)
    x.add_argument("--plan",action="store_true",help="Show the B-roll plan and cost without generating.")
    x.add_argument("--only",nargs="+",metavar="BEAT_ID",help="Limit to these B-roll beats.")
    x.add_argument("--redo",nargs="+",metavar="BEAT_ID",help="Regenerate only these B-roll clips, even if they are done."); x.set_defaults(func=cmd_broll)
    x=sp.add_parser("broll-image"); x.add_argument("project"); x.add_argument("beat"); add_common(x); add_cost_cap(x)
    x.add_argument("--prompt",help="Image instruction; defaults to the beat's overlay.prompt or description.")
    x.add_argument("--from",dest="inputs",nargs="+",metavar="INPUT",help="Input images: avatar, source, a B-roll beat id, a project file path, or none for a new scene from the description alone.")
    x.add_argument("--model",choices=sorted(google.SUPPORTED_IMAGE_MODELS),help="Image model for this image; gemini-3.1-flash-image is half the price and suits simple edits.")
    x.add_argument("--yes",action="store_true"); x.add_argument("--plan",action="store_true",help="Show what would be generated and its cost, without generating."); x.set_defaults(func=cmd_broll_image)
    x=sp.add_parser("broll-use"); x.add_argument("project"); x.add_argument("beat"); x.add_argument("version",type=int); x.set_defaults(func=cmd_broll_use)
    x=sp.add_parser("status"); x.add_argument("project"); x.set_defaults(func=cmd_status)
    x=sp.add_parser("stage"); x.add_argument("project"); x.add_argument("stage",nargs="?",choices=workflow.STAGES); x.set_defaults(func=cmd_stage)
    x=sp.add_parser("approve"); x.add_argument("project"); x.add_argument("stage",choices=workflow.STAGES); x.add_argument("--undo",action="store_true"); x.set_defaults(func=cmd_approve)
    x=sp.add_parser("setup",help="Choose kie.ai or Google and save your API key privately.")
    x.add_argument("--provider",choices=["kie","google"],help="Skip the question and use this service.")
    x.add_argument("--from-clipboard",action="store_true",help="Read the key from the clipboard (then clear it) instead of typing it."); x.set_defaults(func=cmd_setup)
    x=sp.add_parser("install-skill",help="Install the matching agent skill for Claude Code and Codex."); x.set_defaults(func=cmd_install_skill)
    x=sp.add_parser("check"); x.add_argument("project",nargs="?"); x.add_argument("--online",action="store_true",help="Confirm the keys and models with Google (free)."); x.set_defaults(func=cmd_check)
    x=sp.add_parser("next"); x.add_argument("project"); add_common(x); x.set_defaults(func=cmd_next)
    x=sp.add_parser("generate-next"); x.add_argument("project"); add_common(x); x.add_argument("--yes",action="store_true"); add_cost_cap(x); x.set_defaults(func=cmd_generate_next)
    x=sp.add_parser("accept"); x.add_argument("project"); add_common(x)
    x.add_argument("--attempt",type=int,help="Accept this attempt instead of the latest."); x.set_defaults(func=cmd_accept)
    x=sp.add_parser("archive"); x.add_argument("project"); x.add_argument("--series"); x.add_argument("--title"); x.set_defaults(func=cmd_archive)
    a=ap.parse_args()
    # Progress must appear as it happens, even when an agent captures or backgrounds the output.
    if hasattr(sys.stdout,"reconfigure"): sys.stdout.reconfigure(line_buffering=True)
    try: a.func(a)
    except BrokenPipeError:
        # The reader stopped early (e.g. output piped into `head`); exit quietly as other command-line tools do.
        os.dup2(os.open(os.devnull,os.O_WRONLY),sys.stdout.fileno()); sys.exit(0)
    except KeyboardInterrupt: print("\nInterrupted.",file=sys.stderr); sys.exit(130)
    except Exception as e: sys.stdout.flush(); print(f"Error: {e}",file=sys.stderr); sys.exit(1)
if __name__=="__main__": main()
