# Chat Animation

[![License: MIT](https://img.shields.io/badge/License-MIT-22c55e.svg)](LICENSE)
[![Python 3.9+](https://img.shields.io/badge/Python-3.9%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![FFmpeg](https://img.shields.io/badge/FFmpeg-required-007808?logo=ffmpeg&logoColor=white)](https://ffmpeg.org/)
[![Agent Skills](https://img.shields.io/badge/Agent_Skills-compatible-2563EB)](https://agentskills.io/specification)
[![Self tests](https://img.shields.io/badge/self_tests-30_passed-16A34A)](skills/chat-animation/scripts/self_test.py)
[![Workflow](https://img.shields.io/badge/workflow-reviewable%20%7C%20resumable-8b5cf6)](#why-chat-animation)

[![Codex](https://img.shields.io/badge/Codex-E2E_verified-111827?logo=openai&logoColor=white)](https://developers.openai.com/codex/skills)
[![Claude Code](https://img.shields.io/badge/Claude_Code-compatible-D97757?logo=anthropic&logoColor=white)](https://code.claude.com/docs/en/skills)
[![WorkBuddy](https://img.shields.io/badge/WorkBuddy-compatible-0052D9)](https://www.workbuddy.ai/docs/workbuddy/From-Beginner-to-Expert-Guide/Practice-Cases/Create-Skills)
[![Hermes Agent](https://img.shields.io/badge/Hermes_Agent-compatible-7C3AED)](https://github.com/NousResearch/hermes-agent/blob/main/website/docs/user-guide/features/skills.md)
[![Cursor](https://img.shields.io/badge/Cursor-compatible-000000)](https://cursor.com/)
[![Gemini CLI](https://img.shields.io/badge/Gemini_CLI-compatible-4285F4?logo=googlegemini&logoColor=white)](https://geminicli.com/)
[![OpenCode](https://img.shields.io/badge/OpenCode-compatible-0F766E)](https://opencode.ai/)

**English** · [简体中文](README.md)

Turn one idea, article, question, or reference into a complete narrated explainer animation—not merely a set of prompts.

![Paradox of Thrift contact sheet](assets/paradox-of-thrift-contact-sheet.jpg)

▶️ [Watch the 12-second MP4 demo](assets/paradox-of-thrift-demo.mp4)

## Install in 30 seconds

The recommended route uses the open `skills` CLI. It discovers this repository's standard `skills/<name>/SKILL.md` layout and lets you choose the target agent:

```bash
npx skills add xue-xiaobao/chat-animation --skill chat-animation -g
```

Install only for Codex:

```bash
npx skills add xue-xiaobao/chat-animation --skill chat-animation -g -a codex -y
```

Restart the agent or open a new session after installation, then describe the animation you want. If Node.js is unavailable, use the manual copy instructions below.

## Supported agents

Chat Animation follows the standard `SKILL.md` directory layout. Its core workflow only requires an agent that can read files, run Python, and use a terminal.

| Agent | Status | Recommended installation |
| --- | --- | --- |
| Codex App / CLI | **End-to-end verified** | `skills` CLI: `-a codex` |
| Claude Code | Format compatible | `skills` CLI: `-a claude-code` |
| Tencent WorkBuddy | Format compatible | Import the Skill or copy it to `~/.workbuddy/skills/chat-animation/` |
| Hermes Agent | Format compatible | `skills` CLI: `-a hermes-agent`, or copy it to `~/.hermes/skills/` |
| Cursor | Format compatible | `skills` CLI: `-a cursor` |
| Gemini CLI | Format compatible | `skills` CLI: `-a gemini-cli` |
| OpenCode | Format compatible | `skills` CLI: `-a opencode` |

“Format compatible” means the directory layout and runtime requirements match that agent's Skill mechanism. This release's real end-to-end production regression was completed on Codex. Tool names, permissions, and credential setup can vary across agents.

## What it does

Chat Animation gives a compatible AI agent a self-contained, five-stage production workflow:

```text
Direction → Visual keyframes → Motion & transitions → Voice → Final composition
```

Give it a request such as:

> Use Chat Animation to create a fun, 60-second explainer about the paradox of thrift for adults with no economics background. Let me review each stage.

The workflow plans the argument, writes narration and storyboards, generates images and motion, creates speech, aligns the picture to the voice, renders captions, and exports a verified MP4.

## Why Chat Animation?

- **Idea to MP4:** produces a complete video instead of stopping at scripts or prompts.
- **Review before spending:** creates one visual, motion, and voice sample before costly batches.
- **Audio-master timing:** keeps narration natural and retimes silent video to match it.
- **Controllable motion:** Agnes receives a first frame, an end frame, and an English motion prompt.
- **Three edit modes:** hard cuts, dedicated transitions, or fused transitions; dedicated one-second transitions are the default.
- **Local, resumable projects:** saves manifests, provider task IDs, hashes, reviews, and downloaded outputs.
- **Targeted revisions:** redo one scene, transition, voice, or caption layer without rebuilding everything.
- **Built-in Vox style:** paper collage, stickers, halftones, readable metaphors, and restrained breathing motion.
- **Preset or cloned voice:** use a MiMo preset voice or an authorized MP3/WAV voice reference.
- **Portable captions:** downloads and verifies Smiley Sans once, then falls back to built-in macOS or Windows CJK fonts.

## Requirements

- Codex or another agent capable of loading and following `SKILL.md`
- Python 3.9+
- FFmpeg and FFprobe
- An Agnes API key for image and video generation
- A Xiaomi MiMo API key for narration

Agnes and MiMo are external services and may charge for usage. Never commit API keys, generated voice references, or private project outputs.

## Manual install and configuration

Without the `skills` CLI, clone the repository and copy `skills/chat-animation` into your agent's user Skill directory.

macOS/Linux example:

```bash
mkdir -p ~/.codex/skills
cp -R skills/chat-animation ~/.codex/skills/chat-animation
```

Windows PowerShell example:

```powershell
New-Item -ItemType Directory -Force "$env:USERPROFILE\.codex\skills" | Out-Null
Copy-Item -Recurse -Force "skills\chat-animation" "$env:USERPROFILE\.codex\skills\chat-animation"
```

Configure credentials in your environment or operating-system secret store:

```bash
export AGNES_API_KEY="<your-key>"
export MIMO_API_KEY="<your-key>"
```

Run the preflight before the first project:

```bash
python3 skills/chat-animation/scripts/project.py preflight
```

## Use

In Codex, ask naturally:

> Use `$chat-animation` to create a Vox-style explainer about the disposition effect. Use human review gates.

The default reviewable flow is:

1. Review the thesis, narration, storyboard, visual metaphors, and transition plan.
2. Review one generated visual sample before the remaining images.
3. Review one motion sample before the remaining video jobs.
4. Choose a preset or authorized cloned voice and review one audio sample.
5. Review the final synchronized, captioned MP4.

To remove all waiting gates, explicitly say:

> Complete the animation fully automatically and skip all human approvals.

Self-checks, deterministic validation, artifacts, and failure stops still run in full-auto mode.

## Output

Each project keeps editable and auditable layers:

```text
project_01/
├── request.json
├── script.json
├── state/
├── visual/
├── motion/
├── audio/
├── composition/
│   └── final.mp4
└── reviews/
```

The default final format is 1280×720, 24 fps, H.264 video with AAC narration. See the complete workflow in [`SKILL.md`](skills/chat-animation/SKILL.md).

## Using the scripts without Codex

The Agnes, MiMo, validation, and FFmpeg adapters are ordinary Python scripts. They do not technically require Codex. However, without a Skill-aware agent you must prepare the project contracts, narration, prompts, approvals, and QA manually. This repository is therefore an agent workflow first, not yet a one-command consumer application.

## License

The repository is available under the [MIT License](LICENSE). Smiley Sans is not bundled; it is downloaded from its official release at initialization and remains under the SIL Open Font License 1.1. External models and services retain their own terms.
