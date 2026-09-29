---
name: ugc-forge
description: Plan and produce raw AI-presented A-roll and B-roll source clips from reference-driven fictional avatars. Guides concept, storyboard, Avatar/Look creation, calibration, cost approval, generation and reusable series state. Final editing happens elsewhere.
---

# UGC Forge production skill

Use this skill for reference-driven AI-presented video production: UGC ads, social shorts, explainers and recurring Avatar-led creator content.

UGC Forge produces organised **raw source clips**. It is not a video editor. Do not attempt to turn the workflow into a compositing, captioning, music or final-export system unless the user explicitly asks to use a separate editing tool after Forge has finished.

## Core production decisions

### Full A-roll is the v1 default

Generate every spoken storyboard beat as A-roll, including dialogue that will eventually be covered by B-roll.

B-roll is an overlay on top of the A-roll in the final edit. Do not skip the underlying A-roll merely because the storyboard calls for B-roll at that point.

This intentionally spends some generation budget on footage that may not be visible in the final edit. The benefit is a clean, consistent generated audio/performance track without requiring a separate voice-cloning workflow.

Selective A-roll is not part of the default v1 workflow.

### Forge stops at source clips

Forge should finish with organised A-roll, generated Avatar B-roll, references and storyboard/project state.

The user can edit those assets later in CapCut, Premiere Pro, DaVinci Resolve, Remotion, FFmpeg or another editor.

### Prefer the reference over the prompt

Keep prompts short, plain and intentional across the entire workflow: Avatar creation, Looks, A-roll and B-roll.

Do not automatically expand a user's direction into a large “AI prompt”. Do not add generic realism language such as “hyper-realistic”, “8K”, “visible pores”, “skin imperfections”, “cinematic realism” or exhaustive incidental background descriptions merely because the media is AI-generated.

Describe the meaningful action, change, scene or performance and let the reference carry visual information already established.

Example B-roll image direction:

> Marco sits outside a café drinking coffee. He is wearing a dark turtleneck and looking into the distance, relaxed.

Example A-roll direction:

> Static phone camera. Marco speaks directly to camera with calm, measured delivery and subtle natural movement.

Start simple. Generate. Observe a real failure. Add a constraint only when it addresses that failure.

If repeated generations fail for a fundamental reason, reconsider the reference/Look instead of endlessly growing the prompt.

## Persistent workflow state

The project folder is the source of truth. Start every session with:

```bash
ugc-forge status PROJECT_DIR
```

It shows the current stage, approvals, Avatar version, calibration, which A-roll and B-roll clips are done or outstanding, and spend so far. Change the stage and record approvals with commands, never by editing `workflow.json`:

```bash
ugc-forge stage PROJECT_DIR beats
ugc-forge approve PROJECT_DIR beats
ugc-forge approve PROJECT_DIR beats --undo
```

This is not a one-shot wizard. Creative stages are iterative and can move backwards.

Stages:

1. `source`
2. `avatar_design`
3. `avatar_review`
4. `concept`
5. `beats`
6. `prompt_review`
7. `calibration`
8. `preflight`
9. `cost_approval`
10. `a_roll_generation`
11. `b_roll_generation`
12. `complete`

Do not advance a creative stage merely because a draft exists. Advance after explicit approval or a clear request to continue.

When upstream inputs change, invalidate affected downstream approvals, especially cost approval when billable generation can change.

## Local setup and credentials

This skill is for **ugc-forge 0.9.0**. Before any other Forge work, run `ugc-forge --version`:

- If the command is not found, check the folder printed by `uv tool dir --bin` (usually `~/.local/bin`) and, when working inside the Forge repository, `.venv/bin/`. Use the full path if it is not on PATH.
- If it is not installed anywhere, or its version is older than 0.9.0, install or update it by following https://raw.githubusercontent.com/indygill/ugc-forge/main/INSTALL.md, then continue.
- If its version is newer than 0.9.0, this skill is out of date: run `ugc-forge install-skill` (unless the skill came from the Claude Code plugin, in which case update the plugin) and ask the user to start a new session.

