# UGC Forge workflow guide

[Back to the README](../README.md)

UGC Forge is an open-source Agent Skill and Python CLI for producing the raw AI-presented video clips needed to edit UGC ads, social videos and recurring avatar-led content.

It grew out of a manual AI UGC workflow: start with a frame from real captured footage, replace the person with a new fictional character, establish how that character should look and perform, generate the spoken A-roll line by line, and then create B-roll to layer over that A-roll in the final edit.

The method is useful, but doing it manually means repeatedly building prompts, choosing durations, submitting generations, reviewing results, downloading clips and trying to keep the character and performance consistent.

UGC Forge keeps the creative decisions with you and your agent while handling the repetitive production work underneath them.

You can begin with a reference frame and an idea. The skill helps develop the script and storyboard, create or reuse a fictional Avatar, establish a Look, calibrate the performance, estimate generation time and cost, generate the complete A-roll and create any AI Avatar B-roll required by the storyboard.

UGC Forge deliberately stops there. It is **not a video editor**. Its output is an organised set of source clips and production state that you can take into CapCut, Premiere Pro, DaVinci Resolve, Remotion, FFmpeg or another editing workflow.

The other deliberate choice is prompting. UGC Forge does not try to turn every instruction into a huge “AI prompt”. The workflow starts with a strong reference and short, plain instructions. Constraints are added when an actual generation shows that they are needed.

---

## See it work: a UGC ad

Imagine a fictional skincare brand launching a moisturiser.

The idea is simple: a woman in her early 30s explains that she spent years making her skincare routine increasingly complicated, then stripped it back to a few products and started using the moisturiser consistently.

You have a real social-video frame that you are entitled to use. You like the framing, lighting and ordinary bathroom environment, but you want a completely new fictional presenter.

You give the frame and the idea to your agent.

### 1. Develop the script and storyboard

You work on the hook, argument and script conversationally. The finished storyboard might contain:

| Dialogue | Final visual treatment |
| --- | --- |
| “I spent years thinking my skincare routine needed more products.” | A-roll |
| “At one point, this was my bathroom shelf.” | A-roll with B-roll over it |
| “Then I stripped everything back.” | A-roll |
| “Cleanser. This. SPF. That's basically it.” | A-roll with Avatar B-roll using the product |
| “I've been doing that for six weeks now.” | A-roll |
| “And this is the first time my skin has actually felt consistent.” | A-roll with close-up B-roll |
| CTA | A-roll |

UGC Forge's default v1 production strategy is **full A-roll**. Every spoken line is generated as the presenter, including lines that will later be hidden by B-roll.

That costs slightly more than generating only the visible A-roll, but it keeps the presenter's generated audio continuous and avoids introducing a separate voice-cloning workflow. During editing, the B-roll simply sits over the A-roll while its audio continues underneath.

### 2. Create the Avatar

You describe the fictional presenter in normal language. The agent turns those decisions into the Avatar specification and a short image-generation instruction.

The source frame supplies much of the useful visual information already: camera position, perspective, environment and lighting. The prompt does not need to describe every tile, shadow or skin detail.

Each candidate is generated from the original source rather than repeatedly editing an already edited image. When you approve the character, you can name and save the Avatar for future work.

### 3. Establish the Look

An **Avatar** is the reusable character. A **Look** is that character in a particular production setup: scene, framing, wardrobe, accessories and reference image.

For this ad, the approved bathroom setup becomes the primary Look.

### 4. Calibrate the A-roll

Before generating the complete script, choose one representative line and generate it.

If the presenter moves too much, tell the agent:

> Make her less animated.

If the delivery is too fast:

> Keep that performance, but slow the delivery slightly.

The agent changes only what is necessary and generates the same beat again. Once the performance is right, the fixed A-roll prompt is locked.

Calibration is empirical: start simple, observe the result, then add a constraint when there is a real reason for it.

### 5. Generate the complete A-roll

UGC Forge estimates how long each spoken beat needs, maps it to a duration supported by the configured video model and shows the expected production cost.

After approval, the A-roll can be generated as a batch or reviewed sequentially one clip at a time.

