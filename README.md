# Chat Animation

[![License: MIT](https://img.shields.io/badge/License-MIT-22c55e.svg)](LICENSE)
[![Python 3.9+](https://img.shields.io/badge/Python-3.9%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)

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

https://github.com/user-attachments/assets/b02f0520-e2f9-4368-8504-84276eff1d2f

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

### 让你的 Agent 帮你安装

不想使用命令行时，把下面这段提示词完整复制给 Codex、Claude Code、WorkBuddy、Hermes 或其他支持 Skill 的 Agent：

```text
请从 https://github.com/xue-xiaobao/chat-animation 安装 chat-animation Skill。

要求：
1. 阅读仓库的 README.md 和 skills/chat-animation/SKILL.md，确认安装内容。
2. 把 skills/chat-animation 安装到你当前 Agent 的用户级 Skill 目录，不要修改 Skill 本体。
3. 检查 Python 3.9+、FFmpeg 和 FFprobe 是否可用。
4. 不要在聊天、日志或仓库中写入真实 API Key。
5. 安装完成后只运行 preflight；不要提交图片、视频或语音等付费生成任务。
6. 最后告诉我安装位置、检查结果，以及还需要我配置哪些 API Key。
```

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

## 动画风格

当前内置两种经过完整提示词、关键帧策略和动作 QA 约束的 16:9 风格。它们不是简单的画面滤镜，而是会同时改变视觉隐喻、静态帧数量和动画生成方式。

| 风格 | 视觉语言 | 关键帧与动作策略 | 更适合 |
| --- | --- | --- | --- |
| **Vox 风格**（`vox`，默认） | 强烈平坦色场、黑白半调照片剪贴、彩色卡纸点缀、奶油白描边和编辑海报式构图 | 每镜生成内容不同但构图一致的首尾帧；纸片按因果顺序克制组装，落位后只保留一次极慢呼吸 | 金融机制、认知偏差、抽象概念和观点解释 |
| **Storybook 风格**（`storybook`） | 温暖彩色纸雕、绘本舞台、贴纸人物、柔和阴影和生活化场景 | 每镜只生成一张权威主画面并同时作为首尾帧；前景约 1.2 秒柔和入场，随后按约四秒周期低幅呼吸 | 儿童科普、寓言、心理与社会概念，以及更亲和的生活化解释 |

选择优先级是“用户明确指定 → 参考素材最接近 → 默认 Vox”。风格定义会在项目初始化时保存快照，因此 Skill 日后更新风格，不会悄悄改变旧项目。使用时直接说“使用 Vox 风格”或“使用 Storybook 风格”即可。

## 工作原理

Chat Animation 不是一次性生成整条视频，而是把生产过程拆成五层。每层都有结构化产物、自动检查和审批记录；上游确认后，下游才会开始。图片、视频和声音三个高成本阶段默认先生成一个样片，用户确认后再批量生产。

| 层级 | 负责什么 | 默认模型或工具 | 人在环节里做什么 |
| --- | --- | --- | --- |
| 1. 编导层 | 研究主题，确定结论、叙事结构、逐镜台词、视觉隐喻和转场计划 | 当前 Agent 使用的语言模型；专业或时效内容会配合权威资料检索 | 审核“只听台词能否听懂”、事实是否准确、分镜是否值得继续制作 |
| 2. 视觉层 | 按运动计划生成有内容的静态关键帧，固定风格、构图和主体关系 | `agnes-image-2.1-flash` | 先审核一组静帧样片，再检查批量画面的画风、构图、手部和文字错误 |
| 3. 运动层 | 使用首帧、尾帧和英文动作提示词生成内容动画与场景转场 | `agnes-video-v2.0`，1280×720、24fps、keyframes 模式 | 先审核一段完整动画，确认动作幅度、参考图保持、变形和转场节奏 |
| 4. 声音层 | 按镜生成中文口播，支持预置音色与已授权的用户音色 | `mimo-v2.5-tts` 或 `mimo-v2.5-tts-voiceclone` | 选择声音来源，试听一段，确认音色、语速、情绪和停顿 |
| 5. 合成层 | 以口播为时钟对齐画面，拼接镜头、转场和字幕，输出最终 MP4 | 本地 FFmpeg / FFprobe，不使用生成模型 | 审核最终成片的内容、音画同步、字幕、转场和整体观看体验 |

核心运作逻辑：

1. **编导先于生成：** 先把观点和台词讲清楚，再花费图片、视频和声音额度。
2. **静态帧约束动画：** 动画使用首尾关键帧，不用纯文本视频随机猜测构图。
3. **转场提前规划：** 支持硬切、独立转场和融合转场，默认使用一秒独立转场。
4. **口播是最终时钟：** 保持人声自然，通过画面变速匹配音频，而不是加速口播迁就视频。
5. **人在环路中：** 默认每层由 Agent 自检、用户确认；用户明确要求时也可以全自动运行。
6. **可以恢复和局部返工：** 项目保存提示词、任务 ID、哈希、审批和中间素材，断网后可恢复，单镜失败只重做单镜。

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

## FAQ

### 是否要收费？

Skill 本身使用 MIT License，下载安装到本地不收费。实际制作时可能产生三类外部费用：你所使用的 Agent 或语言模型、Agnes 图片/视频生成、Xiaomi MiMo 语音生成。Python、FFmpeg 和本地合成不收费。具体单价和余额以各服务商控制台为准。

### 消耗多少 Token？

没有固定值。编导、资料研究、修改轮次和 Agent 对话会消耗语言模型 Token；Agnes 的图片与视频、MiMo 的语音通常按各自平台的任务、时长或额度规则计费，不等同于 Agent 的文本 Token。成本主要受镜头数量、动画时长和返工次数影响。默认的“先做一个样片再批量生成”就是为了减少无效消耗。

### 如何安装？

推荐运行：

```bash
npx skills add xue-xiaobao/chat-animation --skill chat-animation -g
```

也可以把上方“让你的 Agent 帮你安装”提示词复制给 Agent，或手动把 `skills/chat-animation` 复制到对应的用户级 Skill 目录。安装后运行 `preflight`，按提示配置 Agnes 与 MiMo API Key。

### 如何使用？

安装后重新打开 Agent，直接描述想讲的主题、受众、时长和风格，例如：

> 使用 `$chat-animation` 制作一个一分钟的节俭悖论 Vox 风格科普动画，面向没有经济学基础的成年人，每个阶段让我确认。

默认流程会依次让你确认编导、视觉样片、动画样片、声音样片和最终成片。只有明确提出“全自动完成并跳过所有审批”时，才会跳过等待确认。

## 开源许可

本仓库使用 [MIT License](LICENSE)。Vox 风格中的编辑半调纸拼贴方法参考并改写自 MIT 授权的 [`pyang5166/gbro-collage-broll`](https://github.com/pyang5166/gbro-collage-broll)，原始版权与许可见 [第三方声明](skills/chat-animation/THIRD_PARTY_NOTICES.md)。这里的“Vox 风格”是对一类编辑视觉语言的描述，不表示本项目与 Vox Media 存在隶属、合作或背书关系。

得意黑不随仓库分发，而是在初始化时从官方 Release 下载，仍遵循 SIL Open Font License 1.1。外部模型和服务遵循各自条款。