The pipeline reads `generation_models.image.api_key` and `generation_models.video.api_key` from the installation root `config.yaml`. New video projects inherit these credentials automatically without copying them into their own config. Project keys take precedence; environment variables named by `api_key_env` remain a fallback. Do not ask the user to state credential paths in the creative request or export keys already saved in config.

Check setup with:

```bash
ugc-forge check --online
```

It reports which service is in use (kie.ai or Google), whether its key is found and accepted (for kie.ai, the credit balance; for Google, that both models are available), without printing any key; the online check is free. If a key is missing, ask which service the user wants (kie.ai, recommended, or Google), have them copy their key, and ask them to type `! ugc-forge setup --provider kie --from-clipboard` (or `--provider google`) in Claude Code, or run `ugc-forge setup` in a terminal. The key is read privately and never shown. Never ask the user to paste a key into the chat, and never read, print or copy key values into prompts, briefs, logs or project files.

## Entry / resume

On invocation:

1. locate or create the project (`ugc-forge init` refuses a folder that already holds a project, so it is safe to run; never delete project files to get around it);
2. run `ugc-forge status PROJECT_DIR`;
3. resume the active stage rather than restarting the interview;
4. determine whether the user is creating or reusing an Avatar;
5. determine whether the video is one-off or belongs to a Series;
6. enter the earliest incomplete stage.

The user may move backwards at any time.

## Source reference

Ask for a still frame the user is entitled to use. Prefer genuine captured footage where the composition, lighting, perspective and environment are useful to the intended production.

Put the frame into the project with:

```bash
ugc-forge set-frame PROJECT_DIR /path/to/their/image.jpg
```

It accepts JPEG, PNG or WebP from anywhere (Desktop, Downloads) and leaves the original untouched.

Assess framing, camera angle/distance, lighting, background depth, pose, contamination from captions/overlays and provenance. Captions or on-screen text in the frame tend to reappear in generated images; if the frame has any, add "Remove any captions or on-screen text" to the Avatar spec.

The source is a composition/environment reference. Do not preserve or imitate the source person's identity. The workflow creates a new fictional Avatar.

## Avatar design

Collaboratively maintain `avatar/spec.md`.

Gather only useful characteristics: broad appearance, approximate age, hair, clothing, presentation, voice/accent/performance where known, requested environmental changes and important framing constraints.

Avoid bloating the image prompt with generic realism descriptors.

Image-generation iterations should return to the **original source frame + complete current Avatar specification**, rather than progressively editing an already edited candidate.

When the user approves generating (show the estimated image cost first):

```bash
ugc-forge avatar PROJECT_DIR --yes --max-cost AMOUNT
```

`avatar` refuses to run while `avatar/spec.md` still holds the template text. Every version is kept; to go back to one the user preferred:

```bash
ugc-forge avatar-use PROJECT_DIR VERSION
```

Review and iterate without a fixed revision limit. Save an approved Avatar when useful. Saving under a name that already exists is refused; only pass `--replace` when the user has confirmed they want to overwrite that saved Avatar or Look.

## Avatar and Look

An **Avatar** is the reusable fictional character and general performance profile.

A **Look** is that Avatar in a specific scene/framing/wardrobe/accessory setup with a production reference image.

Do not create separate location, wardrobe, microphone or pose libraries in v1. Those details belong to Looks or individual B-roll references.

For recurring creator channels, prefer reusing the established Avatar and appropriate Look rather than recreating the presenter for every episode:

```bash
ugc-forge use-avatar PROJECT_DIR AVATAR_ID
ugc-forge use-look PROJECT_DIR AVATAR_ID LOOK_ID
```

To create a new Look, start from the saved Avatar's image and a frame of the new scene, then save it:

```bash
ugc-forge use-avatar PROJECT_DIR AVATAR_ID
ugc-forge avatar PROJECT_DIR --from avatar source --prompt "The man in the first image, sitting in the room from the second image, wearing a grey jumper." --yes --max-cost AMOUNT
ugc-forge save-look PROJECT_DIR "Kitchen, grey jumper"
```

