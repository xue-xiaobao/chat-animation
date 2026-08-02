# 五阶段产物与审批模式

## 目录

1. 通用 Gate 协议
2. 编导层
3. 视觉层
4. 运动层
5. 声音层
6. 合成层
7. 返工与审批失效

## 1. 通用 Gate 协议

每阶段都按同一顺序执行：

```text
读取上游已确认产物
→ 只生产当前层
→ Agent 自检
→ 展示可审阅产物
→ 停止并等待人类意见
→ 人类明确通过
→ 运行 approve 记录批准
→ 下一层
```

默认 `human-gated`：Agent 不能代表人类批准，`approve` 只能在当前对话收到明确通过后执行。

用户明确要求全自动并跳过全部审批时使用 `full-auto`：不等待人类 Gate、不创建 sample review，每阶段仍需完成 Agent QA 和确定性验证，再以 `auto-complete` 记录自动完成。任何验证失败都必须停止修复。

每个 review 记录：

- stage
- validated_at
- self_review.status 和 checks
- human_review.status、reviewer、approved_at、note
- full-auto 时的 automation_review.status、completed_at、authorization_note
- approved_artifacts 的相对路径、大小和 SHA-256

## 2. 编导层

输入：`request.json` 和可选参考资料。

输出：`script.json`，包含：

- 项目目标、受众、记忆点、语气、画幅和时长
- 内部风格 ID、版本和项目快照
- 研究结论、来源、边界
- 一句话结论和完整叙事弧
- 风格圣经
- 转场模式、目标时长和 `state/motion-plan.json`
- 逐镜台词、视觉隐喻、元素、首尾帧意图
- image prompt 与 Agnes motion prompt

Agent 自检：

- request、style_bible 和 style-selection 的 ID、版本一致
- 不看画面也能听懂
- 每镜推动论证，不重复
- 专业词第一次出现有通俗解释
- 事实与推断分开
- 每镜只有一个视觉命题
- 每镜 3–6 个关键组
- 图像/运动提示词自包含
- 总字数与目标时长大致匹配
- `request.json`、`script.json` 与 motion plan 的转场模式一致
- 默认使用 `hard-cut` 且转场时长为 0；明确选择独立转场时默认 1.0 秒

给人审阅：先给选中风格、结论和叙事弧，再给逐镜表。不要用大段 JSON 代替可读预览。

## 3. 视觉层

输入：已通过人工批准或自动验证的 `script.json`。

输出：

- `visual/visual-manifest.json`
- motion plan 实际要求的状态帧
- `visual/contact-sheet.jpg`
- 可选单镜对照和 QA 备注

视觉层必须读取项目自己的 `state/style-definition.md`，不能在中途采用 Skill 中更新后的风格定义。

生成静态帧前完整读取 [transitions.md](transitions.md)。静态帧策略由转场模式决定：

- `hard-cut`：静态项目每场景一张完成态；场景内部有动画时才生成该场景首尾帧；
- `transition-separated`：每个内容场景生成首帧和完成尾帧，独立转场复用前景尾帧与后景首帧；
- `transition-fused`：默认每个叙事状态一张，当前状态与下一状态组成一个融合视频任务。

通用状态帧策略：

- 每镜独立生成，表达该镜有意义的初始叙事状态
- 默认保留主体、环境或因果关系中的至少一个可识别内容组
- 首帧不能是纯色空白图，也不能只剩无语义的纸张纹理
- 只有同一个边界状态需要连续传递时才复用同一个文件，不重复调用图片模型
- 双关键帧任务的首尾帧必须视觉可区分，并共同定义状态变化

尾帧策略：

- 16:9 完成构图
- 3–6 个可分离组
- 主体中部，底部字幕安全区
- 自然的脸、手、肢体和物体结构
- 无多余文字、数字、logo、UI、水印

Agent 必须视觉检查实际图片，不得只检查文件名和尺寸。

样片 Gate：

- 默认先做第一镜；另一镜更能代表整体难度时可明确改选。
- 样片生成后立即停止，展示原图、模型和检查结论。
- 用户明确通过后运行 `validate-sample` 与 `approve-sample`。
- 未批准前只能重做同一镜，禁止生成第二镜或批量生成。
- 样片 manifest 条目或文件变化会使样片批准失效。

批量完成后展示 contact sheet，并标记任何“带瑕疵通过”的理由；这时仍需正式 `visual` 阶段批准。

## 4. 运动层

输入：已通过人工批准或自动验证的视觉 manifest 和逐镜动作提示词。

输出：

- `motion/motion-manifest.json`
- 每镜请求摘要与 provider 状态
- 原始 MP4 和无声标准化 MP4
- 每镜 contact sheet、实际首帧和尾帧

固定约束：

- provider：Agnes
- model：`agnes-video-v2.0`
- mode：`keyframes`
- 两张输入图
- 默认 1280×720、24fps；内容任务按台词字数规划 81–441 帧，转场任务默认 169 帧
- 串行提交

风格相关的运动速度、组装顺序、落位状态和呼吸幅度来自项目风格快照；提供商契约仍固定为 Agnes 双关键帧。

