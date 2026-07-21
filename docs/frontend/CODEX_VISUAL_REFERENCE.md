# Codex-inspired 公开视觉参考

本文件只记录公开资料和视觉推断，不代表 OpenAI 官方设计 Token。前端产品名为“能源诊断”，不使用 OpenAI/Codex 商标、Logo、字体文件、私有图标或截图资产。

## 公开来源

- [Introducing the Codex app](https://openai.com/index/introducing-the-codex-app/)：官方将 App 描述为管理多个 agent 的 command center，任务以 project/thread 组织，执行、变更审查和后续协作在 thread 内完成。
- [Introducing Codex](https://openai.com/index/introducing-codex/)：公开产品截图和说明强调任务列表、实时进度、可验证证据、测试输出和人工 review。
- [Codex developer documentation](https://developers.openai.com/codex/)：用于核对任务、线程、审查和多端产品表述。

## 布局观察

- 主体是任务/线程工作区，不是传统顶部导航的 KPI 后台。
- 左侧区域承担任务切换；中间区域承载连续线程；检查或变更详情作为邻接面板出现。
- 信息组织主要依靠细分隔线、留白、字体层级和选中底色，独立浮起 Card 较少。
- 进度、工具输出和最终结果自然出现在同一工作流上下文中。

以上观察映射为：桌面三栏、平板两栏加 Inspector overlay、手机单栏顺序导航。右侧 Inspector 是能源诊断所需的 Evidence、Time Series、Tools、Trace，不复制 Codex 的代码 diff 语义。

## 字号与密度观察

- 正文采用接近系统 UI 的紧凑字号；标题只做轻量放大，不使用营销型大标题。
- 列表行保持可扫描密度，同时为状态、更新时间和辅助标识保留一行信息。
- ID、trace 和 run 使用等宽字体；长 ID 默认截断并允许复制。

实现中的具体字号是基于公开截图的中等置信度视觉推断，并按中文可读性调整。

## 面板比例推断

- 大屏左栏约 264–288px，中栏占剩余主要空间，右栏约 360–420px。
- 中等桌面左栏收窄到约 240px，Inspector 收窄到约 320px。
- 低于 1100px 时 Inspector 变 overlay；低于 768px 时不压缩三栏，改为单栏。

这些比例来自跨截图的视觉测量与 Phase 7 产品约束，未声称为官方数值。

## 颜色与材质推断

- 内容面板接近中性白/深灰，画布略有明度差。
- 边框低对比、阴影极弱，选中态以轻微灰阶面强调。
- 产品内仅风险、运行、完成、警告和错误使用少量语义色。
- 官方发布页的彩色营销背景不属于产品工作区语言，因此未采用。

## 响应式推断

公开资料确认 Codex 覆盖桌面与移动端，但没有公开完整断点和尺寸 Token。本项目的断点、Drawer 行为和 200% 缩放策略依据 Phase 7 要求重建，属于产品适配决策。

## 不确定项

- 官方实际字体名称、字重映射和字距未从公开资料确认；使用合法系统字体替代。
- 官方阴影、圆角、边框透明度与动画曲线未公开；实现值均记录在 `frontend/design-system/token-provenance.json`。
- 未推断或复制任何私有图标、内部组件名、Logo 安全区或品牌资产。
