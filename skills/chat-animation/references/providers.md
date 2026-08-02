# Provider 配置与可替换路线

## 目录

1. 凭据
2. Agnes
3. Xiaomi MiMo
4. 图像层替换
5. 合成层替换
6. 安全与恢复

## 1. 凭据

首次使用需要两个 key：

### Agnes

国际站与 CN 站账号、API Key 和请求域名彼此独立。选择其中一套：

```bash
# 国际站
export CHAT_ANIMATION_AGNES_REGION="global"
export AGNES_GLOBAL_API_KEY="<global-key>"

# 或 CN 站
export CHAT_ANIMATION_AGNES_REGION="cn"
export AGNES_CN_API_KEY="<cn-key>"
```

国际站在 <https://platform.agnes-ai.com> 创建 Key；CN 站在 <https://platform.agnes-ai.cn> 创建 Key。旧的 `AGNES_API_KEY`、`AGNES_API_TOKEN`、`APIHUB_AGNES_API_KEY` 继续作为国际站兼容别名。

初始化可用 `--agnes-region global|cn` 显式选择。未显式选择时：只有 CN Key 可用则自动使用 `cn`，只有国际站 Key 或没有 Key 时使用 `global`；两套 Key 同时存在会停止并要求明确选择。项目一旦初始化，`request.json.agnes` 会固化区域和 Base URL，后续图片、视频、轮询和恢复都读取该项目配置。

### Xiaomi MiMo

1. 打开 <https://platform.xiaomimimo.com> 并登录。
2. 在开放平台控制台创建 API key。
3. 配置：

```bash
export MIMO_API_KEY="<your-key>"
```

不要把 export 命令连同真实 key 写入项目文档、JSON、日志或聊天截图。

### macOS 长期存储

本 Skill 在环境变量缺失时，会只读查询当前用户的 macOS Keychain：

```text
service: chat-animation/AGNES_GLOBAL_API_KEY
service: chat-animation/AGNES_CN_API_KEY
service: chat-animation/MIMO_API_KEY
account: 当前 macOS 用户
```

可用 `security add-generic-password -U` 写入对应 service。脚本只把 key 保存在进程内存中，不输出到日志。设置 `CHAT_ANIMATION_DISABLE_KEYCHAIN=1` 可禁用此兜底，便于隔离测试。其他系统继续使用环境变量或系统密钥管理器。

## 2. Agnes

区域与基础地址：

```text
global → https://apihub.agnes-ai.com
cn     → https://api.agnes-ai.cn
```

全局兼容覆盖使用 `CHAT_ANIMATION_AGNES_BASE_URL`；分区覆盖使用 `CHAT_ANIMATION_AGNES_GLOBAL_BASE_URL` 或 `CHAT_ANIMATION_AGNES_CN_BASE_URL`。代码自行拼接 `/v1`，覆盖值不要带 `/v1`。

视频：

- `POST /v1/videos`
- model：`agnes-video-v2.0`
- `extra_body.mode=keyframes`
- `extra_body.image=[first_data_url, end_data_url]`
- 推荐用返回的 `video_id` 查询 `GET /agnesapi?video_id=...&model_name=agnes-video-v2.0`
- 老任务可回退 `GET /v1/videos/{task_id}`

转场任务的生产默认：

```json
{
  "model": "agnes-video-v2.0",
  "width": 1280,
  "height": 720,
  "num_frames": 169,
  "frame_rate": 24,
  "extra_body": {
    "mode": "keyframes",
    "image": ["<first-data-url>", "<end-data-url>"]
  }
}
```

`num_frames` 必须满足 `8n + 1` 且不超过 441。

内容任务不再无条件使用 169 帧。未显式指定时，适配器统计台词中的中文、英文和数字有效字符，并读取当前项目的声音时序配置：内置默认“白桦”配置使用已验证基线 `0.215 秒/字`；其他音色或语速 context 使用一次性样片的实测值或相同配置的本地缓存。随后选择 81–441 范围内最接近的合法帧数。`state/motion-plan.json` 中人工指定的 `target_duration_seconds` 优先于字数估算；命令行 `--num-frames` 优先级最高。provider request 与 motion manifest 必须记录 `duration_plan` 和 `requested_num_frames`。同一提示词若帧数变化，必须新建 provider run，不能复用旧视频。

图片兜底：

- `POST /v1/images/generations`
- model：`agnes-image-2.1-flash`
- `extra_body.response_format=url`

Agnes 图片和视频统一通过本 Skill 的 `scripts/providers.py` 调用。

## 3. Xiaomi MiMo

接口：

```text
POST https://api.xiaomimimo.com/v1/chat/completions
```

请求：

```json
{
  "model": "mimo-v2.5-tts",
  "messages": [
    {"role": "user", "content": "<可选风格指导>"},
    {"role": "assistant", "content": "<真正要合成的台词>"}
  ],
  "audio": {"format": "wav", "voice": "茉莉"}
}
```

