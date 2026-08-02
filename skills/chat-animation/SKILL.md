---
name: chat-animation
description: "Turn a user’s idea, question, concept, article, or reference into a complete narrated explainer animation through a self-contained five-stage workflow. Supports hard cuts, dedicated transition animations, and fused motion transitions; defaults to hard cuts, while explicitly selected dedicated transitions default to one second with narration crossing the transition midpoint. Defaults to human review with one-scene samples before costly batches, and supports an explicitly authorized full-auto mode. Includes built-in style knowledge, Agnes image/video adapters, Xiaomi MiMo preset or cloned narration adapters, FFmpeg captions, and composition scripts. Use when the user asks to 制作动画、科普动画、概念讲解视频、纸拼贴或贴纸动画、转场动画、使用自己的音色讲解、全自动完成动画、把一个想法做成带口播字幕的 MP4，or wants a reviewable or automated resumable idea-to-video project."
---

# Chat Animation

把用户的一句话要求做成观点清楚、视觉统一、口播自然、字幕同步且可局部返工的完整 MP4。不要把目标降级为“写提示词”或“生成几段视频”。

## 不可绕过的规则

1. 首次动作必须是预检。与所选区域匹配的 Agnes Key 和 MiMo token 未同时配置时，停止生产并只引导配置。
2. 严格按五阶段执行：编导 → 视觉 → 运动 → 声音 → 合成。
3. 每阶段都必须先由 Agent 自检。`human-gated` 模式展示产物并等待人明确通过；`full-auto` 模式在验证通过后自动进入下一阶段。
4. 默认使用人工 Gate。只有用户明确要求“全自动完成并跳过所有审批”时才启用 `full-auto`；全自动仍执行每阶段自检、确定性验证和产物留档。
5. Agnes 只使用首帧 + 尾帧 + 英文动作提示词的 `keyframes` 模式。禁止用纯文本视频替代。
6. MiMo WAV 是最终时钟。运动生成前先确定声音时序配置；调整画面时长，不变速有声内容来迁就视频。
7. 所有外部结果下载到项目目录；不要依赖临时 URL，不要保存或打印 token。
8. `human-gated` 模式下，视觉、运动、声音三个高成本阶段必须先生产一镜样片并获得明确批准，之后才允许批量生产；样片批准不能替代该阶段的全量批准。`full-auto` 模式可跳过样片 Gate。
9. 生产流程只显式指定本 Skill 的 `scripts/`、`references/` 和项目产物，不在流程文档、命令或用户交付中显式指定本目录之外的能力路由。
10. 转场模式必须在编导层确定。默认使用 `hard-cut` 且转场时长为 0；用户明确选择动画转场时才生成过渡动画，独立转场成片默认 1.0 秒。

## 首次预检

首次使用只配置一次凭据。命令在终端中隐藏输入，并保存到用户私有目录：macOS/Linux 为 `~/.chat-animation/credentials.env`，Windows 为 `%USERPROFILE%\\.chat-animation\\credentials.env`。

```bash
python3 <skill>/scripts/project.py configure-credentials \
  --set agnes-global --set agnes-cn --set mimo
```

只配置实际使用的 Agnes 区域即可。后续自动读取该文件，环境变量只用于临时覆盖。

运行：

```bash
python3 <skill>/scripts/project.py preflight
```

要求：

- 国际站使用 `AGNES_GLOBAL_API_KEY`，CN 站使用 `AGNES_CN_API_KEY`；旧的 Agnes 变量继续作为国际站兼容别名
- `MIMO_API_KEY`
- Python 3.9+
- FFmpeg 与 FFprobe

预检失败时，不创建项目、不进入编导阶段。按命令输出引导用户分别到 Agnes AI 和 Xiaomi MiMo 开放平台创建 key，并用环境变量配置。详细说明见 [providers.md](references/providers.md)。

首次配置新 key 或遇到 401 时，再做一次最小在线鉴权：

```bash
python3 <skill>/scripts/providers.py auth-smoke \
  --output <安全的本地临时目录>/chat-animation-auth-smoke
```

该命令只调用一次 Agnes 文本和一次极短 MiMo TTS；不测试视频。失败时停止，不进入编导层。

预检通过后创建项目：

```bash
python3 <skill>/scripts/project.py init \
  --projects-root <用户指定或当前目录>/chat-animation-projects \
    --name <project-name> \
    --idea "<用户要求>" \
    --style vox \
    --agnes-region global
```