Even the lines marked for B-roll are generated. They provide the underlying voice and performance track for the finished edit.

### 6. Create the B-roll

Some B-roll may already exist: a product shot, screen recording, customer footage or other supplied asset. Forge records that in the storyboard but does not need to regenerate it.

Other B-roll can use the established Avatar. For example:

> Same character in the bathroom, applying the moisturiser at the mirror. Different casual clothing.

That is intentionally close to the level of prompt detail Forge prefers. The Avatar reference carries the character identity; the prompt describes the meaningful change.

Forge can create a new reference for that B-roll scene and animate it as a source clip. Clothing can change where the B-roll represents another moment, while useful identity details can remain consistent.

### 7. Edit elsewhere

The production package is organised roughly as:

```text
output/
├── a-roll/
│   ├── 01_hook.mp4
│   ├── 02_bathroom-shelf.mp4
│   └── ...
└── b-roll/
    ├── 01_apply-product_reference.png
    ├── 01_apply-product.mp4
    └── ...
```

You now have the raw generated clips. The final assembly, B-roll placement, captions, music, graphics, transitions and colour work belong in your editor.

---

## A second use case: a recurring Avatar-led creator

UGC Forge isn't limited to advertisements.

Consider a fictional presenter called Marco who fronts an interiors and renovation channel. The human creator behind the channel supplies the ideas, opinions and arguments; Marco is the recurring on-screen presenter.

One episode starts with a strong opinion:

> **Why does everyone put their TV this high?**

The creator's argument is that televisions are often mounted for the appearance of the wall rather than the seated viewing position of the people actually using the room.

The storyboard could become:

| Dialogue / idea | Final visual treatment |
| --- | --- |
| “Why does everyone put their TV up here?” | A-roll |
| “You're sitting down here, and your television is halfway to the ceiling.” | A-roll + B-roll |
| “So every evening you're basically doing this.” | A-roll; Marco demonstrates looking upwards |
| Explain seated viewing position | A-roll + explanatory B-roll/graphic |
| Show a more comfortable placement | A-roll + B-roll |
| “Design the room for the people living in it, not the estate-agent photos.” | A-roll |

This time the production doesn't start by inventing another presenter.

Marco already exists. His voice and performance characteristics are established, and the channel may already have reusable Looks such as a living room, desk or workshop.

The workflow becomes:

```text
New idea / opinion
        ↓
Develop script
        ↓
Storyboard A-roll + overlays
        ↓
Reuse Marco
        ↓
Choose an existing Look
        ↓
Generate complete A-roll
        ↓
Create required AI B-roll
        ↓
Organised raw source clips
        ↓
Edit elsewhere
```

This is why UGC Forge keeps **Avatars**, **Looks**, **Series** and individual **Videos** separate. A presenter can persist across a channel while each episode still begins with something new that the creator actually wants to say.

UGC Forge is not intended to turn scraped information into large volumes of near-identical videos. The agent can help a creator develop an idea, but the point of the recurring Avatar workflow is to provide a production system for original material, not to manufacture the creator's point of view.

---

## The workflow

```text
Idea
  ↓
Script and storyboard
  ↓
Create or reuse Avatar
  ↓
Create or reuse primary Look
  ↓
Generate calibration beat
  ↓
Review and refine only what needs changing
  ↺
Lock A-roll prompt
  ↓
Preflight full A-roll
  ↓
Approve generation cost
  ↓
Batch or sequential A-roll generation
  ↓
Create required Avatar B-roll references/clips
  ↓
Organised raw source clips
  ↓
Edit elsewhere
```

The project is file-based, so the workflow does not depend on a single chat session remembering every decision.

---

## Prompting philosophy

**Prefer the reference over the prompt.**

UGC Forge uses short, direct prompts. Describe what the model needs to know and allow the reference image to carry visual information that is already established.

Do not automatically expand a simple request into a large “AI prompt”. In particular, Forge should not add generic phrases such as:

- hyper-realistic;
- ultra-detailed;
- visible skin pores;
- natural skin imperfections;
- cinematic realism;
- photorealistic 8K;
- exhaustive descriptions of incidental background details.

