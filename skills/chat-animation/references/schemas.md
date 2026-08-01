# 项目 JSON 契约

## 目录

1. request.json
2. script.json
3. font-selection.json
4. motion-plan.json
5. voice-timing.json
6. visual-manifest.json
7. motion-manifest.json
8. audio-manifest.json
9. timing.json
10. review

所有路径相对项目根目录。所有 JSON 使用 UTF-8、两个空格缩进，不保存 token。

`state/style-selection.json` 除风格 ID、版本、定义快照和哈希外，还固定：

```json
{
  "motion_strategy": "content-to-completed-keyframes",
  "frame_policy": "distinct-first-end"
}
```

`frame_policy` 只允许 `distinct-first-end` 或 `shared-hero-frame`。前者要求内容首尾帧不同；后者要求首尾字段引用同一权威主画面且文件哈希相同。旧项目未保存此字段时按 `distinct-first-end` 兼容。

## 1. request.json

```json
{
  "schema_version": "1.0",
  "project_name": "disposition-effect",
  "version": "01",
  "idea": "为什么人会卖掉涨得好的，却死守亏损的？",
  "style_id": "vox",
  "style_version": "2.0",
  "audience": "没有专业背景的成年人",
  "desired_takeaway": "",
  "target_duration_seconds": 90,
  "tone": "有趣但不轻浮",
  "language": "zh-CN",
  "approval_mode": "human-gated",
  "approval_note": "",
  "transition": {
    "mode": "transition-separated",
    "duration_seconds": 1.0
  },
  "frame": {
    "aspect_ratio": "16:9",
    "width": 1280,
    "height": 720,
    "fps": 24
  },
  "caption_font": {
    "id": "smiley-sans",
    "family": "Smiley Sans",
    "source": "downloaded-cache"
  },
  "created_at": "ISO-8601"
}
```

用户明确要求全自动时，`approval_mode` 为 `full-auto`，`approval_note` 保存其授权原话。不能从模糊表达推断该模式。

`transition.mode` 只允许：`hard-cut`、`transition-separated`、`transition-fused`。默认是 `transition-separated`。`hard-cut` 的 `duration_seconds` 固定为 `0`；两种动画转场默认 `1.0`，用户可明确修改。

## 1.1 font-selection.json

初始化写入 `state/font-selection.json`。默认成功时：

```json
{
  "schema_version": "1.0",
  "requested": "smiley-sans",
  "id": "smiley-sans",
  "display_name": "得意黑",
  "family": "Smiley Sans",
  "version": "2.0.1",
  "source": "downloaded-cache",
  "file": "/absolute/user-cache/SmileySans-Oblique.ttf",
  "sha256": "b447d7e781f08bc95c4c9f23ba71ed2b8ebb639aa7184485c71c4ca5afcd25c4",
  "license": "SIL Open Font License 1.1",
  "initialized_at": "ISO-8601"
}
```

已缓存时 `source=cached`。下载失败时 `id=system-fallback`，`source` 为 `system-fallback` 或 `system-fallback-family`，并记录 `fallback_reason`；不得因此阻断初始化。

## 2. script.json

```json
{
  "schema_version": "1.0",
  "project": {
    "title": "标题",
    "one_sentence_takeaway": "观众看完能复述的一句话",
    "narrative_arc": ["钩子", "冲突", "机制", "方法", "记忆句"],
    "transition": {
      "mode": "transition-separated",
      "duration_seconds": 1.0
    }
  },
  "research": {
    "question_type": "concept",
    "supporting_points": ["支撑点"],
    "misconceptions": ["误解"],
    "boundaries": ["非投资建议"],
    "sources": [
      {"title": "来源名", "url": "https://...", "supports": "支持什么"}
    ]
  },
  "style_bible": {
    "id": "vox",
    "version": "2.0",
    "source": "chat-animation-internal",
    "name": "Vox Style",
    "continuity": "统一半调、描边、纸张和阴影",
    "caption_safe_area": "lower 16 percent",
    "avoid": ["logo", "watermark", "UI", "glossy 3D"]
  },
  "scenes": [
    {
      "id": "01",
      "slug": "hook",
      "purpose": "提出矛盾",
      "narration": "为什么很多人一赚钱就卖，一亏钱却死扛？",
      "caption_phrases": ["为什么很多人一赚钱就卖", "一亏钱却死扛？"],
      "emotion": "惊讶",
      "visual": {
        "meaning": "同一个人对赢家和输家采取相反动作",
        "metaphor": "人物推走上升卡片，却抱紧下沉卡片",
        "elements": ["人物", "上升卡", "下沉卡"],
        "background_hex": "#2D1747",
        "accent_colors": ["#E94F37", "#2CB5A0", "#F3E8CE"],
        "first_frame": {
          "type": "content-keyframe",
          "description": "人物站在两张尚未变化的投资卡片之间，冲突已经建立"
        },
        "end_frame": "完成构图描述",
        "assembly_order": ["上升轨道", "下降轨道", "人物与动作"],
        "ambiguities_to_avoid": ["不要变成交易 UI"]
      },
      "first_frame_prompt": "Self-contained English prompt for a content-rich initial keyframe",
      "image_prompt": "Self-contained English image prompt",
      "motion_prompt": "Self-contained English Agnes keyframes prompt"
    }
  ]
}
```