初始化同时从得意黑官方发布页下载固定版本 `v2.0.1` 到当前用户缓存，并校验压缩包与 TTF 的 SHA-256；字体文件不放进 Skill 包。若网络、GitHub 或校验失败，初始化继续进行并自动使用 Windows 的微软雅黑/黑体或 macOS 的苹方/黑体。最终选择写入 `state/font-selection.json`，详见 [fonts.md](references/fonts.md)。

`--style` 可省略，默认读取内部风格注册表的默认项。同名项目自动使用 `_01`、`_02` 版本号。`--agnes-region` 选择 `global` 或 `cn`，并把对应域名固化到项目；只有一套 Key 时可自动选择，两套 Key 同时存在时必须明确指定。转场默认写入 `hard-cut` 和 `0` 秒；需要动画转场时使用 `--transition-mode transition-separated` 或 `transition-fused`，需要调整动画转场时长时使用 `--transition-duration`。

## 审批模式

默认 `human-gated`，保持逐阶段展示、等待用户确认、记录人工批准。仅当用户明确要求全自动并跳过所有审批时，在初始化时记录授权原话：

```bash
python3 <skill>/scripts/project.py init \
  --projects-root <root> --name <name> --idea "<idea>" \
  --full-auto --approval-note "<用户明确要求的原话>"
```

已有项目切换时使用 `set-approval-mode`。不要根据“尽快”“继续”“帮我完成”等模糊表达推断全自动。

`full-auto` 跳过样片等待和人工批准，但不跳过生产顺序、Agent QA、`validate` 和失败阻断。每阶段完成后运行：

```bash
python3 <skill>/scripts/project.py auto-complete <project> <stage>
```

该命令只在 `full-auto` 项目可用，验证通过后记录 `automation_review=completed`。验证失败时停止并修复，不能强行进入下一层。

## 项目契约

```text
<project-name>_01/
├── request.json
├── script.json
├── state/
│   ├── style-selection.json
│   ├── style-definition.md
│   ├── font-selection.json
│   └── motion-plan.json
├── visual/
│   ├── visual-manifest.json
│   ├── 01-first.png
│   ├── 01-end.png
│   └── contact-sheet.jpg
├── motion/
│   ├── motion-manifest.json
│   ├── 01-scene.mp4
│   └── ...
├── audio/
│   ├── audio-manifest.json
│   ├── 01-scene-raw.wav
│   ├── 01-scene.wav
│   └── ...
├── composition/
│   ├── timing.json
│   ├── subtitles.ass
│   ├── aligned/
│   ├── contact-sheet.jpg
│   └── final.mp4
└── reviews/
    ├── 01-director.json
    ├── 02-visual.json
    ├── 02-visual-sample.json
    ├── 03-motion.json
    ├── 03-motion-sample.json
    ├── 04-audio.json
    ├── 04-audio-sample.json
    └── 05-composition.json
```

文件后缀可随供应商实际输出调整，但 manifest 必须记录真实相对路径。所有状态帧必须有内容，禁止用纯色空白图代替。静态帧数量、边界帧复用和视频任务拆分由转场模式决定，完整规则见 [transitions.md](references/transitions.md)。

## 五阶段状态机

每个阶段开始前读取 [stages.md](references/stages.md) 中对应章节。需要写 JSON 时读取 [schemas.md](references/schemas.md)。

### 1. 编导层

目标：把想法变成可听懂的论证、逐镜台词、视觉隐喻、图像提示词和动作提示词。

先完整读取 [director.md](references/director.md) 完成内容导演，并读取 [transitions.md](references/transitions.md) 选择运动剪辑策略。再读取内部注册表 [styles.json](references/styles.json)，按以下顺序选择风格：

1. 用户明确指定风格 ID 或别名时，选择对应项。
2. 用户提供参考图或参考视频时，选择视觉与运动语言最接近的项。
3. 用户未指定时，使用 `default_style_id`。
4. 读取选中项 `reference` 指向的完整风格定义。
5. 在编导预览中展示风格名称、ID 和版本，允许用户在批准前修改。

不在运行时读取其他 Skill 补充风格知识。风格通过 `request.json.style_id/style_version`、`script.json.style_bible`、`state/style-selection.json` 和 `state/style-definition.md` 项目快照固定。Skill 中的风格定义更新后，不自动改变旧项目。切换或刷新风格时运行：

```bash
python3 <skill>/scripts/project.py set-style <project> --style <style-id>
```

输出 `script.json` 和 `state/motion-plan.json`。风格与转场策略相互独立；把规范化的 mode 和目标时长同步写入 `request.json.transition` 与 `script.json.project.transition`。涉及金融、医学、法律、时效信息或专业事实时先检索权威来源，并把来源写入 `script.json.research.sources`。

