# Storybook Style（彩色纸雕绘本风格）

风格 ID：`storybook`
版本：`1.0`
运动策略：`same-frame-breathing-keyframes`
关键帧策略：`shared-hero-frame`

对用户展示的风格名称固定为“storybook”。

## 目录

1. 适用范围
2. 视觉签名
3. 隐喻与元素
4. 色彩、构图与材质
5. 共享主画面
6. 图像提示词
7. Agnes 动作提示词
8. QA
9. 常见失败

## 1. 适用范围

适合：

- 用生活化场景解释经济、心理、社会和儿童认知概念；
- 需要温暖、友好、低认知负担的讲解动画；
- 固定构图、贴纸人物慢速出场、落位后低频呼吸的短镜头。

不适合：

- 依赖复杂角色表演、口型同步或连续空间调度的故事；
- 需要镜头穿越、快速追逐、写实物理或精密机械运动的内容；
- 依赖画内长文字、真实软件界面或数据表格的解释。

## 2. 视觉签名

- 彩色、温暖的手工纸雕绘本场景；
- 前景人物和关键物体呈贴纸造型，带暖米白色裁切描边；
- 清晰的纸层、裁切边、轻微纸张纤维和方向一致的柔和阴影；
- 人物造型简洁友好，面部清晰，四肢和双手自然；
- 建筑、树木、家具等背景以分层纸片搭成小型舞台；
- 色彩柔和但有清楚的前景、中景、背景层级；
- 固定机位、平视或轻微俯视的故事书构图；
- 无 logo、水印、UI、glossy 3D、照片拼贴或写实材质。

同一视频统一纸张颗粒、描边宽度、阴影方向、人物比例和色彩温度。背景可以随场景变化，但必须像同一本绘本中的连续页面。

## 3. 隐喻与元素

每镜建立一个一眼可读的生活化情境：

```text
一个具体人物或群体
→ 面对一个可见选择、关系或变化
→ 呈现概念的结果
```

每镜保留 3–7 个大组。优先使用家庭、商店、村庄、道路、花园、储蓄罐、篮子、桥梁和队伍等儿童也能理解的场景。抽象概念必须落到人物、物件和空间关系上，不把术语做成画面中的大字。

## 4. 色彩、构图与材质

- 默认横屏 16:9，1280×720；
- 主体集中在中部约 70%，人物脚下有明确落点；
- 底部 15–18% 保持安静，供单行字幕使用；
- 使用奶油白、暖黄、砖红、柔和蓝绿、橄榄绿等低刺激配色；
- 关键人物与背景保持足够明度或色相对比；
- 纸张纤维细微可见，阴影柔和且方向统一；
- 禁止可读字母、数字、货币符号、随机招牌、品牌、字幕和水印；
- 不用景深模糊、霓虹光、塑料高光或写实摄影照明。

## 5. 共享主画面

每个内容场景只生成一张权威主画面（hero frame）：

- 主画面已经包含完整人物、背景、物件和最终空间关系；
- `first_frame_prompt` 与 `image_prompt` 必须描述同一完整画面，建议使用完全相同的英文文本；
- 视觉层只调用一次图片模型；
- 同一个规范化文件同时登记为首帧和尾帧；
- Agnes 仍接收两个关键帧输入，但两者使用同一张主画面；
- 不要为了满足双关键帧接口重复生成相同图片。

这一策略的目的不是制造状态变化，而是锁死人物身份和构图，让视频模型只执行克制的贴纸入场与呼吸。跨场转场仍按 `state/motion-plan.json` 复用相邻场景的主画面；若要最接近安静绘本效果，优先选择 `hard-cut`。

## 6. 图像提示词

每镜写一条自包含的英文主画面提示词，并把它同时写入 `first_frame_prompt` 与 `image_prompt`：