Those phrases should not appear merely because the content is AI-generated.

For a B-roll reference, this can be enough:

> Marco sits outside a café drinking coffee. He is wearing a dark turtleneck and looking into the distance, relaxed.

For A-roll:

> Static phone camera. Marco speaks directly to camera with calm, measured delivery and subtle natural movement.

Then provide the dialogue and the small number of fixed rules that calibration has shown are actually necessary.

If a generation introduces unwanted camera movement, add a camera constraint. If the presenter becomes too animated, constrain the movement. If the reference repeatedly fails in a fundamental way, reconsider the reference instead of endlessly growing the prompt.

The goal is not the most detailed prompt. It is the minimum useful direction combined with a strong reference.

---

## Full A-roll first

In v1, every spoken storyboard beat is A-roll by default.

B-roll is modelled as an **overlay on a spoken beat**, not as a replacement for generating that beat.

Conceptually:

```json
{
  "id": "bathroom-shelf",
  "dialogue": "At one point, this was my bathroom shelf.",
  "a_roll": true,
  "overlay": {
    "type": "broll",
    "description": "Close-up of the crowded bathroom shelf",
    "asset": "bathroom-shelf.mp4"
  }
}
```

Avatar-generated B-roll can instead be described as:

```json
{
  "id": "apply-product",
  "dialogue": "Cleanser. This. SPF. That's basically it.",
  "a_roll": true,
  "overlay": {
    "type": "avatar_broll",
    "description": "Same character applying the moisturiser at the bathroom mirror in different casual clothing",
    "duration": 4
  }
}
```

The first example generates A-roll but expects the supplied B-roll asset to be added later in editing. The second generates the A-roll and can also create an Avatar B-roll source clip.

Selective A-roll and external voice cloning may be useful future cost optimisations, but they are deliberately outside the v1 workflow.

---

## Reference selection

The preferred starting point is a still from genuine captured footage that you are entitled to use.

Look at the framing, body position, camera angle, lighting, background depth, pose and whether captions or overlays contaminate the frame. A useful real reference already contains many incidental decisions that don't need to be reconstructed in text.

The source is used for composition and environment, **not to preserve the source person's identity**. UGC Forge is designed to replace that person with a new fictional character.

---

## Avatar vs Look

**Avatar** answers: *Who is this person?*

It can include appearance, voice, accent, pace, energy and general performance characteristics.

**Look** answers: *How does this person appear in this production setup?*

A Look can include the reference image, scene, framing, wardrobe and accessories.

For example:

```text
~/.ugc-forge/
└── avatars/
    └── marco/
        ├── avatar.json
        ├── reference.png
        ├── spec.md
        └── looks/
            ├── living-room/
            ├── desk/
            └── workshop/
```

The same Avatar can therefore front many videos without every production being visually identical.

B-roll does not need to preserve the exact wardrobe of the primary A-roll Look when it represents another moment or location. It should still plausibly belong to the same character and production.

---

## Calibration and prompt locking

A still reference can look convincing while producing poor animation. Calibration tests the actual performance before the full production run.

Generate one representative A-roll beat and review voice, cadence, energy, expression, eye contact, movement, framing and camera behaviour.

Make a small correction where necessary, then generate the same beat again.

Once approved:

```bash
ugc-forge lock-prompt my-video
```

UGC Forge stores a hash of the calibrated scene and fixed rules. If those files change afterwards, production refuses to continue until the new prompt has been recalibrated or explicitly relocked.

Calibration itself is a chargeable video generation and therefore has its own approval step.

---

## Dialogue timing

UGC Forge estimates natural speech duration from word count, configured speaking pace and pauses, then maps that estimate to a duration supported by the configured video model.

If a line fits poorly, preflight can flag it before money is spent. The user can shorten it, split it, select a longer duration or deliberately plan a disposable tail for trimming.

Forge never silently adds filler or rewrites dialogue merely to satisfy a duration.

---

## Batch and sequential A-roll

