# Chat Animation

[![License: MIT](https://img.shields.io/badge/License-MIT-22c55e.svg)](LICENSE)
[![Python 3.9+](https://img.shields.io/badge/Python-3.9%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![FFmpeg](https://img.shields.io/badge/FFmpeg-required-007808?logo=ffmpeg&logoColor=white)](https://ffmpeg.org/)
[![Agent Skills](https://img.shields.io/badge/Agent_Skills-compatible-2563EB)](https://agentskills.io/specification)
[![Self tests](https://img.shields.io/badge/self_tests-30_passed-16A34A)](skills/chat-animation/scripts/self_test.py)
[![Workflow](https://img.shields.io/badge/workflow-reviewable%20%7C%20resumable-8b5cf6)](#为什么选择-chat-animation)

[![Codex](https://img.shields.io/badge/Codex-E2E_verified-111827?logo=openai&logoColor=white)](https://developers.openai.com/codex/skills)
[![Claude Code](https://img.shields.io/badge/Claude_Code-compatible-D97757?logo=anthropic&logoColor=white)](https://code.claude.com/docs/en/skills)
[![WorkBuddy](https://img.shields.io/badge/WorkBuddy-compatible-0052D9)](https://www.workbuddy.ai/docs/zh/workbuddy/From-Beginner-to-Expert-Guide/Practice-Cases/Create-Skills)
[![Hermes Agent](https://img.shields.io/badge/Hermes_Agent-compatible-7C3AED)](https://github.com/NousResearch/hermes-agent/blob/main/website/docs/user-guide/features/skills.md)
[![Cursor](https://img.shields.io/badge/Cursor-compatible-000000)](https://cursor.com/)
[![Gemini CLI](https://img.shields.io/badge/Gemini_CLI-compatible-4285F4?logo=googlegemini&logoColor=white)](https://geminicli.com/)
[![OpenCode](https://img.shields.io/badge/OpenCode-compatible-0F766E)](https://opencode.ai/)

[English](README.en.md) · **简体中文**

把一个想法、问题、文章或参考资料做成带口播、动画和字幕的完整科普视频，而不只是输出脚本或提示词。

![节俭悖论视频画面总览](assets/paradox-of-thrift-contact-sheet.jpg)

▶️ [观看 12 秒 MP4 演示](assets/paradox-of-thrift-demo.mp4)

## 30 秒安装

推荐使用开放的 `skills` CLI，它能识别本仓库的标准 `skills/<name>/SKILL.md` 结构，并让你选择安装到哪个 Agent：

```bash
npx skills add xue-xiaobao/chat-animation --skill chat-animation -g
```

只安装到 Codex：

```bash
npx skills add xue-xiaobao/chat-animation --skill chat-animation -g -a codex -y
```

安装后重新启动 Agent 或新建会话，然后直接提出动画需求即可。没有 Node.js 时，也可以在下方使用手动复制方式。

## 支持的 Agent

Chat Animation 遵循标准 `SKILL.md` 目录结构，核心流程只依赖 Agent 能够读取文件、执行 Python 和调用终端。

| Agent | 状态 | 推荐安装方式 |
| --- | --- | --- |
| Codex App / CLI | **端到端验证通过** | `skills` CLI：`-a codex` |
| Claude Code | 标准兼容 | `skills` CLI：`-a claude-code` |
| Tencent WorkBuddy | 标准兼容 | 导入 Skill，或复制到 `~/.workbuddy/skills/chat-animation/` |
| Hermes Agent | 标准兼容 | `skills` CLI：`-a hermes-agent`，或复制到 `~/.hermes/skills/` |
| Cursor | 标准兼容 | `skills` CLI：`-a cursor` |
| Gemini CLI | 标准兼容 | `skills` CLI：`-a gemini-cli` |
| OpenCode | 标准兼容 | `skills` CLI：`-a opencode` |

“标准兼容”表示目录格式和运行依赖匹配该 Agent 的 Skill 机制；当前版本的真实端到端生产回归在 Codex 完成。不同 Agent 的工具名称、权限与密钥配置界面可能不同。

## 它能做什么？

Chat Animation 为兼容的 AI Agent 提供一套自包含的五阶段制作流程：

```text
编导 → 静态关键帧 → 动画与转场 → 口播 → 最终合成
```

你只需要提出类似这样的要求：

> 使用 Chat Animation 制作一个一分钟的节俭悖论科普动画，面向没有经济学基础的成年人，语气有趣，并让我审核每个阶段。

它会规划论证、撰写台词和分镜、生成画面与动画、制作口播、完成音画同步与字幕，最终交付经过校验的 MP4。

## 为什么选择 Chat Animation？

- **从想法到 MP4：** 不停留在脚本、分镜或提示词阶段。
- **先看样片再付成本：** 图片、动画和声音都先生产一个样例，确认后才批量生成。
- **以口播为时间标准：** 保持声音自然，通过画面变速对齐口播。
- **动画更可控：** Agnes 使用首帧、尾帧和英文动作提示词生成视频。
- **三种剪辑方式：** 支持硬切、独立转场和融合转场，默认使用一秒独立转场。
- **可恢复：** 保存任务 ID、请求摘要、文件哈希、审核记录和本地素材，断网后优先恢复任务。
- **可以局部返工：** 单独重做某个镜头、转场、音色或字幕，不必整批推倒重来。
- **内置 Vox 风格：** 纸张拼贴、贴纸、半调网点、清晰视觉隐喻和克制的呼吸运动。
- **支持预置或克隆音色：** 可以选择 MiMo 预置音色，也可以使用本人或已获授权的 MP3/WAV 样本。
- **字幕字体可移植：** 首次下载并校验得意黑；失败时自动使用 macOS 或 Windows 内置中文字体。

## 使用条件

- Codex，或其他能够读取并执行 `SKILL.md` 的 Agent
- Python 3.9+
- FFmpeg 与 FFprobe
- Agnes API Key，用于图片和视频生成
- Xiaomi MiMo API Key，用于口播生成

Agnes 和 MiMo 是外部服务，可能产生调用费用。不要把 API Key、用户音色样本或私人项目产物提交到公开仓库。

## 手动安装与配置

不使用 `skills` CLI 时，克隆仓库并把 `skills/chat-animation` 复制到对应 Agent 的用户级 Skill 目录。

macOS/Linux 示例：

```bash
mkdir -p ~/.codex/skills
cp -R skills/chat-animation ~/.codex/skills/chat-animation
```

Windows PowerShell 示例：

```powershell
New-Item -ItemType Directory -Force "$env:USERPROFILE\.codex\skills" | Out-Null
Copy-Item -Recurse -Force "skills\chat-animation" "$env:USERPROFILE\.codex\skills\chat-animation"
```

通过环境变量或系统密钥存储配置凭据：

```bash
export AGNES_API_KEY="<your-key>"
export MIMO_API_KEY="<your-key>"
```

第一次创建项目前运行预检：

```bash
python3 skills/chat-animation/scripts/project.py preflight
```

## 使用方法

在 Codex 中直接说：

> 使用 `$chat-animation` 制作一个解释处置效应的 Vox 风格科普动画，每个阶段让我确认。

默认审核流程为：

1. 审核核心观点、台词、分镜、视觉隐喻和转场计划。
2. 先审核一组静态画面，再生成其余图片。
3. 先审核一段动画，再提交其余视频任务。
4. 选择预置音色或已授权的克隆音色，并试听一段口播。
5. 审核最终完成音画同步和字幕的 MP4。

如果不希望逐步等待，可以明确提出：

> 请全自动完成动画，并跳过所有人工审批。

全自动模式仍然执行阶段自检、确定性验证、产物留档和失败阻断。

## 项目产物

每个项目都保留可以修改和审计的分层产物：

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

默认成片规格是 1280×720、24fps、H.264 视频和 AAC 音频。完整工作流见 [`SKILL.md`](skills/chat-animation/SKILL.md)。

## 没有 Codex 能否使用？

Agnes、MiMo、验证和 FFmpeg 适配器都是普通 Python 脚本，技术上不依赖 Codex。但没有能够执行 Skill 的 Agent 时，用户必须自己准备项目契约、台词、提示词、审批记录和质量检查。因此它目前首先是一套 Agent 工作流，还不是面向普通用户的一键应用。

## 开源许可

本仓库使用 [MIT License](LICENSE)。得意黑不随仓库分发，而是在初始化时从官方 Release 下载，仍遵循 SIL Open Font License 1.1。外部模型和服务遵循各自条款。
