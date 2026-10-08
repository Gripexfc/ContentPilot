# 数据模型与 API 契约草案

这是 S2/S3/S4a/S4b/S4c 及连接器、公众号草稿切片的实现契约。字段可扩展，但已命名的溯源字段不能删除或改成隐式字符串。当前已实际开放简报修订、平台 revision 历史、能力记忆决策、任务状态转换、热点手动入池、热点入任务、输入资产、CSV/JSON 指标导入、产物导出、Mock Connector 状态和公众号本地草稿接口；RSS/官方采集、真实平台 API、分析快照仍是后续实现边界。

## 1. 通用约定

- id：UUID 字符串；时间：UTC ISO 8601，展示时转 Asia/Shanghai。
- 所有实体含 `created_at`、`updated_at`；观察数据另含 `observed_at`。
- `status` 用枚举；未知/不可用用 `null` 和 `status` 表达，不以空字符串冒充成功。
- 写 API 返回实体或 `{data, trace}`；长任务返回 202 `{job_id, status_url}`。
- 错误统一为 `{error:{code,message,field?,retryable?,details?}, request_id}`，不返回秘密或上游原始 Cookie。

## 2. 核心表

### creator_profiles / creator_profile_versions

`creator_profiles` 是稳定身份；`creator_profile_versions` 是不可变快照。快照 JSON 使用结构化 schema，但在表中保留 `schema_version`。

```text
creator_profiles(id, name, current_version_id, created_at, updated_at)
creator_profile_versions(
  id, profile_id, version_no, parent_version_id, snapshot_json,
  change_summary, confirmation_status, confirmed_at, created_at
)
```

snapshot 包含 identity、experience、domains、pillars、readers、voice、boundaries、platforms、goals、evidence_refs。建议对象有 `suggestion_id`、diff、reason、status，不直接写 current。

### assets / sources / claims / claim_evidence

```text
assets(id, storage_key, original_name, mime, bytes, sha256, kind, rights_status, created_at)
sources(id, task_id?, asset_id?, source_type, url, title, publisher, published_at?, fetched_at?, raw_ref?, status, error_code?)
claims(id, task_id, text, claim_type, status, created_at)
claim_evidence(id, claim_id, source_id, locator?, quote?, verification_status, checked_by, checked_at?)
```

网页/文件原件只保存到 data/assets；数据库保存摘要、哈希和引用定位。原始来源不可访问时 source 为 `unverified`，不会被引用为已核验事实。

### content_tasks / briefs / task_events

```text
content_tasks(id, profile_version_id, title, status, reader_problem, author_angle,
              created_at, updated_at, archived_at?)
task_inputs(id, task_id, input_type, text?, metadata_json, parse_status)
task_events(id, task_id, event_type, from_status?, to_status?, actor, payload_json, created_at)
briefs(id, task_id, version_no, payload_json, confirmation_status, created_at)
```

brief payload 固定保存事实核、读者问题、作者观点、待验证、平台计划、研究缺口、参考到原创映射和使用的 memory ids。

### platform_artifacts / artifact_revisions / edit_events

```text
platform_artifacts(id, task_id, platform, status, current_revision_id?, error_code?, created_at, updated_at)
artifact_revisions(id, artifact_id, revision_no, parent_revision_id, content_json,
                   profile_version_id, brief_id, source_ids_json, memory_ids_json,
                   generation_job_id?, editor, created_at)
edit_events(id, artifact_revision_id, path, before_json, after_json, reason?, actor, created_at)
```

platform 必须为 `wechat / xiaohongshu / douyin`；content_json 分别符合平台契约。每个 revision 保存实际使用的画像、简报、来源和记忆快照引用。

### hotspots / hotspot_evidence

```text
hotspots(id, title, canonical_url, source_name, source_kind, published_at?, fetched_at,
         summary, fact_status, heat_status, relevance_score?, relevance_reason,
         platform_fit_json, needs_human_review, created_at)
hotspot_evidence(id, hotspot_id, evidence_type, source_id, claim, value_json, checked_at?)
```

### metric_imports / metric_observations / analyses / experiments

```text
metric_imports(id, platform, source_type, file_asset_id?, connector_id?, imported_at,
               observed_at, mapping_json, status, error_json?)
metric_observations(id, import_id, account_ref, content_ref?, published_at?, content_type?,
                    pillar?, title_ref?, hook_ref?, metrics_json, unit_json, source_ref,
                    observed_at, row_hash)
analyses(id, scope_json, sample_size, time_window_json, methodology, result_json,
         limitations_json, created_at)
experiments(id, hypothesis, variable, control?, target_metric, planned_window?,
            result_json?, status, created_at)
```

metrics_json 允许 null；必须同时保存单位和数据来源。row_hash 用于去重但不覆盖原始导入。

### memories / memory_events / jobs

```text
memories(id, kind, statement, source_event_id, confidence, scope_json,
         confirmation_status, confirmed_at?, revoked_at?, created_at)
memory_events(id, memory_id, action, before_json?, after_json?, actor, created_at)
jobs(id, kind, entity_type, entity_id, adapter, status, attempt_count, next_retry_at?,
     error_code?, error_message?, created_at, finished_at?)
job_attempts(id, job_id, attempt_no, started_at, finished_at?, status, request_meta_json,
             result_ref?, error_code?, error_message?)
```

