# Vox Style（Vox 风格）

风格 ID：`vox`
版本：`2.0`
运动策略：`content-to-completed-keyframes`

对用户展示的风格名称固定为“Vox 风格”。下文列出的题材只是适用范围，不是风格名称。

## 目录

1. 适用范围
2. 视觉签名
3. 隐喻与元素
4. 色彩
5. 构图与材质
6. 首尾帧
7. 图像提示词
8. Agnes 动作提示词
9. QA
10. 常见失败

## 1. 适用范围

适合：

- 抽象概念、经济机制、认知偏差和观点解释；
- 需要把因果关系压成一个视觉命题的短镜头；
- 固定机位、逐件组装、落位后近乎静止的讲解动画。

不适合：

- 真实产品广告、写实人物表演或口型同步；
- 精确复杂遮挡、镜头穿越或连续空间叙事；
- 依赖可读长文字、真实软件界面或数据表格的内容。

## 2. 视觉签名

- 强烈、平坦、均匀的纸张色场；
- 黑白半调人物或物体作为视觉骨架；
- 彩色卡纸只用于信息层级；
- 清晰裁切边和暖奶油白 keyline；
- 低透明度、方向一致的柔和纸片阴影；
- 细微未涂布纸纤维；
- 固定机位、编辑海报式构图；
- 无 logo、水印、UI、glossy 3D 或写实房间。

同一视频统一半调密度、纸张颗粒、描边宽度和阴影方向。背景色可以随语义变化，但不要让相邻镜头像来自不同系列。

## 3. 隐喻与元素

每镜只表达一个关系：

```text
主体 A
→ 通过一个动作
→ 改变主体 B
→ 得到可见结果
```

保留 3–6 个大组。一个“人群”“店铺链”或“信封序列”可以作为一组；不要把每个小零件都算作独立元素。

优先使用：

- 容器：储蓄罐、漏斗、档案盒；
- 连接：桥、管道、纸带、齿轮；
- 变化：缩小、收窄、分叉、锁住、点亮；
- 循环：轮盘、轨道、链条；
- 对照：一个个体与一个网络、投入与结果。

不要把抽象词做成大字。文字只能出现在最终字幕层，不进入静帧。

## 4. 色彩

按语义选强色场：

- 焦橙或红：时间消耗、劳动、紧迫、风险；
- 芥末黄：警示、工具、经验漏失、关键节点；
- 墨绿：判断、修复、成长、系统重置；
- 深紫：制度、记忆、长期、反思；
- 青绿：协作、机会、连接、自动执行；
- 奶油白：中性结构、连接件、信封和纸张边缘。

每镜使用一个主背景和 2–4 个点色。彩色纸张服务信息层级，不为了“热闹”增加颜色。

## 5. 构图与材质

- 默认横屏 16:9；
- 主体集中在中部约 70%；
- 底部 15–18% 保持安静，给单行字幕；
- 使用 3–6 个可分离大组；
- 保留明显负空间，方便新增纸片进入并保持构图清晰；
- 人脸、手和身体结构自然；
- 禁止可读字母、数字、货币符号、随机标牌和品牌；
- 阴影只用于纸片层级，不制造真实景深。

## 6. 首尾帧

尾帧是视觉真相：

- 它必须完整表达隐喻；
- 所有最终元素、位置、比例和颜色都在尾帧确定；
- 动画模型不得自由改造尾帧。

首帧默认：

- 必须是有内容的独立关键帧，不能是纯色空纸面；
- 呈现冲突发生前、因果链启动前或变化尚未完成的初始状态；
- 至少保留一个可识别的主体、环境或关系组，让观众第一眼就进入叙事；
- 与尾帧保持背景、材质、主体身份、比例和构图锚点一致；
- 与尾帧存在明确但克制的状态差异，为运动提供可执行路径；
- 每个独立内容状态单独设计；只有 motion plan 明确把同一边界状态作为前一任务尾帧和后一任务首帧时，才复用同一个文件。

## 7. 图像提示词

每镜分别写自包含的 `first_frame_prompt` 和尾帧 `image_prompt`。两条提示词都要完整复述相同的风格、背景、主体身份、构图锚点和禁止项，不能依赖 “same as the other frame”。

首帧提示词至少说明：