`script.json.project.transition` 必须与 `request.json.transition` 一致。

## 3. motion-plan.json

`state/motion-plan.json` 在编导层生成，是视觉层、运动层和合成层之间的共享契约。

独立转场示例：

```json
{
  "schema_version": "1.0",
  "transition": {
    "mode": "transition-separated",
    "duration_seconds": 1.0
  },
  "states": [
    {"id": "01-first", "scene_id": "01", "role": "content-first"},
    {"id": "01-end", "scene_id": "01", "role": "content-end"},
    {"id": "02-first", "scene_id": "02", "role": "content-first"},
    {"id": "02-end", "scene_id": "02", "role": "content-end"}
  ],
  "jobs": [
    {"id": "content-01", "kind": "content", "first": "01-first", "end": "01-end"},
    {"id": "transition-01-02", "kind": "transition", "first": "01-end", "end": "02-first"},
    {"id": "content-02", "kind": "content", "first": "02-first", "end": "02-end"}
  ],
  "narration_handoffs": [
    {"from_scene": "01", "to_scene": "02", "at": "transition-midpoint"}
  ]
}
```

内容任务的 `target_duration_seconds` 只用于人工明确覆盖，不承载尚未测量的全局估值。默认时长由运动层用每镜有效字符数乘以当前 `state/voice-timing.json` 的秒/字得到；没有该文件时只允许使用内置白桦基线。转场任务沿用转场时长规则。若目标超过 441 帧在 24fps 下的 `18.375 秒` 上限，编导层必须先拆镜，禁止依赖后期拉伸兜底。

三种模式的结构：

- `hard-cut`：没有 transition job；静态项目的 `jobs` 可以为空。
- `transition-separated`：N 个 content job + N-1 个 transition job。
- `transition-fused`：通常 N 个 state + N-1 个 fused job；每个 fused job 额外记录 `content_range` 与 `transition_range`。

## 3.1 voice-timing.json

`state/voice-timing.json` 在运动生成前锁定当前声音的时序基线。默认白桦配置使用内置记录；替换音色时由一次性校准或本地缓存写入：

```json
{
  "schema_version": "1.0",
  "profile_id": "...",
  "source": "measured-sample",
  "model": "mimo-v2.5-tts",
  "mode": "preset",
  "voice": "茉莉",
  "voice_reference_sha256": null,
  "context": "自然清晰的中文金融科普解说……",
  "context_sha256": "...",
  "sample_scene_id": "02",
  "sample_characters": 57,
  "sample_duration_seconds": 12.105083,
  "seconds_per_character": 0.212370,
  "characters_per_second": 4.708774,
  "sample_audio": "audio/02-mechanism.wav"
}
```

`source` 可为 `built-in-default`、`measured-sample` 或 `cached-measurement`。`profile_id` 由 model、mode、voice 或参考音频哈希以及 context 哈希共同确定；相同 ID 只测量一次。缓存命中时 `sample_audio` 可以省略，因为原样片不属于当前项目。

## 4. visual-manifest.json

```json
{
  "schema_version": "1.0",
  "provider": "agnes",
  "scenes": [
    {
      "id": "01",
      "frame_policy": "distinct-first-end",
      "first_frame": "visual/01-first.png",
      "end_frame": "visual/01-end.png",
      "first_frame_prompt_sha256": "...",
      "end_frame_prompt_sha256": "...",
      "width": 1280,
      "height": 720,
      "qa": {
        "first_frame_meaningful": true,
        "metaphor_readable": true,
        "anatomy_valid": true,
        "no_unwanted_text": true,
        "caption_safe": true
      }
    }
  ],
  "contact_sheet": "visual/contact-sheet.jpg"
}
```

manifest 只登记 motion plan 实际需要的状态帧。所有状态帧必须有内容；同一个跨场边界状态允许按 motion plan 复用同一文件，禁止为相同像素重复调用图片模型。`shared-hero-frame` 场景的 `first_frame` 与 `end_frame` 应为同一相对路径；供应商记录必须说明图片只生成一次并被两个关键帧槽位复用。

## 5. motion-manifest.json

