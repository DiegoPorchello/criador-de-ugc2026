# Installing UGC Forge

These steps are for an AI agent (Claude Code, Codex or similar) that a user has asked to install or update UGC Forge. Run each command yourself and tell the user briefly what you are doing. Running the steps again updates an existing installation.

UGC Forge needs an agent that can run commands on the user's computer: Claude Code (in a terminal, an IDE, or the Code tab of Claude Desktop) or Codex. It cannot work in a chat-only app such as the claude.ai website; if that is where you are running, tell the user and stop.

## 1. Make sure uv is installed

Run `uv --version`. If uv is not found, install it:

- macOS or Linux: `curl -LsSf https://astral.sh/uv/install.sh | sh`
- Windows (PowerShell): `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"`

uv installs into `~/.local/bin` (Windows: `%USERPROFILE%\.local\bin`). If `uv` is still not found in your current shell, call it by that full path for the rest of these steps.

## 2. Install or update the ugc-forge command

```bash
uv tool install --force --refresh https://github.com/indygill/ugc-forge/archive/refs/heads/main.zip
uv tool update-shell
```

If the user pointed you to a local folder or another copy of UGC Forge, install from that instead of the GitHub URL, e.g. `uv tool install --force --refresh /path/to/ugc-forge`.

`--refresh` is required: without it, uv reuses a cached copy and an update silently installs the old version. uv downloads a suitable Python automatically if needed.

If `ugc-forge` is not found in your current shell, run `uv tool dir --bin` and use the full path to `ugc-forge` inside that folder. Confirm the installation with `ugc-forge --version`.

## 3. Install the skill

If the user installed UGC Forge as a Claude Code plugin, skip this step: the plugin already provides the skill. Otherwise run:

```bash
ugc-forge install-skill
```

It installs the skill that matches this version of the command, for Claude Code (`~/.claude/skills/ugc-forge/`) and Codex (`~/.agents/skills/ugc-forge/`). The skill loads in the next session.

## 4. The user chooses a service and adds their API key

Never ask the user to paste the key into the chat, and never read, print or handle the key yourself.

First ask which service they want to use, as one question:

1. **kie.ai** (recommended): quick sign-up, prepaid credits, lower prices. They sign up and buy credits at https://kie.ai, then find their key at https://kie.ai/api-key.
2. **Google**: they create a key at https://aistudio.google.com/apikey; its Google Cloud project needs billing enabled.

Then ask them to copy their key and enter this themselves. The key is read from the clipboard, never shown, and the clipboard is cleared afterwards:

- In Claude Code, they type in the prompt: `! ugc-forge setup --provider kie --from-clipboard` (or `--provider google`).
- In a terminal window, they can instead run `ugc-forge setup` and paste the key when asked; it is not shown.

If `setup` says the clipboard doesn't hold a key, they copied something else; ask them to copy the key again and repeat the command.

Then run `ugc-forge check --online` and tell the user the result. The check is free.

## 5. Finish

Tell the user UGC Forge is installed, that a new session is needed for the skill to load, and that they can start with something like: "Let's make a video with UGC Forge."