```text
Use case: friendly educational explainer animation.
Asset type: authoritative hero frame for a locked 16:9 storybook shot.

Create a warm tactile layered cut-paper storybook diorama showing:
[one concrete visual proposition]. Include [3–7 large readable groups]
already arranged in their final positions.

Style: colorful handcrafted paper layers, visible fine paper fibers,
clean cut edges, warm off-white sticker outlines around foreground
characters, and soft low-opacity physical paper shadows with one
consistent direction.
Composition: fixed 16:9 camera, readable center grouping, clear feet and
hands, stable spatial relationships, and a visually quiet lower 16 percent
for one-line captions.
Palette: [warm restrained palette and semantic accent colors].
Avoid: typography, readable letters, numerals, currency symbols, signs,
logos, watermark, UI, subtitles, photorealism, glossy 3D, plastic texture,
clutter, malformed hands, extra limbs and empty composition.
```

提示词必须完整描述单张主画面，不能描述“之后才出现”的物体，也不能依赖上一镜。

## 7. Agnes 动作提示词

每镜使用以下动作骨架，再补充当前场景中哪些前景纸片属于呼吸主体：

```text
Use the supplied first and last frames as strict composition references.
They are the same authoritative hero frame. Preserve the exact characters,
objects, colors, silhouettes, facial features, background layout, and
spatial relationships.

The camera and background remain completely locked.

During the first 1.2 seconds, the designated foreground paper-sticker
characters gently scale from 96 percent to 100 percent around their own
center points. Use a soft ease-out without overshoot or elastic bounce.

After the entrance, every character remains fixed at the exact original
position. Apply only extremely subtle breathing: scale slowly between
100 percent and 101.5 percent over a four-second cycle. Do not move the
feet, hands, faces, objects, or background.

No camera movement, no zoom, no pan, no parallax, no translation, no new
objects, no disappearing objects, no morphing, no lip movement, no limb
deformation, no text changes, no lighting change, no scene transition and
no sound. End on the supplied hero frame.
```

负面动作约束：

```text
camera movement, zoom, pan, parallax, large translation, rapid bouncing,
elastic overshoot, object morphing, new objects, disappearing objects,
limb distortion, malformed hands, face deformation, lip movement,
text appearing, text mutation, lighting change, scene transition
```

动作节奏：

- 入场约 1.2 秒，不使用快速弹射；
- 背景、机位和物件始终静止；
- 人物落位后不平移，只保留极慢且低幅的整体呼吸；
- 一镜最多一个明显呼吸周期；
- 不让手脚、五官或单个身体部位独立缩放。

## 8. QA

静帧：

- 是否像同一本温暖的手工纸雕绘本；
- 隐喻是否不看字幕也能大致理解；
- 是否只有 3–7 个大组，主体层级清楚；
- 人物手、脸、四肢是否自然，脚下是否有稳定落点；
- 是否没有假字、数字、logo、水印或 UI；
- 底部字幕安全区是否安静；
- manifest 的首帧和尾帧是否指向同一文件且哈希相同。

动画：

- 实际首尾画面是否接近确认主画面；
- 背景、机位、人物身份和空间关系是否锁定；
- 出场是否约 1.2 秒、无弹性过冲；
- 是否没有位置漂移、手脚乱动、口型和结构变形；
- 呼吸是否约四秒一周期、幅度不超过 1.5%；
- 是否没有新增或消失物件、文字变化和跨场变化。

## 9. 常见失败

- 背景跟着呼吸：只指定前景贴纸人物为呼吸主体，并重复锁定背景。
- 人物缓慢漂移：明确 `fixed at the exact original position`，禁止 translation 和 parallax。
- 出场弹性太快：固定 1.2 秒 soft ease-out，并禁止 overshoot、bounce。
- 呼吸频率过快：明确四秒一个周期，一镜最多一个明显周期。
- 手脚和五官变形：呼吸必须作用于整个人物贴纸，不允许身体局部独立运动。
- 首尾画面漂移：确认两项输入引用同一个本地文件和同一个哈希。