内容动画提交前先锁定声音时序配置并做时长预算：内置“白桦”配置使用已验证的 `0.215 秒/字` 基线；其他音色、克隆声音或不同语速 context 先生成一次代表性 MiMo 样片，测得秒/字并缓存，相同配置不重复测量。逐镜统计有效台词字数，再取最接近的 Agnes 合法帧数 `8n+1`。目标是让原始视频时长接近预计口播，避免合成层把短视频大幅拉长而导致运动迟缓。帧数或时长计划变化必须生成新 run 并保留旧产物。

任务拆分读取 [transitions.md](transitions.md)：

- `hard-cut`：静态时不调用 Agnes Video；有内部动画时只提交 N 个内容任务。
- `transition-separated`：提交 N 个内容任务和 N-1 个独立转场任务。明确选择该动画转场时，独立转场成片默认为 1.0 秒。
- `transition-fused`：通常提交 N-1 个“内容动作 + 转场”任务，记录每段内部的动作区间与转场区间。

独立内容任务不得提前进入下一场景；独立转场任务不得重复内容动作。融合任务出现人物、手部或物体比例重绘时，回退到独立转场，而不是继续增加提示词复杂度。

检查：

- 实际第一帧接近已确认首帧
- 中间逐件组装，不是整画面漂移
- 固定机位和背景
- 没有新增物件、假字、额外手指或结构变形
- 落位后只有极慢、低幅呼吸
- 最后帧接近确认尾帧
- 交付版本无音轨

样片 Gate：

- 只提交一镜 Agnes 双关键帧视频，等待完成并完整查看。
- 展示该镜 MP4，不能只展示首尾截图。
- 用户明确通过并记录 `motion` 样片批准后，才允许 `--all`。
- 未批准前只能恢复或重做同一镜，不能提交其他镜头。
- 批量完成后再做全量运动 QA 和正式 `motion` 阶段批准。

## 5. 声音层

输入：已确认台词；阶段顺序上还要求运动层已通过人工批准或自动验证。

输出：

- `audio/audio-manifest.json`
- 每镜 raw WAV
- 每镜清理后 WAV
- 时长、文本哈希、voice、context 和清理报告

生成前让用户选择声音来源：

- 预置音色：model=`mimo-v2.5-tts`；默认白桦，中文还可选冰糖、茉莉、苏打。
- 用户音色：model=`mimo-v2.5-tts-voiceclone`；输入本人或已授权的 MP3/WAV，最大 10 MB。

用户音色复制到 `audio/reference/`，manifest 记录相对路径、MIME、字节数和 SHA-256。不得把 Base64 Data URL 写进 provider 记录。用户未指定时使用已声明的默认白桦配置；替换声音时必须在运动生成前完成一次时序校准或命中已有缓存。

样片 Gate：

- 选定生成方式后只生成一镜 WAV，清理异常静音并提供试听。
- Agent 先核对台词与自然度，再让用户审核音色、语速、情绪和停顿。
- 用户明确通过后记录 `audio` 样片批准，才允许批量生成。
- 批量必须沿用样片的 model、mode、voice、reference SHA-256 和 context；任一变化都要重做样片。
- 批量完成后仍需逐镜核对和正式 `audio` 阶段批准。

默认一镜一次完整请求。

清理只处理明显异常静音。不要：

- 把所有停顿删掉
- 为适配视频而变速声音
- 把一句话拆成多个 TTS 请求再机械拼接

Agent 需要逐镜试听，或用可靠 ASR 转写并与原台词核对；必要时重生单镜。

## 6. 合成层

输入：已通过人工批准或自动验证的无声 motion MP4 和清理后 WAV。

输出：

- `composition/timing.json`
- `composition/subtitles.ass`
- 逐镜 aligned MP4
- `composition/final.mp4`
- `composition/contact-sheet.jpg`
- 媒体 QA

字体输入来自初始化生成的 `state/font-selection.json`。默认得意黑；若初始化下载失败，明确记录并使用当前 Windows/macOS 内置中文字体。合成时将实际字体文件复制到 `composition/fonts/`。

规则：

- MiMo clean WAV 是总时钟，所有台词首尾无额外静音
- 画面用 `setpts` 变速，音频不变速
- 1280×704 等非标准返回用同色或黑色补边到 1280×720，不拉伸
- `hard-cut`：台词边界与画面切点对齐
- `transition-separated`：上一场景台词覆盖独立转场前半段，下一场景台词从转场中点开始覆盖后半段；独立转场默认 1.0 秒
- `transition-fused`：按 motion plan 记录的内部转场区间，把台词交接点对齐该区间中点，不能用文件边界代替
- 上一句音频结束时下一句立即开始，无黑场、无额外停顿
- 字幕按标点分句，再吸附到真实静音
- 单行、无背景、白字、黑描边

完成检查：

- 1280×720、24fps
- H.264 + AAC
- 可完整解码
- 无黑帧和静音缝隙
- 转场中点与台词交接点一致
- 字幕不换行、不溢出、不遮挡主体
- 总时长与 clean WAV 累计时长接近

## 7. 返工与审批失效

若已确认阶段的文件发生变化：

1. 当前阶段批准失效。
2. 所有下游批准失效。
3. 只重做受影响镜头或文件。
4. 从最早变化阶段重新验证与人工审批。

不要覆盖旧的付费/耗时产物。使用 `-v02`、`-v03` 或 provider run 子目录保留历史，manifest 指向当前采用版本。