```text
Use case: educational explainer animation.
Asset type: content-rich first keyframe for a locked 16:9 shot.

Create an editorial halftone paper-collage image showing the meaningful
initial state before the change: [initial visual proposition]. The frame
must already contain [recognizable subject/environment/relationship groups]
and must not be an empty or background-only image.

Backdrop, style, composition, materials and structural constraints:
[repeat the complete shared visual specification].
Avoid: typography, readable letters, numerals, logos, watermark, UI,
subtitles, glossy 3D, photoreal environment, clutter and empty composition.
```

尾帧提示词至少说明：

```text
Use case: educational explainer animation.
Asset type: completed last keyframe for a locked 16:9 shot.

Create a finished editorial halftone paper-collage image that makes this
relationship immediately readable without text: [visual proposition].

Backdrop: perfectly flat [color and hex] paper field with subtle uncoated
paper fiber.
Style: black-and-white halftone photographic cut-outs with selective
[accent colors] cardstock.
Composition: locked 16:9 editorial poster frame, subject in the middle
70 percent, lower 16 percent visually quiet, only 3–6 large separable
paper groups.
Materials: visible halftone dots, crisp cut edges, thin warm-cream
keylines and soft low-opacity physical shadows.
Structural constraints: [exact relationship and anatomy constraints].
Avoid: typography, readable letters, numerals, logos, watermark, UI,
subtitles, glossy 3D, photoreal environment and clutter.
```

两张关键帧都必须有内容且视觉可区分。不要依赖上一镜或另一张关键帧提示词中的“same style”。

## 8. Agnes 动作提示词

动作的目标是“从有内容的初始状态克制地变化到确认尾帧”，不是从空纸面开场，也不是让完成画面持续漂移。

默认顺序：

```text
已有主体保持稳定
→ 新的关键卡片或关系进入
→ 连接件
→ 因果动作
→ 最终结果
```

每镜英文提示词必须包含：

```text
Use Image 1 as the exact first frame and Image 2 as the exact completed
last frame. Lock the 16:9 camera, background, framing, palette, paper
texture, faces, hands and object shapes.

Preserve the meaningful content already visible in Image 1. Introduce or
transform only the paper groups explicitly defined by the two keyframes in
this order: [ordered actions].
Use slow controlled paper timing. Slide pieces in or scale them gently
from 94% to 100%, with less than 16 pixels of settling travel and no
elastic bounce. Complete assembly in the first 55–65% of the clip.
Then hold the supplied final composition with only one very slow 0.5%
breathing pulse.

No scene cut, no camera movement, no zoom, no morphing, no new object,
no extra fingers, no face or hand deformation, no text mutation, no
lighting change and no sound. End on Image 2.
```

节奏要求：

- 纸片出场要让观众看清，不使用快速弹射；
- 背景始终静止；
- 元素落位后不再大幅移动；
- 呼吸速度慢、幅度低，整镜最多一次明显呼吸；
- 动作顺序来自因果关系，不使用通用漂浮或镜头推进。

## 9. QA

静帧：

- 隐喻是否不用字幕也能大致看懂；
- 首帧是否已经包含可识别的叙事内容，而不是纯色或背景纹理；
- 首帧和尾帧是否视觉可区分且主体身份、构图锚点一致；
- 是否只有 3–6 个大组；
- 主体是否集中，字幕安全区是否安静；
- 人脸、手、肢体和物件结构是否自然；
- 是否出现假字、数字、logo、水印或 UI；
- 是否保留足够负空间供新增元素克制进入。

动画：

- 实际首帧是否接近确认首帧；
- 是否逐件进入，而不是整画面淡入；
- 背景和机位是否锁定；
- 是否没有新增物件、假字和结构变形；
- 出场是否克制且无快速弹性；
- 落位后是否基本静止，只保留极慢呼吸；
- 实际尾帧是否接近确认尾帧。

## 10. 常见失败

- 画面像关键词拼盘：回到一句视觉命题，删到 3–6 组。
- 抽象概念变成大字：改用容器、连接、变化或循环关系。
- 首帧为空白或只有背景：加入冲突前的主体、环境或初始关系。
- 首尾帧像两个不同场景：固定主体身份、背景、比例和构图锚点，只改变叙事状态。
- 整体漂移：强化锁定背景和逐件进入顺序。
- 出场过快、弹性过强：要求 slow controlled timing 和 no elastic bounce。
- 呼吸太快：要求全镜最多一次、幅度约 0.5%。
- 手部或结构错误：回到视觉层重生尾帧，不用动作提示词修补。
- 尾帧漂移：减少复杂动作，并强化 Image 2 是精确最终帧。