**Batch** is useful once the calibrated setup is reliable. Forge preflights the complete A-roll, shows the total estimated video cost, obtains approval and then submits clips with controlled concurrency and retry/resume state. Each job is recorded as soon as it is submitted, so an interrupted run can be rerun to collect clips already paid for. A clip is reused only while its dialogue, prompt, reference image, duration, resolution and model are unchanged, and `ugc-forge generate my-video --redo BEAT_ID` regenerates a specific line.

**Sequential** keeps a review point between beats. Only one A-roll beat is active. Generate it, review it, regenerate if necessary, accept it, then move to the next.

Through an agent that can remain conversational:

> His expression is too surprised. Keep it understated and try that beat again.

> That's right. Next one.

---

## B-roll

B-roll is planned as part of the storyboard rather than treated as an afterthought.

It can be:

- existing footage supplied by the creator;
- product footage;
- screen recordings;
- stills or graphics;
- generated footage of the established Avatar in another situation.

Avatar B-roll should make sense for the character. A carefully composed creator may plausibly make more deliberate B-roll; another character may use simpler, rougher phone footage. The agent should consider this when planning scenes rather than applying one generic visual style to every Avatar.

Forge generates two kinds of B-roll: `avatar_broll`, featuring the Avatar, and `scene_broll`, such as a room or product shot without the Avatar. Both take two steps.

First, make each shot's image from a short instruction and one or more input images: the Avatar reference, the original frame, another shot's image, or a project file. Refine it by editing the current image, and go back to any earlier version:

```bash
ugc-forge broll-image my-video sofa
ugc-forge broll-image my-video sofa --from sofa --prompt "Turn the TV on."
ugc-forge broll-use my-video sofa 1
```

Then animate the approved images:

```bash
ugc-forge broll my-video --plan
ugc-forge broll my-video
```