```json
{
  "schema_version": "1.0",
  "provider": "agnes",
  "model": "agnes-video-v2.0",
  "mode": "keyframes",
  "scenes": [
    {
      "id": "01",
      "first_frame": "visual/01-first.png",
      "end_frame": "visual/01-end.png",
      "prompt_sha256": "...",
      "provider_record": "motion/runs/01-v01/provider.json",
      "raw_video": "motion/runs/01-v01/raw.mp4",
      "video": "motion/01-hook.mp4",
      "contact_sheet": "motion/runs/01-v01/contact-sheet.jpg",
      "width": 1280,
      "height": 720,
      "fps": 24,
      "has_audio": false
    }
  ]
}
```

## 6. audio-manifest.json

```json
{
  "schema_version": "1.0",
  "provider": "mimo",
  "model": "mimo-v2.5-tts-voiceclone",
  "mode": "voiceclone",
  "voice": "user-reference",
  "voice_reference": {
    "path": "audio/reference/voice-ab12cd34ef56.mp3",
    "sha256": "...",
    "bytes": 168696,
    "mime_type": "audio/mpeg"
  },
  "scenes": [
    {
      "id": "01",
      "model": "mimo-v2.5-tts-voiceclone",
      "mode": "voiceclone",
      "voice": "user-reference",
      "voice_reference_sha256": "...",
      "narration_sha256": "...",
      "raw_audio": "audio/01-hook-raw.wav",
      "audio": "audio/01-hook.wav",
      "duration_seconds": 5.12,
      "provider_record": "audio/runs/01-v01/provider.json",
      "cleanup": {
        "filter": "silenceremove",
        "raw_duration_seconds": 5.44,
        "clean_duration_seconds": 5.12
      }
    }
  ]
}
```

预置音色时使用 `model=mimo-v2.5-tts`、`mode=preset`、`voice=<Voice ID>`、`voice_reference=null`，每镜 `voice_reference_sha256=null`。不在 manifest 或 provider record 中保存参考音频 Base64。

## 6.1 sample review

视觉、运动、声音各有一个阶段内样片 review：

```json
{
  "schema_version": "1.0",
  "gate": "sample",
  "stage": "audio",
  "scene_id": "01",
  "sample_entry_sha256": "...",
  "self_review": {"status": "passed", "checks": []},
  "human_review": {
    "status": "approved",
    "reviewer": "human",
    "approved_at": "ISO-8601",
    "note": "用户原话"
  },
  "approved_artifacts": [
    {"path": "audio/01-hook.wav", "bytes": 12345, "sha256": "..."}
  ]
}
```

样片 review 只解锁同层剩余镜头，不能解锁下一阶段；全量完成后仍需正常阶段 review。

## 7. timing.json

```json
{
  "schema_version": "1.0",
  "timebase": "audio",
  "transition": {
    "mode": "transition-separated",
    "duration_seconds": 1.0
  },
  "scenes": [
    {
      "id": "01",
      "start": 0.0,
      "end": 5.12,
      "audio_duration": 5.12,
      "raw_video_duration": 7.04,
      "video_setpts_factor": 0.727273,
      "aligned_video": "composition/aligned/01-hook.mp4",
      "captions": [
        {"text": "为什么很多人一赚钱就卖", "start": 0.0, "end": 2.55},
        {"text": "一亏钱却死扛？", "start": 2.55, "end": 5.12}
      ]
    }
  ],
  "total_duration": 5.12
}
```

字幕文本禁止包含换行。

动画转场存在时，`timing.json` 还必须记录每个转场的 `start`、`midpoint`、`end` 与相邻台词 ID。独立转场默认 `end - start = 1.0` 秒；上一句结束与下一句开始都等于 `midpoint`。用户要求无字幕时，`captions` 使用空数组且合成时不烧录字幕。

## 8. review

```json
{
  "schema_version": "1.0",
  "stage": "visual",
  "validated_at": "ISO-8601",
  "self_review": {
    "status": "passed",
    "checks": [{"name": "all_frames_present", "passed": true, "detail": ""}]
  },
  "human_review": {
    "status": "approved",
    "reviewer": "human",
    "approved_at": "ISO-8601",
    "note": "用户确认全部静帧"
  },
  "approved_artifacts": [
    {"path": "visual/01-end.png", "bytes": 123, "sha256": "..."}
  ]
}
```

`full-auto` 模式保留相同的 `self_review` 与 `approved_artifacts`，但使用：

```json
{
  "approval_mode": "full-auto",
  "human_review": {"status": "skipped"},
  "automation_review": {
    "status": "completed",
    "completed_at": "ISO-8601",
    "authorization_note": "用户明确要求的原话"
  }
}
```