Other library commands: `ugc-forge avatars`, `ugc-forge looks AVATAR_ID`, `ugc-forge save-avatar PROJECT_DIR NAME`, `ugc-forge series`, `ugc-forge series-create NAME`, `ugc-forge attach-series PROJECT_DIR SERIES_ID`, `ugc-forge archive PROJECT_DIR`.

## Concept

Agree what the video is trying to do before finalising beats.

Discuss the premise, viewer payoff, hook, argument/reveal, intended tone, approximate length and likely A-roll/B-roll treatment.

For recurring Avatar-led creator content, the human creator should supply or approve the underlying idea, opinion, explanation or argument. Do not turn the workflow into automatic scraped-content production.

## Storyboard / beats

`beats.json` represents the spoken timeline and planned visual overlays.

Every spoken beat is A-roll by default:

```json
{
  "id": "hook",
  "dialogue": "Why does everyone put their TV up here?",
  "a_roll": true,
  "overlay": null
}
```

A supplied B-roll overlay:

```json
{
  "id": "example",
  "dialogue": "You're sitting down here, and your television is halfway to the ceiling.",
  "a_roll": true,
  "overlay": {
    "type": "broll",
    "description": "Wide shot demonstrating an excessively high TV",
    "asset": "high-tv-example.mp4"
  }
}
```

Generated B-roll featuring the Avatar:

```json
{
  "id": "demonstration",
  "dialogue": "So every evening you're basically doing this.",
  "a_roll": true,
  "overlay": {
    "type": "avatar_broll",
    "description": "Marco sits on the sofa in the second image, looking up at the TV.",
    "inputs": ["avatar", "room"],
    "animation_prompt": "Marco cranes his neck up at the TV.",
    "duration": 6
  }
}
```

Generated B-roll without the Avatar (a room, product or object shot):

```json
{
  "id": "room",
  "dialogue": "Here's the room.",
  "a_roll": true,
  "overlay": {
    "type": "scene_broll",
    "description": "Remove the person. Keep the room exactly as it is.",
    "inputs": ["source"],
    "animation_prompt": "Slow push-in.",
    "duration": 4
  }
}
```

Generated overlay fields:

- `description` (or `prompt`): the image instruction. Keep it short and describe the change.
- `inputs`: images the instruction applies to, in order. `avatar` is the Avatar reference, `source` the original frame, a B-roll beat id is that beat's current image, anything else is a project file path. Defaults: `["avatar"]` for `avatar_broll`, `["source"]` for `scene_broll`. `[]` makes a new scene from the description alone (on the command line: `--from none`).
- `animation_prompt`: the motion for the clip, stating the action to keep ("He keeps looking up at the TV, then sighs."). Write one for every shot. The config fallback, `broll.default_animation_prompt`, does not preserve the pose: in a live test the Avatar stopped looking up and turned to camera.
- `duration`: whole seconds from `timing.supported_durations`; defaults to `broll.default_duration`.
- `animate`: set to `false` for a shot that will be used as a still image in the edit. Forge makes its image but never animates it, and the plan lists it separately.

The overlay describes what may cover the A-roll in the final edit. It does not remove the underlying A-roll generation.

Supported overlay concepts include supplied B-roll, Avatar B-roll, stills, graphics and other editor assets.

## A-roll prompt review

Maintain:

- `prompts/scene.md`
- `prompts/fixed-rules.md`

Composition is:

```text
scene
+ dialogue
+ exceptional beat override, if any
+ fixed rules
```

Start with a minimal scene/performance description. `prompt_override` is exceptional; do not invent a unique production prompt for every line.

Once calibrated, the normal change between A-roll clips is dialogue.

Voice and accent: the video model has no voice or audio reference, so the voice comes only from the words. In one run, accent wording in the middle of the scene description was ignored; the voice only changed once the scene ended with a named speaker and the voice description immediately before the dialogue, for example `Raj, a British-Indian man in his sixties, speaks in a warm, measured voice:`. Try that shape first when the voice matters.

Pronunciation: if a word comes out wrong (a brand name, an acronym), suggest a phonetic spelling in the dialogue, such as "Open A.I." for OpenAI, and ask the user before changing their words.

## Calibration

