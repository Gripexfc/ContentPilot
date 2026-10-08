# 文章生成系统核对与当前契约

日期：2026-10-01（Asia/Shanghai）  
本文件描述当前离线生成边界和后续可替换接口；不把模板输出称为真实 LLM 生成。

## 当前链路

```text
theme/url/notes/file/hotspot
  → task_inputs（原文、元数据、sha、解析状态）
  → brief（读者问题、作者角度、事实/来源/缺口、平台计划）
  → 用户确认
  → demo_deterministic（公众号、小红书、抖音各自字段）
  → artifact_revision（画像/简报/来源/记忆引用）
  → 用户编辑 → edit_event → proposed memory
```

`creatoros/adapters/demo_content.py` 是唯一当前生成入口。它不联网、不读取凭据、不声称亲测，输出 `generation_kind=demo_deterministic`。三平台字段分别包含：

- 公众号：标题候选、标题、摘要、分段正文、事实引用、首图/配图说明、自然结尾策略。
- 小红书：标题候选、封面文案、分页卡片、正文、话题、图片提示词。
- 抖音：标题、3 秒开场、口播、分镜、字幕、B-roll、声音/音乐建议和“未渲染视频”说明。

## 事实与发布边界

链接、文件和热点目前只保存输入或手动证据；生成的 `facts`/`fact_citations` 为空或待核验，不可升级为已核验来源。模板回退可用于体验流程，不能作为 LLM 质量、平台效果、真人表达门禁或已发布证明。公众号本地草稿的 Mock 提交也只更新本地状态。

## 下一步适配器契约

后续 `LLMAdapter` 至少需要接收：任务、已确认简报、画像版本、允许检索的确认记忆、来源账本和平台目标；返回平台内容、模型标识、Prompt 版本、输入/输出摘要、耗时、失败原因和可重试标志。每次尝试写入 `generation_jobs`，失败重试不能覆盖旧 revision；没有凭据时明确返回 `not_configured`，再决定是否使用 `template_fallback`。

质量门禁、参考—原创映射、朱雀回执和平台发布包属于生成后的独立阶段，不能由 adapter 自评通过。