The plan shows each shot's duration, motion prompt and status, and warns when a shot was built from an older version of another shot. A shot you only want as a still image in the edit gets `"animate": false` in its overlay: Forge makes the image but never animates it. To give up on a job that's taking too long, `ugc-forge abandon my-video BEAT_ID` stops Forge waiting for it (after checking it hasn't already finished), and the next run submits a new one. Generation runs concurrently with retries. Rerunning skips finished clips, collects clips from an interrupted run without paying again, and redoes any clip whose image, motion prompt, duration or resolution has changed. `--redo BEAT_ID` regenerates a specific clip. Each command asks for approval before chargeable generation. Video cost is estimated from configured pricing; image generation is not priced.

---

## Agent + CLI architecture

The **Agent Skill** handles work that benefits from conversation and judgement: concept development, scripting, storyboard decisions, Avatar design, reference assessment, prompt refinement and interpreting creative feedback.

The **Python CLI** handles deterministic work: validation, timing, cost estimation, approval gates, generation, retries, resume state, prompt locking and reusable asset storage.

There is deliberately no conversational LLM inside the Python CLI. Your existing agent is the conversational intelligence; Forge is the workflow and execution layer underneath it.

---

## Project structure

```text
my-video/
├── config.yaml
├── project.json
├── workflow.json
├── creative-brief.md
├── source/
│   ├── frame.jpg
│   └── reference-notes.md
├── avatar/
│   ├── spec.md
│   └── reference.png
├── prompts/
│   ├── scene.md
│   └── fixed-rules.md
├── beats.json
├── calibration.json
├── sequential.json
├── job.json
├── broll.json
├── costs.json
└── output/
    ├── calibration/
    ├── a-roll/
    └── b-roll/
```

Files appear as they become relevant. They preserve decisions between sessions and make the production state inspectable rather than hiding it inside a chat transcript.

---

## Series

Series are independent of Avatars. A saved Avatar can appear in multiple series or one-off videos.

```text
~/.ugc-forge/
├── avatars/
│   └── marco/
└── series/
    └── renovation-opinions/
        ├── series.json
        ├── series.md
        └── videos/
            ├── 001-tv-too-high/
            └── 002-curtain-height/
```

`series.md` provides compact creative continuity: established format, previous subjects, useful generation observations and things the creator intentionally wants to avoid repeating.

It is context for the next idea, not a template for mass-producing near-identical episodes.

---

## Installation

> UGC Forge is currently an early open-source prototype. Read [Current status and limitations](#current-status-and-limitations) before using paid generation APIs.

Follow the [README setup](../README.md#get-started): install uv, run `uv tool install .` from this repository, then `ugc-forge setup` to choose kie.ai or Google and save its API key privately and `ugc-forge check --online` to confirm it.

For development, use an editable install with the test dependencies and run the tests:

```bash
uv venv
uv pip install -e ".[dev]"
.venv/bin/python -m pytest
```

The repository includes `SKILL.md` for compatible agent environments. Installation varies by host agent and will be documented against verified public integrations before v1.

### API keys

Forge reads the key from the first of these that exists: the file named by the `UGC_FORGE_CONFIG` environment variable, `config.yaml` in a source checkout's root, then `~/.ugc-forge/config.yaml`. `ugc-forge setup` updates that file, or creates `~/.ugc-forge/config.yaml`, readable only by you. `ugc-forge check` shows which file is in use. Video projects inherit the key automatically. A project's own `config.yaml` can override it, and environment variables named in `api_key_env` remain a fallback.

---

## Quick start

```bash
ugc-forge init my-video
ugc-forge set-frame my-video ~/Desktop/frame.jpg
```

Then begin with your agent:

> I want to make a short video explaining why people mount their TVs too high. Here's the reference frame. I want to use Marco as the presenter.

The agent should work through the creative stages conversationally and maintain the project files. You should not need to hand-edit JSON simply to change a line of dialogue.

Useful direct CLI commands include:

```bash
ugc-forge storyboard my-video
ugc-forge avatar my-video --plan      # cost only; nothing generated
ugc-forge avatar my-video
ugc-forge calibrate my-video --beat hook
ugc-forge lock-prompt my-video
ugc-forge preflight my-video
ugc-forge generate my-video
ugc-forge broll my-video
ugc-forge status my-video
```

Reusable assets:

```bash
ugc-forge avatars
ugc-forge save-avatar my-video Marco
ugc-forge use-avatar my-video marco
ugc-forge looks marco
ugc-forge save-look my-video "Living Room"
ugc-forge use-look my-video marco living-room
```

Sequential A-roll:

```bash
ugc-forge next my-video
ugc-forge generate-next my-video
ugc-forge accept my-video
```

---

## Configuration

UGC Forge uses YAML for deterministic settings such as generation mode, concurrency, retries, timing and provider configuration.

```yaml
generation_models:
  image:
    model: gemini-3-pro-image
    api_key_env: UGC_FORGE_IMAGE_API_KEY

  video:
    model: gemini-omni-1.1-flash
    api_key_env: UGC_FORGE_VIDEO_API_KEY

  broll_image:
    model: gemini-3-pro-image   # or gemini-3.1-flash-image: half the price, less exact

generation:
  mode: batch
  concurrency: 3
  max_retries: 3

video:
  resolution: 720p
  aspect_ratio: "9:16"
  timeout: 600

timing:
  words_per_minute: 135
  supported_durations: [3, 4, 5, 6, 7, 8, 9, 10]

broll:
  default_duration: 4
```

The model IDs are part of the implementation contract, not arbitrary selectors. Different generation models have different request formats, capabilities, duration rules and pricing.

**Choosing a resolution.** 720p is the recommended production setting. Google renders 1080p and 4K by upscaling, charging 1.5× and 3×; in a test, a 720p version upscaled back to 1080p was visually indistinguishable from Google's 1080p (SSIM 0.993). Upscale in your editor instead. 360p costs a third of 720p and suits early calibration experiments; calibrate the final take at the production resolution.

---

## Cost safety

Chargeable video generation requires explicit approval.

Batch A-roll shows the complete estimated run before submission. Sequential generation is approved one generation at a time. Calibration also shows its duration and estimated video cost before submission. Generated Avatar B-roll has a separate approval gate.

The default pricing snapshot (2026-09-28) estimates video output with audio at $17.50 per million output tokens: 1931 tokens/second for 360p, 5792 for 720p, 8688 for 1080p, and 17376 for 4K. This gives $0.0337925, $0.10136, $0.15204, and $0.30408 per second respectively. Input tokens and text-output charges are excluded. Sources: [Gemini API pricing](https://ai.google.dev/gemini-api/docs/pricing) and [Google Cloud resolution token rates](https://cloud.google.com/gemini-enterprise-agent-platform/generative-ai/pricing). Existing project configs retain their explicit pricing overrides.

`costs.json` and CLI estimates are calculations based on the configured pricing snapshot. They are **not provider invoices**.

`costs.json` has an `a_roll` and a `b_roll` section. Each records the estimated video cost and, where the API reported them, the video tokens actually generated and their cost. Image generation is counted but not priced.

---

## Supported models

The current implementation is intentionally model-specific. Two services run the same Google models, chosen with `provider` (set by `ugc-forge setup`):

| | kie.ai (`provider: kie`, default) | Google (`provider: google`) |
| --- | --- | --- |
| Video | `google/gemini-omni-flash-1-1` | `gemini-omni-1.1-flash` |
| Images | `nano-banana-pro` | `gemini-3-pro-image`, or `gemini-3.1-flash-image` for B-roll edits |
| Clip lengths | 4, 6, 8, 10 s | 3–10 s |
| Billing | prepaid credits, charged per clip | Google Cloud billing, charged per second of output |

An interrupted job is always collected from the service that accepted it, even after switching.

These identifiers reflect the current prototype implementation. The exact current Google model names, API behaviour, supported capabilities and pricing must be verified against official production documentation before Forge is described as production-ready.

Changing a model name in YAML does not make another model compatible. Unsupported IDs fail validation.

---

## Current status and limitations

UGC Forge is pre-v1.

The workflow, project state, Avatar/Look library, full A-roll storyboard model, calibration/prompt locking, timing, cost gates, batch/sequential generation and initial Avatar B-roll workflow are implemented, and single image and A-roll video calls were verified live on 2026-09-28. B-roll and sequential generation have not yet been run end to end.

Important limitations:

- Only single image and A-roll video calls have been verified live; B-roll and sequential runs have not.
- Provider pricing changes quickly; configured costs are estimates.
- Avatar B-roll currently uses the same pinned image/video provider path and a deliberately simple prompt strategy.
- Reference sourcing is not automated.
- Forge does not download social-media references for you.
- Forge does not perform final editing or B-roll compositing.
- Non-Avatar B-roll is tracked as an asset for the later edit rather than generated automatically.
- Final captions, music, transitions, graphics, sound design and colour work remain outside Forge.
- Creative judgement still matters. A technically valid reference or generation can still be a poor creative choice.

---

## Origin

UGC Forge was inspired by a YouTube tutorial demonstrating a manual workflow for creating AI UGC from real social-video reference frames, followed by a second video showing how the resulting A-roll can be developed into a fuller piece of content with B-roll.

Part one:
https://www.youtube.com/watch?v=kvf2lRSGixg&t=1681s

Part two:
https://www.youtube.com/watch?v=6rW-sH74A64

The useful idea wasn't that every step needed automating. The reference choice, concept, character, script and judgement of whether a performance works still benefit from a person making decisions.

The repetitive parts around those decisions — maintaining state, constructing the approved prompt, timing dialogue, checking cost, submitting generations, retrying failures and organising clips — are what UGC Forge is intended to remove.

The tutorials are worth watching to understand the manual workflow that prompted the project. UGC Forge does not claim that those videos invented AI UGC, reference-driven generation or the broader techniques involved.

---

## Contributing

Useful contributions include provider verification, tests, capability validation, timing improvements, pricing adapters, retry/resume behaviour, agent compatibility and additional explicitly supported generation providers.

New providers should implement their real capabilities rather than being added as model-name aliases to an incompatible API.

---

## Licence

UGC Forge is released under the Apache License 2.0. See [LICENSE](../LICENSE) for the full text.