Choose a representative A-roll beat and test the actual animation/performance before production.

Before the chargeable request, show the selected duration and estimated video cost and obtain explicit approval.

```bash
ugc-forge calibrate PROJECT_DIR --beat BEAT_ID
```

Review voice/accent, cadence, energy, expression, eye contact, movement, framing, camera behaviour and unwanted cuts.

When the user identifies a problem, change the smallest useful instruction and regenerate the **same beat**.

Do not pre-emptively stack defensive prompt rules.

When approved:

```bash
ugc-forge lock-prompt PROJECT_DIR
```

When nothing about that line changes afterwards, the approved take is reused as the line's finished clip: preflight shows it as "from calibration" and `generate` copies it instead of paying again. This locks the latest successful calibration clip. To lock an earlier take the user preferred, pass `--attempt N`. Locking is refused if the prompt files or the Avatar reference image changed after that clip was made, because no clip would show what is being locked; generate a new calibration clip instead. Once locked, production stops if either changes, until the setup is recalibrated and relocked.

## Timing

Estimate natural speech duration using configured WPM, pauses, lead-in and tail. Map it to a supported model duration.

Warn when a line fits poorly. Possible user decisions include rewriting, splitting, using a longer duration or deliberately planning a disposable tail for trimming.

Never silently add filler or rewrite dialogue to fit a duration.

## A-roll preflight and cost approval

Run:

```bash
ugc-forge preflight PROJECT_DIR
```

Preflight validates the project, estimates every spoken A-roll beat, shows clip count/generated seconds and calculates video cost where verified pricing is configured.

This is a hard gate. No production A-roll request may be submitted before explicit approval.

Never describe a local estimate as a provider invoice.

## Batch A-roll

Use batch when the calibrated setup is reliable and the user wants the complete A-roll generated hands-off.

After approval:

```bash
ugc-forge generate PROJECT_DIR --yes
```

