# 字幕字体初始化

## 默认字体

默认使用得意黑（Smiley Sans）`v2.0.1`。Skill 不携带字体二进制；`project.py init` 从官方 GitHub Release 下载固定版本，校验后写入用户缓存。

- 发布包：`smiley-sans-v2.0.1.zip`
- ZIP SHA-256：`299c0be6c960ae37361762eca76f7d0cd516615435bb96c0d4b98a1e70178a07`
- 文件：`SmileySans-Oblique.ttf`
- TTF SHA-256：`b447d7e781f08bc95c4c9f23ba71ed2b8ebb639aa7184485c71c4ca5afcd25c4`
- 许可：SIL Open Font License 1.1

缓存位置：

- macOS：`~/Library/Caches/chat-animation/fonts/smiley-sans/2.0.1/`
- Windows：`%LOCALAPPDATA%/chat-animation/fonts/smiley-sans/2.0.1/`
- 其他系统：`${XDG_CACHE_HOME:-~/.cache}/chat-animation/fonts/smiley-sans/2.0.1/`

每个项目的 `state/font-selection.json` 记录请求字体、实际字体、来源、绝对路径、版本与 SHA-256。合成时把实际字体复制到 `composition/fonts/`，让成品工程保留当次渲染依据。

## 下载失败回退

字体下载、解压或校验失败不阻断项目初始化：

1. macOS：优先苹方，若找不到对应文件则使用系统黑体，再回退到系统字体族名。
2. Windows：优先微软雅黑，再尝试黑体和宋体。
3. 其他系统：使用 `sans-serif`，建议生产环境自行安装支持中文的系统字体。

回退原因写入 `state/font-selection.json.fallback_reason`。不要静默伪装成得意黑。

## 调试开关

- `CHAT_ANIMATION_FONT_CACHE_DIR`：覆盖用户字体缓存目录。
- `CHAT_ANIMATION_DISABLE_FONT_DOWNLOAD=1`：禁止联网并直接测试系统字体回退。

这两个变量只用于调试与隔离测试；正常用户无需设置。