自检：

```bash
python3 <skill>/scripts/project.py validate <project> director
```

在 `human-gated` 模式向用户展示：选中风格 ID 与版本、转场模式与目标时长、一句话结论、叙事弧、逐镜台词、逐镜视觉隐喻、计划生成的静态帧与视频任务、运动摘要，停下等待确认。收到明确通过后：

```bash
python3 <skill>/scripts/project.py approve <project> director \
  --reviewer human --note "<用户原话或简短摘要>"
```

`full-auto` 模式不等待确认，完成自检后运行 `auto-complete <project> director`。

### 2. 视觉层

目标：根据已批准的 motion plan 得到所需状态帧，而不是无条件为每镜生成两张图片。

生成图片前读取项目内的 `state/style-definition.md`，不要悄悄改用 Skill 中更新后的风格版本。所有静帧和图像提示词必须遵守该项目快照。

先读取 [transitions.md](references/transitions.md) 的静态帧契约：硬切静态模式通常每场景一张；独立转场模式每内容场景首尾两张；融合转场模式默认每叙事状态一张。相邻任务需要完全相同的边界状态时，复用同一个已生成文件，不重复调用图片模型。

`human-gated` 模式先选择一组能代表当前模式的状态帧作为视觉样片，默认使用第一场景。只生成并检查该样片，向用户展示原尺寸图片；不要同时生成其他镜头。样片通过后记录：

```bash
python3 <skill>/scripts/project.py validate-sample <project> visual --scene 01
python3 <skill>/scripts/project.py approve-sample <project> visual \
  --scene 01 --reviewer human --note "<用户原话或简短摘要>"
```

`human-gated` 模式只有 `visual` 样片批准有效时，才生成后续全部静帧。首镜被修改后样片批准自动失效，必须重新展示和批准。`full-auto` 模式按镜生成并检查全部静帧，不创建 sample review。

使用本 Skill 内置的 Agnes Image 适配器，根据 motion plan 和项目快照中的 `frame_policy` 生成有内容的状态帧。`distinct-first-end` 根据 `first_frame_prompt` 和 `image_prompt` 分别生成首帧与完成态尾帧；`shared-hero-frame` 只根据主画面提示词生成一次，并把同一文件复用为首尾帧：

```bash
python3 <skill>/scripts/providers.py agnes-image <project> --scene 01
```

只有用户明确提供图片或迁移已有本地图片时，才用统一导入命令保存原图、规范化尺寸、准备首帧并更新 manifest：

```bash
python3 <skill>/scripts/providers.py register-visual <project> \
  --scene 01 --first <generated-first-frame> --end <generated-end-frame> \
  --provider user-provided --model none
```

在需要双关键帧的内容任务中，首帧和尾帧都必须显式提供。`distinct-first-end` 要求两者视觉可区分；`shared-hero-frame` 要求两者指向同一个权威主画面且哈希相同。融合模式的一张状态帧可以同时作为前一任务尾帧和后一任务首帧；这是连续性复用，不重复生成。命令生成的 QA 默认全部为 `false`，实际查看图片并确认具有叙事内容后才可如实更新。不要用动画模型修复错误静帧。

全部静帧完成后，自检并向用户展示 contact sheet：

```bash
python3 <skill>/scripts/project.py validate <project> visual
```

`human-gated` 模式收到明确通过后批准 `visual`；`full-auto` 模式运行 `auto-complete <project> visual`。

### 3. 运动层

目标：按已批准的转场模式生成内容动画与跨场运动。

先确定声音时序配置。内置默认配置为 MiMo 预置音色“白桦”及固定的中等略快金融科普 context，实测基线 `0.215 秒/有效字符`；用户接受默认配置时直接使用内置基线，不调用 TTS 校准。用户改用其他预置音色、克隆音色或改变会影响语速的 context 时，在提交任何内容动画前只生成一次代表性口播样片：

```bash
python3 <skill>/scripts/providers.py mimo-calibrate <project> --voice <Voice ID>
# 或
python3 <skill>/scripts/providers.py mimo-calibrate <project> \
  --voice-file "/path/to/authorized-voice.mp3" --context "<固定播讲指令>"
```