返回音频通常位于 `choices[0].message.audio.data`，为 Base64。

用户音色克隆：

```json
{
  "model": "mimo-v2.5-tts-voiceclone",
  "messages": [
    {"role": "user", "content": "<可选风格指导>"},
    {"role": "assistant", "content": "<真正要合成的台词>"}
  ],
  "audio": {
    "format": "wav",
    "voice": "data:audio/mpeg;base64,<参考音频>"
  }
}
```

参考音频仅支持 MP3/WAV，Base64 编码前的文件不超过 10 MB。必须确认用户本人拥有或已经取得该声音的使用授权。把原样本复制到项目 `audio/reference/` 并记录 SHA-256；请求中的 Data URL 只存在于进程内存，不写入 JSON 或日志。

预置音色：

| Voice ID | 语言 | 风格 |
| --- | --- | --- |
| 冰糖 | 中文女声 | 活泼少女 |
| 茉莉 | 中文女声 | 知性、适合科普 |
| 苏打 | 中文男声 | 阳光少年 |
| 白桦 | 中文男声 | 成熟稳重 |
| Mia / Chloe | 英文女声 | 活泼 / 甜美 |
| Milo / Dean | 英文男声 | 阳光 / 稳重 |

本 skill 用 Python 标准库调用，不依赖 `openai` 包。

CLI：

```bash
# 默认白桦配置不调用校准；替换为其他预置音色时只校准一次
python3 scripts/providers.py mimo-calibrate <project> --voice 茉莉

# 用户音色首次校准
python3 scripts/providers.py mimo-calibrate <project> \
  --voice-file /path/to/authorized-reference.mp3
```

默认声音时序配置为预置音色“白桦”及 Skill 固定 context，基线约 `4.65 字/秒`。`mimo-calibrate` 的 `--voice` 与 `--voice-file` 互斥且必须二选一；默认选择有效字符最多的镜头，保存 `state/voice-timing.json`。实测配置按 model、voice 或参考音频 SHA-256、context SHA-256 缓存在当前用户的 `~/.config/chat-animation/voice-timing-profiles.json`；相同配置跨项目复用，不重复请求。最终 `mimo-tts` 未传 voice/context 时沿用项目时序配置；克隆音色仍需传 `--voice-file` 才能构造请求。未批准声音样片前，`--all` 和其他镜头会被脚本拒绝。

## 4. 内置图像层

默认只使用本 Skill 的 Agnes Image 适配器。项目风格快照的 `frame_policy` 决定图像调用：`distinct-first-end` 分别调用 `first_frame_prompt` 和尾帧 `image_prompt`，生成两张有内容且视觉可区分的关键帧；`shared-hero-frame` 只调用一次 `image_prompt` 生成权威主画面，再将同一个规范化文件登记为首帧和尾帧。硬切静态模式和融合转场按 `state/motion-plan.json` 只生成所需状态。禁止纯色空白状态帧。只有 `shared-hero-frame` 或 motion plan 明确共享同一个跨场边界状态时才复用同一文件，不为相同像素重复调用图片模型。用户明确提供或迁移已有本地首尾帧时，可以使用 `register-visual` 导入，且双关键帧任务的 `--first` 与 `--end` 都是必填项；共享主画面策略下两项应传入同一个文件。导入本地文件不是调用其他 Skill。

两种内置路线都必须写：

- 原始提示词
- provider/model
- 文件相对路径
- 尺寸
- SHA-256
- 人工视觉检查结论

## 5. 内置合成层

使用本 Skill 的 `scripts/compose.py`，通过 FFmpeg 完成音频主时钟、画面变速、无缝拼接、单行字幕和最终编码。字幕字体由初始化生成的 `state/font-selection.json` 决定：默认下载并校验得意黑，失败时使用 Windows 或 macOS 内置中文字体，完整契约见 [fonts.md](fonts.md)。

FFmpeg/FFprobe 是最终媒体处理的系统依赖，不是 Python 包。若系统缺失，预检会停止并提供安装指引。

## 6. 安全与恢复

- 请求记录永不包含 Authorization header。
- provider 记录必须保存 Agnes `region` 与 `base_url`；已有任务与项目配置不一致时停止恢复，禁止跨站查询。
- 视频提交前先写 `submission_intent`；成功后记录 ID。
- 如果提交过程中断且无法判断服务端是否已创建任务，标记 `submission_uncertain`，不要自动重复提交。
- `queued`、`in_progress` 不是失败。
- 远端已 `completed` 但 raw 或标准化 delivery 尚未落盘时仍属于可恢复状态；继续下载或标准化同一任务，禁止新建 run。
- `video_queue_full` 或 503 使用有上限的等待重试。
- 下载成功后计算 SHA-256；断点续跑先验证本地文件。
- 外部 URL 只保存在 provider 记录中，最终工程依赖本地文件。