`request_meta_json` 只保留非敏感摘要；适配器不得写 token、Cookie、二维码或全文私密正文。

### connector_states / connector_events / wechat_drafts

```text
connector_states(id, connector_key, platform, label, adapter_kind, state,
                 last_operation, last_error_code?, last_error?, updated_at)
connector_events(id, connector_key, operation, from_state?, to_state,
                 success, error_code?, created_at)
wechat_drafts(id, title, digest, author, content_html, cover_path?, status,
              submitted_at?, publish_error?, created_at, updated_at)
wechat_draft_events(id, draft_id, operation, from_status?, to_status,
                    success, error?, created_at)
```

Mock Connector 的状态顺序为 `not_configured → configured → connecting → connected → read_succeeded → submit_succeeded`；失败保留 `failed` 和错误码。`wechat_drafts` 的提交只允许用户触发，并要求 `wechat-oa` 先读取成功；本地成功不等于真实公众号草稿箱成功。

## 3. 平台内容 DTO

公众号 DTO：`title_candidates[]`, `title`, `summary`, `sections[]`, `fact_citations[]`, `cover_brief`, `body_image_briefs[]`, `ending_policy`（默认 natural）。

小红书 DTO：`title_candidates[]`, `cover_copy`, `cards[]`, `body`, `topics[]`, `image_prompts[]`。

抖音 DTO：`title`, `hook_3s`, `voiceover`, `shots[]`（time/start/end/visual/audio/dialogue/subtitle/broll_refs）、`subtitle`, `voice_and_music`, `render_plan?`。

DTO 校验平台字段和引用存在；不能保证创作质量。三份 DTO 的 canonical body hash 不得全部相同；重复时 job 失败并要求重新适配。

## 4. API 草案

### 画像

`GET /api/v1/profile`、`GET /api/v1/profile/versions`、`POST /api/v1/profile/draft`、`POST /api/v1/profile/versions`、`GET /api/v1/profile/versions/{id}/diff/{other_id}`、`POST /api/v1/profile/restore/{id}`、`POST /api/v1/profile/suggestions/{id}/accept`、`POST /api/v1/profile/suggestions/{id}/reject`。

### 任务与生成

`POST /api/v1/tasks`、`GET /api/v1/tasks`、`GET /api/v1/tasks/{id}`、`POST /api/v1/tasks/{id}/inputs`、`POST /api/v1/tasks/{id}/research`、`POST /api/v1/tasks/{id}/briefs`、`POST /api/v1/tasks/{id}/briefs/{brief_id}/confirm`、`POST /api/v1/tasks/{id}/generate`、`GET /api/v1/jobs/{id}`。

`POST /api/v1/artifacts/{id}/revisions` 保存用户修改，`POST /api/v1/artifacts/{id}/status` 做显式审核状态转换，`GET /api/v1/tasks/{id}/trace` 返回画像/来源/记忆/作业链。

### 热点、指标、记忆与导出

`POST /api/v1/hotspots`、`GET /api/v1/hotspots`、`POST /api/v1/hotspots/{id}/task`、`POST /api/v1/metrics/imports`、`GET /api/v1/metrics/imports`、`POST /api/v1/metrics/imports/{id}/inclusion`、`GET /api/v1/metrics/summary`、`POST /api/v1/memories/{id}/decisions`、`GET /api/v1/artifacts/{id}/export?format=markdown|json|html`。

原始文件由 `POST /api/v1/tasks/{id}/inputs/file` 写入 `data/assets/tasks/{task_id}`，文件名只作为元数据，路径使用服务生成的随机前缀；`GET /api/v1/inputs/{input_id}/download` 只允许回读该目录内仍存在的文件。

连接器接口只新增用户触发的命令：`GET /api/v1/connectors`、`POST /api/v1/connectors/{id}/configure`、`POST /api/v1/connectors/{id}/connect`、`POST /api/v1/connectors/{id}/read`、`POST /api/v1/connectors/{id}/submit`。默认是 Mock；`CREATOROS_WECHAT_ADAPTER=browser` 时微信公众号连接器会启动持久化 Playwright 登录会话，返回 `connecting / expired / failed` 等可恢复状态，未通过会话核验不会返回真实连接成功。`GET /api/v1/analytics/wechat` 只在 browser 模式读取公众号后台数据，Mock 模式明确返回未启用错误。

公众号草稿接口：`GET/POST /api/v1/drafts`、`GET/PATCH /api/v1/drafts/{id}`、`POST/GET /api/v1/drafts/{id}/cover`、`POST /api/v1/drafts/{id}/submit`。提交失败写回 `publish_error` 并新增事件，前端立即回读失败状态；Mock 与 browser 适配器分层，browser 成功时保存 `remote_id` 和非敏感提交回执，重试不覆盖旧错误，已提交草稿不会重复调用上游。

## 5. 版本与冲突规则

更新画像/产物时客户端带 `base_version_id` 或 `parent_revision_id`。已变更则 409，返回当前版本和可比较的差异；服务不静默覆盖。回滚是 restore 事件 + 新版本，因而所有任务仍能关联当时使用的快照。