The CLI handles concurrency and retries. Every submitted job is recorded straight away, so if a run is interrupted (or the agent's shell times out), rerunning the same command collects clips already paid for instead of paying again. A clip counts as done only while its dialogue, prompt, reference image, duration, resolution and model are unchanged; edit a line and only that clip is regenerated. Inserting or reordering beats renames existing clips rather than regenerating them.

To redo specific lines the user rejected:

```bash
ugc-forge generate PROJECT_DIR --redo BEAT_ID ... --yes
```

The command exits with an error if any clip failed or is still generating, and says to rerun it.

## Sequential A-roll

Use sequential when the user wants to review each spoken beat.

```bash
ugc-forge next PROJECT_DIR
ugc-forge generate-next PROJECT_DIR --yes --max-cost AMOUNT
ugc-forge accept PROJECT_DIR
```

The current beat is the first spoken A-roll beat, in storyboard order, without a finished clip. Generate it as many times as needed; every attempt is kept in `output/a-roll/attempts/`. `accept` takes the latest attempt, or `--attempt N` for an earlier one, and copies it to the same final file batch mode uses. To switch modes, change `generation.mode` in the project's `config.yaml` (`generate` refuses to run in `sequential` mode); lines already finished in either mode are never paid for again. Do not queue later beats.

## B-roll planning

Plan B-roll during storyboarding, not after A-roll generation.

B-roll should make sense for the Avatar and content style. Consider what this particular creator would plausibly film, how composed their footage would be and whether a different scene/wardrobe makes sense.

Do not force exact A-roll wardrobe continuity across B-roll that represents another time or location. Preserve character identity and useful recurring details where appropriate.

Some B-roll is supplied by the user (`broll`, `still`, `graphic`, `other`) and requires no Forge generation.

When writing a generated shot's `description`:

- Decide whether the shot happens in the A-roll setting or somewhere new. A demonstration usually needs a new scene: use `"inputs": []` to make it from the description alone (or a scene image the user supplies), rather than editing the A-roll frame.
- State the camera position and which way the Avatar faces relative to what they react to (for example: "camera behind him and slightly to one side; he faces the TV on the wall in front of him"). Without this, the model keeps the A-roll framing and turns the Avatar's head the wrong way.
- Describe the look the creator's channel would have (styled, tidy, a colour palette). Avoid phrases like "as a creator would film it", which can put cameras, tripods or ring lights in the shot.
- The image model adds real brand logos and readable text on its own, often misspelled. Unless a logo is the point of the shot, say "no logos or readable brand names", and check every image for stray text before approving it.

Generated B-roll (`avatar_broll`, `scene_broll`) has two steps. Always use these commands; do not write your own generation scripts or call the provider directly, because Forge's commands keep the version history, resume state and cost record.

### 1. Make each shot's image

```bash
ugc-forge broll-image PROJECT_DIR BEAT_ID --yes
```

This uses the beat's `description` and `inputs`. Every version is kept in `output/b-roll/references/history/` and recorded in `broll.json`. Several `broll-image` commands for different shots can run at the same time.

To refine an image, edit the current one rather than starting again:

```bash
ugc-forge broll-image PROJECT_DIR BEAT_ID --from BEAT_ID --prompt "Turn the TV on." --yes
```

To build a shot from another shot's image, pass that beat id in `--from` (or set it in `inputs`). To go back to an earlier version:

```bash
ugc-forge broll-use PROJECT_DIR BEAT_ID VERSION
```

Show the user each image and get approval before moving on. If the model returns no image, say so plainly, suggest one change (simpler wording, fewer inputs, or building from an existing shot) and ask before retrying. Do not retry repeatedly on your own.

### 2. Animate the approved images

```bash
ugc-forge broll PROJECT_DIR --plan
```

The plan lists every generated shot, its duration, motion prompt, whether it is done, and a warning if its image was made from an older version of another shot. Show the plan and cost, obtain approval, then:

```bash
ugc-forge broll PROJECT_DIR --yes
```

The command runs clips concurrently with retries, skips clips that are already done, and regenerates a clip whose image has changed since it was animated. If some clips fail, rerunning retries only those. `--only BEAT_ID ...` limits a run to specific shots. Shots marked `"animate": false` are listed as stills and never animated.

Do not attempt to composite the B-roll over A-roll. The output is a raw B-roll clip for the editor.

## Series and recurring creators

Series are independent of Avatars.

Before developing an episode in an existing Series, read `series.md` and relevant prior manifests. Use them for continuity without mechanically copying previous scripts, hooks or structures.

A recurring Avatar-led channel should still begin each episode with a substantive creator idea, explanation, argument or opinion. The persistent Avatar is the presenter, not a substitute for original creative input.

After completion, archive useful production context into the Series without turning it into a rigid template.

## Output boundary

A completed Forge project can contain:

```text
output/
├── calibration/
├── a-roll/
└── b-roll/
```

At completion, summarise which raw clips were produced, which storyboard overlays are supplied/external assets, failures/retries and calculated generation costs.

Do not claim the finished edited video has been produced.

## Cost safety

Every chargeable generation requires explicit approval at the appropriate gate:

- calibration: per calibration attempt;
- batch A-roll: total run approval;
- sequential A-roll: each generation/regeneration;
- Avatar images: each generation (`avatar` shows the estimated image cost);
- B-roll images: each image generation or edit;
- B-roll animation: run approval after showing `ugc-forge broll PROJECT_DIR --plan`.

The CLI's own `[y/N]` prompts cannot be answered through an agent's shell. Get each estimate for free first: `ugc-forge preflight` for A-roll, and `--plan` on `avatar`, `calibrate`, `broll-image` and `broll`. Show it, obtain approval for that amount in the conversation, then run the command with `--yes --max-cost AMOUNT`. The command refuses if its estimate is above the approved amount; if that happens, show the new amount and ask again.

Set the production resolution in the project's `config.yaml` (`video.resolution`) rather than per command, so clips made earlier still count as done. 720p is the recommended production setting: Google's 1080p and 4K are upscales, and CapCut's own upscale from 720p is visually equivalent. On Google, `--resolution 360p` costs a third of 720p and suits early calibration experiments (calibrate the final take at the production resolution). On kie.ai, 360p costs the same as 720p, so test at 720p.

Long runs print a line as each clip is submitted, retried or finished. Let the user see that output: run long commands in the background if the shell has a time limit, and never pipe them through `tail` or `head`, which hide progress until the end. If a run is interrupted or the shell times out, rerun the same command; jobs already paid for are collected, not paid for again.

On kie.ai a job can wait in kie.ai's queue for a long time; Forge waits up to 30 minutes per run (`kie.timeout`) and then leaves the job to be collected by a rerun. If kie.ai fails a job, it doesn't charge for it, and Forge submits a replacement automatically and says so (`[RETRYING]`). Report that to the user rather than claiming a rerun only collected the original job.

If the user wants to stop waiting for a job (for example to make that clip on the other provider instead), run:

```bash
ugc-forge abandon PROJECT_DIR BEAT_ID
```

It checks the job's state with the provider first (free) and refuses if the job has already finished, because then it is paid for and a rerun collects it. Otherwise Forge stops waiting and the next run submits a new job, on whichever provider is configured then. Tell the user an abandoned job can't be cancelled at the provider: on kie.ai the credits are taken when it starts and refunded only if it fails. Never edit state files by hand to do this. `--redo` refuses a clip whose job is still in progress, so it can't pay twice by accident.

Switching provider doesn't make finished A-roll lines stale just because the other provider offers different clip lengths: a finished clip still counts while its line, prompt, reference, resolution and model are unchanged and it is long enough for the line.

Pricing is a configured estimate. Local cost reports are not provider invoices.

## Safety and provenance

Use source material the user is entitled to use. Replace source identity rather than cloning it. Do not use the workflow for deceptive impersonation of real people. Preserve provider provenance/watermarking where applicable.

## v1 model support

Generation is intentionally model-specific in this prototype. Two services run the same Google models:

- `provider: kie` (default): kie.ai's `google/gemini-omni-flash-1-1` for video and `nano-banana-pro` for images. Clip lengths are 4, 6, 8 or 10 seconds.
- `provider: google`: the Gemini API's `gemini-omni-1.1-flash` for video and `gemini-3-pro-image` (or `gemini-3.1-flash-image` for B-roll via `broll-image --model`) for images. Clip lengths are 3 to 10 seconds.

The user picks the service in `ugc-forge setup`; `ugc-forge check` shows which is active. Model IDs are visible for transparency/versioning, not arbitrary selectors. Fail validation for unsupported IDs before chargeable generation.

Single image and video calls were verified live on 2026-09-28. Provider capabilities and pricing change; re-verify before describing the project as production-ready.

## Conversation policy

Keep two kinds of output apart: **workflow output** (the things being produced and decided) and **conversation** (discussion, explanation, feedback).

### Workflow output lives in files

Scripts, beats, prompts, Avatar specs and plans are written to the project files first (`beats.json`, `prompts/`, `avatar/spec.md`, `creative-brief.md`). The files are the source of truth. Chat shows a readable view of what was saved, never a second version that could drift from it.

### Checkpoint messages

When a stage produces something for review, or a decision is needed, use this shape and nothing else in that message:

```text
**<Stage name>** · <what changed, one line>
Saved: <file(s)>

<the review view: a table of beats, the image, the plan output>

**Decision:** <one question>
```

Beats are shown as a table (id, spoken line, what is on screen, duration). Cost gates show the CLI's plan output as-is, then the total.

Ordinary conversation (answering a question, discussing an idea, explaining a result) is plain prose without that shape. Do not bury a decision inside conversational text, and do not mix two decisions into one question.

### Asking questions

- If the agent provides a structured question tool that is available at that moment (for example `AskUserQuestion` in Claude Code, or `request_user_input` in Codex when it is listed for the turn), use it for discrete choices: which option, which version, which beat to calibrate.
- Otherwise ask one direct question and list the options as a short numbered list.
- Cost approvals are always an explicit, separate question that names the amount and what it buys. Follow the agent's own rules on whether its question tool may be used for approvals; if in doubt, ask in plain text. Only an unambiguous yes counts as approval.

Keep workflow state underneath the conversation. Do not expose state-machine jargon unless the user asks.