未指定 `--scene` 时自动选择有效字符最多的镜头。命令用清理后 WAV 时长除以有效字符数，把结果写入 `state/voice-timing.json`，并按模型、音色 ID 或参考音频哈希、context 哈希缓存到用户本地配置。相同声音时序配置在当前项目和后续项目直接复用，不再调用 TTS；配置变化才重新校准。`human-gated` 模式展示首次校准音频并确认声音后再生成运动，`full-auto` 模式完成自动试听/转写 QA 后继续。

先完整读取 [transitions.md](references/transitions.md)。动作语言来自项目内的 `state/style-definition.md`；Agnes 的双关键帧契约保持不变，但任务拆分不同：

- `hard-cut`：不生成转场任务；静态项目不调用视频模型，有内部运动时只生成各场景内容任务。
- `transition-separated`：可选的高质量动画转场；生成 N 个内容任务和 N-1 个独立转场任务。内容任务不得进入下一场景，转场任务只连接前景尾帧与后景首帧。独立转场成片默认压缩到 1.0 秒。
- `transition-fused`：通常用 N 张状态图生成 N-1 个融合任务；每个提示词明确“内容动作”和“进入下一状态”两个节拍，并记录转场区间。

```bash
python3 <skill>/scripts/providers.py agnes-video <project> --scene 01 --poll
python3 <skill>/scripts/project.py validate-sample <project> motion --scene 01
python3 <skill>/scripts/project.py approve-sample <project> motion \
  --scene 01 --reviewer human --note "<用户原话或简短摘要>"
python3 <skill>/scripts/providers.py agnes-video <project> --all --poll
python3 <skill>/scripts/project.py validate <project> motion
```

默认 `agnes-video-v2.0`、1280×720、24fps，串行提交。提交内容动画前统计该镜有效台词字数，乘以当前项目 `state/voice-timing.json` 的实测值；没有该文件时只能使用内置“白桦”基线。把预计口播时长映射到最接近的 Agnes 合法帧数（`8n+1`，81–441 帧）；转场任务仍默认 169 帧。motion plan 可用 `target_duration_seconds` 人工覆盖，CLI 可用 `--num-frames` 显式覆盖。若预计时长超过 441 帧在 24fps 下的上限 `18.375 秒`，必须先在自然语义停顿处拆成多个内容镜头，并为每个新镜头补齐首尾帧和运动提示词；禁止钳制到 441 帧后再靠合成长时间拉伸。每镜保存字数、声音时序来源、预计时长、帧数来源、请求摘要、task/video ID、原始 MP4、无声 MP4、首尾抽帧和 contact sheet。帧数变化视为新的运动请求，不能因提示词未变而复用旧视频。网络中断时先恢复已有 task，禁止盲目重复提交。

`human-gated` 模式必须先展示一镜完整运动样片，收到明确通过后才能批量提交其余镜头；全量完成后再展示运动 contact sheet 并批准 `motion`。`full-auto` 模式可直接 `--all` 串行生成，逐镜 QA 后运行 `auto-complete <project> motion`。

### 4. 声音层

目标：使用运动层已经锁定的声音配置，通过 MiMo V2.5 TTS 按镜生成自然中文口播。用户未替换声音时使用默认“白桦”；已校准其他声音时必须沿用 `state/voice-timing.json` 中相同的音色与 context：

1. MiMo 预置音色：列出适合当前语言的音色并让用户指定。
2. 用户音色：要求用户提供本人或已获授权的 MP3/WAV 样本，使用 `mimo-v2.5-tts-voiceclone`；样本不超过 10 MB，并复制到项目 `audio/reference/` 留存哈希。

`human-gated` 模式把运动前的首次校准样片同时作为声音试听样片；使用内置默认音色时，在声音层先生成一镜试听。`full-auto` 模式未指定声音时直接使用内置默认配置。

```bash
python3 <skill>/scripts/providers.py mimo-tts <project> --scene 01
```

用户音色样例：

```bash
python3 <skill>/scripts/providers.py mimo-tts <project> --scene 01 \
  --voice-file "/path/to/authorized-voice.mp3" \
  --context "自然清晰的中文科普解说，语速中等，停顿克制。"
python3 <skill>/scripts/project.py validate-sample <project> audio --scene 01
python3 <skill>/scripts/project.py approve-sample <project> audio \
  --scene 01 --reviewer human --note "<用户原话或简短摘要>"
python3 <skill>/scripts/providers.py mimo-tts <project> --all \
  --voice-file "/path/to/authorized-voice.mp3" \
  --context "自然清晰的中文科普解说，语速中等，停顿克制。"
python3 <skill>/scripts/project.py validate <project> audio
```

预置音色也要完成同样的 `validate-sample`、试听和 `approve-sample`，之后才能以完全相同的 voice/context 参数运行 `--all`。

优先一镜一次完整合成。保留 raw WAV；只压缩异常长静音，不改变有声段速度和音高。逐镜试听或转写核对，不得只检查文件存在。批量参数与已批准样片的模型、音色、参考音频哈希和 context 不一致时停止。

`human-gated` 模式向用户提供试听文件与时长表，收到明确通过后批准 `audio`；`full-auto` 模式逐镜完成试听/转写 QA 后运行 `auto-complete <project> audio`。

### 5. 合成层

目标：以清理后的 WAV 为主时钟，按 motion plan 变速画面，按用户要求选择是否生成单行字幕，并导出最终 MP4。

只使用本 Skill 内置的 FFmpeg 合成脚本：

```bash
python3 <skill>/scripts/compose.py <project>
python3 <skill>/scripts/project.py validate <project> composition
```

硬切模式让台词边界对齐切点。两种过渡动画模式都不得为转场插入静音：上一场景台词覆盖转场前半段，下一场景台词从转场中点开始并覆盖后半段；中间场景的台词还覆盖下一转场的前半段。融合模式按记录的内部转场区间定位中点，不能简单按文件边界切台词。字幕启用时默认读取 `state/font-selection.json`：优先得意黑，下载不可用时使用当前系统的中文字体；仍保持按真实停顿切换、单行、白字、黑描边、无背景。用户明确不要字幕时不烧录字幕。镜头之间没有黑场或静音缝隙。完成 FFprobe、完整解码和全片 contact sheet 后展示最终视频。`human-gated` 模式收到明确通过后批准 `composition`；`full-auto` 模式运行 `auto-complete <project> composition` 后直接交付。

## 独立替换与局部返工

- 替换编导：重写 `script.json`，使后续审批失效。
- 切换视频风格：运行 `set-style`，重写当前层提示词并从编导层重新审核。
- 替换图片模型：只重做 `visual/` 对应镜头。
- 替换视频模型：保持 visual manifest 契约，只重做 `motion/`。
- 替换音色或影响语速的播讲指令：先校准或读取缓存；若时序配置改变，则按新帧数重做受影响的 `motion/`，再重做 `audio/` 和合成。
- 修改字幕：只改 `composition/timing.json` 或字幕文件并重渲染。
- 单镜失败：只重做该镜，禁止整批推倒重来。

任何上游已确认产物发生变化时，必须重新运行该阶段验证；`human-gated` 模式重新获得人类批准，`full-auto` 模式重新完成自动验证。下游 review 自动视为过期。

## 扩展内部风格

新增风格时：

1. 新增 `references/style-<id>.md`，完整定义适用范围、视觉签名、构图与材质、首尾帧、动作语法、图像/动作提示词、QA 和常见失败。
2. 在 `references/styles.json` 登记唯一 ID、用户名称、版本、别名、定义路径、运动策略和 `frame_policy`。当前合法策略为 `distinct-first-end` 与 `shared-hero-frame`。
3. 用至少一个真实编导任务验证后再设为默认或用于生产。

修改既有风格的视觉或运动结果时递增版本；只修错别字时不递增。不要在其他文档重复维护风格列表。

## 扩展内置能力

生产过程中发现内置能力缺口时，先进入 Skill debug/维护流程。可以查阅本机已有实现或官方资料来理解协议，但不要把参考来源显式写进生产流程或用户交付；应把必要知识、请求适配、恢复逻辑和校验规则沉淀到本目录的 `references/` 或 `scripts/`，补充离线回归并通过结构校验后再恢复生产。不要复制无关文件，也不要保留运行时引用。

## 完成定义

- `human-gated`：五个 review 均为 `human_review.status=approved`，三个 sample review 均有效
- `full-auto`：五个 review 均为 `automation_review.status=completed`，sample review 可省略
- `request.json`、`style_bible` 和风格快照的 ID、版本与哈希一致
- 所有运动镜头均记录 `mode=keyframes` 和两张输入帧
- `request.json`、`script.json` 与 `state/motion-plan.json` 的转场模式一致；未指定时为 `hard-cut` 且转场时长为 0，明确选择独立转场时成片默认 1.0 秒
- 过渡动画的台词交接位于转场中点，整条口播没有转场静音
- 最终 MP4 为 1280×720、24fps、H.264 + AAC 且可完整解码
- 总时长与清理后 WAV 累计时长仅有编码级误差
- 字幕不换行、不溢出、不遮挡主体
- 中间产物、请求摘要、provider 记录和 QA 结论可追溯
