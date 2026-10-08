export type Platform = "wechat" | "xiaohongshu" | "douyin";

export type PlatformProfile = { positioning: string; audience: string; format_preferences: string[]; tone: string };

export type ProfileSnapshot = {
  identity: { display_name: string; profession: string; bio: string };
  experiences: { title: string; detail: string; occurred_at?: string | null }[];
  domains: string[];
  pillars: string[];
  readers: { name: string; problems: string[] }[];
  voice: { tone: string; examples: string[] };
  boundaries: { forbidden_words: string[]; sensitive_topics: string[]; unwanted_expressions: string[] };
  platforms: Record<string, PlatformProfile>;
  content_defaults?: { positioning: string; format_preferences: string[] };
  goals: { priorities: string[] };
  evidence_refs: string[];
};

export type ProfileVersion = {
  id: string;
  profile_id: string;
  version_no: number;
  parent_version_id: string | null;
  snapshot: ProfileSnapshot;
  change_summary: string;
  confirmation_status: string;
  confirmed_at: string | null;
  created_at: string;
};

export type ProfileVersionSummary = Omit<ProfileVersion, "profile_id" | "snapshot" | "confirmed_at">;

export type ProfileResponse = {
  id: string;
  current_version_id: string;
  current_version: ProfileVersion;
};

export type ProfileDiffItem = { path: string; before: unknown; after: unknown };
export type ProfileDiff = { left_version_id: string; right_version_id: string; changes: ProfileDiffItem[] };

export type ContentTask = {
  id: string;
  quick_draft_id: string | null;
  profile_version_id: string;
  title: string;
  status: string;
  reader_problem: string;
  author_angle: string;
  created_at: string;
  updated_at: string;
  archived_at: string | null;
};

export type QuickDraft = {
  quick_draft_id: string;
  task_id: string;
  input_id: string;
  input_version: number;
  title: string;
  context: string;
  source: Record<string, unknown>;
  platform: Platform;
  mode: "文章" | "配图" | "内容+配图";
  skill: string;
  workflow_id: string | null;
  output_artifact: string | null;
  output: string;
  profile_version_id: string;
  persistence_state: "saved_input";
  content_status: "draft";
  publish_state: "not_started";
  created_at: string;
  updated_at: string;
};

export type Brief = {
  id: string;
  task_id: string;
  version_no: number;
  payload: Record<string, unknown>;
  confirmation_status: string;
  created_at: string;
};

export type ArtifactRevision = {
  id: string;
  revision_no: number;
  parent_revision_id: string | null;
  content: Record<string, unknown>;
  profile_version_id: string;
  brief_id: string;
  source_ids: string[];
  memory_ids: string[];
  generation_kind: string;
  created_at: string;
};

export type Artifact = {
  id: string;
  task_id: string;
  platform: Platform;
  status: string;
  current_revision_id: string | null;
  current_revision: ArtifactRevision | null;
  created_at: string;
  updated_at: string;
};

export type Memory = {
  id: string;
  kind: string;
  statement: string;
  source_event_id: string;
  confidence: number;
  scope: Record<string, unknown>;
  confirmation_status: string;
  confirmed_at: string | null;
  created_at: string;
};

export type ContentTaskDetail = {
  task: ContentTask;
  latest_brief: Brief | null;
  artifacts: Artifact[];
  memories: Memory[];
  inputs: { id: string; text: string; input_type: string; metadata: Record<string, unknown>; parse_status: string; created_at: string }[];
  events: { id: string; event_type: string; from_status: string; to_status: string; payload: Record<string, unknown>; created_at: string }[];
  briefs: Brief[];
};

export class ApiError extends Error {
  constructor(public status: number, message: string) { super(message); }
}

/**
 * Vite normally proxies `/api` to CreatorOS on port 8000. When it moves to a
 * fallback port such as 5175, or when a static preview serves the bundle, use
 * the local API directly so content reads do not land on the frontend server.
 */
const apiOrigin = (() => {
  const configured = import.meta.env.VITE_API_BASE_URL?.trim();
  if (configured) return configured.replace(/\/+$/, '');
  if (typeof window === 'undefined') return '';
  const { hostname, port } = window.location;
  const isLoopback = hostname === 'localhost' || hostname === '127.0.0.1' || hostname === '::1';
  return isLoopback && port && port !== '8000' ? 'http://127.0.0.1:8000' : '';
})();

export const apiUrl = (path: string) => `${apiOrigin}${path}`;

const request = async <T>(path: string, init?: RequestInit): Promise<T> => {
  // Status polling must not hang forever when the local service or gateway
  // stops responding. Callers that provide their own AbortSignal keep control
  // of the deadline; ordinary requests get a short local timeout.
  const controller = init?.signal ? null : new AbortController();
  const timeout = window.setTimeout(() => controller?.abort(), 15000);
  let response: Response;
  try {
    response = await fetch(apiUrl(path), {
      ...init,
      signal: init?.signal ?? controller?.signal,
      headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError' && !init?.signal) {
      throw new ApiError(408, '本地服务响应超时，请稍后重试。');
    }
    throw error;
  } finally {
    window.clearTimeout(timeout);
  }
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = body.detail;
    const message = Array.isArray(detail) ? detail.map((item: { loc?: string[]; msg?: string }) => `${item.loc?.slice(1).join(".")}: ${item.msg}`).join("；")
      : typeof detail === "object" && detail?.message ? detail.message : detail || "请求失败，请重试";
    throw new ApiError(response.status, String(message));
  }
  return body as T;
};

export const getProfile = () => request<ProfileResponse>("/api/v1/profile");
export const listProfileVersions = () => request<ProfileVersionSummary[]>("/api/v1/profile/versions");
export const createProfileVersion = (payload: {
  snapshot: ProfileSnapshot;
  change_summary: string;
  base_version_id?: string;
}) => request<ProfileVersion>("/api/v1/profile/versions", { method: "POST", body: JSON.stringify(payload) });
export const restoreProfileVersion = (versionId: string) =>
  request<ProfileVersion>(`/api/v1/profile/restore/${versionId}`, { method: "POST" });
export const getProfileDiff = (left: string, right: string) =>
  request<ProfileDiff>(`/api/v1/profile/versions/${left}/diff/${right}`);

export const createContentTask = (payload: { title: string; input_text: string; input_type?: "theme" | "url" | "notes" | "hotspot"; input_metadata?: Record<string, unknown> }) =>
  request<ContentTask>("/api/v1/tasks", { method: "POST", body: JSON.stringify(payload) });
export const uploadTaskFile = async (taskId: string, file: File) => {
  const response = await fetch(apiUrl(`/api/v1/tasks/${taskId}/inputs/file`), { method: "POST", headers: { "content-type": file.type || "application/octet-stream", "x-filename": encodeURIComponent(file.name) }, body: file });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new ApiError(response.status, typeof body.detail === "object" ? body.detail.message : String(body.detail || "文件上传失败"));
  return body as Record<string, unknown>;
};
export const listContentTasks = () => request<ContentTask[]>("/api/v1/tasks");
export const saveQuickDraft = (payload: {
  quick_draft_id: string; topic: string; context: string; source: Record<string, unknown>;
  platform: Platform; mode: "文章" | "配图" | "内容+配图"; skill: string; workflow_id?: string | null;
  output: string; output_artifact?: string | null;
}) => request<QuickDraft>("/api/v1/quick-drafts", { method: "POST", body: JSON.stringify(payload) });
export const listQuickDrafts = () => request<QuickDraft[]>("/api/v1/quick-drafts");
export const createBrief = (taskId: string) =>
  request<Brief>(`/api/v1/tasks/${taskId}/briefs`, { method: "POST" });
export const confirmBrief = (taskId: string, briefId: string) =>
  request<Brief>(`/api/v1/tasks/${taskId}/briefs/${briefId}/confirm`, { method: "POST" });
export const generateArtifacts = (taskId: string) =>
  request<{ task: ContentTask; artifacts: Artifact[] }>(`/api/v1/tasks/${taskId}/generate`, { method: "POST" });
export const getContentTask = (taskId: string) => request<ContentTaskDetail>(`/api/v1/tasks/${taskId}`);
export const createArtifactRevision = (artifactId: string, content: Record<string, unknown>, reason: string, baseRevisionId: string) =>
  request<Artifact>(`/api/v1/artifacts/${artifactId}/revisions`, {
    method: "POST",
    body: JSON.stringify({ content, reason, base_revision_id: baseRevisionId }),
  });
export const acceptMemory = (memoryId: string) =>
  request<Memory>(`/api/v1/memories/${memoryId}/accept`, { method: "POST" });
export const listMemories = (taskId?: string) =>
  request<Memory[]>(taskId ? `/api/v1/memories?task_id=${encodeURIComponent(taskId)}` : "/api/v1/memories");

export type BriefEdit = { base_brief_id: string; reader_problem: string; author_angle: string; facts: string[]; sources: string[]; research_gaps: string[] };
export const reviseBrief = (taskId: string, payload: BriefEdit) => request<Brief>(`/api/v1/tasks/${taskId}/brief-revisions`, { method: "POST", body: JSON.stringify(payload) });
export type HistoryRevision = ArtifactRevision & { edits: { id: string; path: string; before: unknown; after: unknown; reason: string }[] };
export const getArtifactHistory = (artifactId: string) => request<HistoryRevision[]>(`/api/v1/artifacts/${artifactId}/revisions`);
export const exportArtifact = (artifactId: string, format: "markdown" | "json" | "html") => {
  const link = document.createElement("a"); link.href = apiUrl(`/api/v1/artifacts/${artifactId}/export?format=${format}`); link.download = ""; link.click();
};
export const decideMemory = (id: string, action: "accept" | "reject" | "revoke" | "edit", statement?: string) => request<Memory>(`/api/v1/memories/${id}/decisions`, { method: "POST", body: JSON.stringify({ action, statement }) });
export const changeTaskStatus = (id: string, status: "reviewing" | "archived") => request<ContentTask>(`/api/v1/tasks/${id}/status`, { method: "POST", body: JSON.stringify({ status }) });
export const getStatus = () => request<{ name: string; data_dir: string; initialized: boolean }>("/api/v1/status");
export type Overview = {
  active_task_count: number; task_count: number; pending_memory_count: number; pending_source_count: number;
  draft_count: number; pending_draft_count: number; metric_import_count: number;
  last_metric_imported_at: string | null; read_at: string;
};
export const getOverview = () => request<Overview>("/api/v1/overview");

export type ConnectorState = {
  id: string; connector_key: string; platform: string; label: string; adapter_kind: string;
  state: "not_configured" | "configured" | "connecting" | "connected" | "read_succeeded" | "submit_succeeded" | "publish_succeeded" | "failed" | "unsupported" | "expired";
  last_operation: string | null; last_error_code: string | null; last_error: string | null; updated_at: string;
};
export const listConnectors = () => request<ConnectorState[]>("/api/v1/connectors");
export const configureConnector = (key: string) => request<ConnectorState>(`/api/v1/connectors/${key}/configure`, { method: "POST" });
export const connectConnector = (key: string) => request<ConnectorState>(`/api/v1/connectors/${key}/connect`, { method: "POST" });
export const readConnector = (key: string) => request<ConnectorState>(`/api/v1/connectors/${key}/read`, { method: "POST" });
export const submitConnector = (key: string, simulate_failure = false) => request<ConnectorState>(`/api/v1/connectors/${key}/submit`, { method: "POST", body: JSON.stringify({ simulate_failure }) });
export type WechatAnalytics = {
  platform: string; source: string; fetched_at: string; posts: number;
  notes: { title: string; url: string; cover: string; reads: number | null; likes: number | null }[];
  metrics: { label: string; value: number }[]; limitations: string[];
};
export const getWechatAnalytics = () => request<WechatAnalytics>("/api/v1/analytics/wechat");

export type WechatDraft = {
  id: string; title: string; digest: string; author: string; content_html: string; cover_path: string | null;
  cover_url: string | null; status: "writing" | "ready" | "submitted" | "failed"; submitted_at: string | null;
  publish_error: string | null; remote_id: string | null; created_at: string; updated_at: string;
  submission_receipt: Record<string, unknown> | null;
  source_task_id: string | null; source_artifact_id: string | null; source_revision_id: string | null;
};
export type WechatDraftDetail = WechatDraft & { events: { id: string; operation: string; from_status: string | null; to_status: string; success: boolean; error: string | null; created_at: string }[] };
export const listWechatDrafts = () => request<WechatDraft[]>("/api/v1/drafts");
export const getWechatDraft = (id: string) => request<WechatDraftDetail>(`/api/v1/drafts/${id}`);
export const createWechatDraft = (payload: Pick<WechatDraft, "title" | "digest" | "author" | "content_html">) => request<WechatDraft>("/api/v1/drafts", { method: "POST", body: JSON.stringify(payload) });
export const createWechatDraftFromArtifact = (artifactId: string, revisionId: string) =>
  request<WechatDraft>(`/api/v1/artifacts/${artifactId}/draft`, { method: "POST", body: JSON.stringify({ revision_id: revisionId }) });
export const updateWechatDraft = (id: string, payload: Pick<WechatDraft, "title" | "digest" | "author" | "content_html">) => request<WechatDraft>(`/api/v1/drafts/${id}`, { method: "PATCH", body: JSON.stringify(payload) });
export const copyWechatDraft = (id: string) => request<WechatDraft>(`/api/v1/drafts/${id}/copy`, { method: "POST" });
export const uploadWechatCover = async (id: string, file: File) => { const response = await fetch(apiUrl(`/api/v1/drafts/${id}/cover`), { method: "POST", headers: { "content-type": file.type || "application/octet-stream", "x-filename": encodeURIComponent(file.name) }, body: file }); const body = await response.json().catch(() => ({})); if (!response.ok) throw new ApiError(response.status, typeof body.detail === "object" ? body.detail.message : String(body.detail || "封面上传失败")); return body as WechatDraft; };
export const submitWechatDraft = (id: string, simulate_failure = false) => request<WechatDraft>(`/api/v1/drafts/${id}/submit`, { method: "POST", body: JSON.stringify({ simulate_failure }) });

export type Hotspot = {
  id: string; title: string; canonical_url: string; source_name: string; source_kind: string;
  published_at: string | null; fetched_at: string; summary: string; fact_status: string; heat_status: string;
  relevance_score: number | null; relevance_reason: string; platform_fit: Record<string, unknown>;
  needs_human_review: boolean; evidence: { id: string; evidence_type: string; source_url: string; claim: string; value: unknown; verification_status: string; checked_at: string | null }[]; created_at: string;
};
export const listHotspots = () => request<Hotspot[]>("/api/v1/hotspots");
export type TrendSourceKey = 'douyin' | 'weibo' | 'zhihu' | 'bilibili' | 'baidu' | 'toutiao';
export type TrendItem = { id: string; title: string; hot: string; url: string; rank: number; summary: string };
export type TrendBoard = {
  platform: TrendSourceKey; label: string;
  status: 'fresh' | 'cached' | 'stale' | 'unavailable';
  fetched_at: string | null; source_name: string | null; source_url: string | null;
  error: string | null; items: TrendItem[];
};
export type TrendsResponse = { trends: TrendBoard[]; refresh_after_seconds: number };
export const getTrends = (sources: TrendSourceKey[], refresh = false, signal?: AbortSignal) =>
  request<TrendsResponse>(`/api/v1/trends?platforms=${sources.join(',')}&limit=12&refresh=${refresh}`, { signal });
export const createTaskFromHotspot = (id: string) => request<ContentTask>(`/api/v1/hotspots/${id}/task`, { method: "POST" });
export const createHotspot = (payload: {
  title: string; canonical_url: string; source_name: string; source_kind: string; published_at?: string;
  summary: string; fact_status: string; heat_status: string; relevance_score?: number | null;
  relevance_reason: string; platform_fit: Record<string, unknown>; needs_human_review: boolean;
  evidence: { evidence_type: string; source_url: string; claim: string; value: Record<string, unknown>; verification_status: string }[];
}) => request<Hotspot>("/api/v1/hotspots", { method: "POST", body: JSON.stringify(payload) });
export type MetricImport = { id: string; platform: string; source_type: string; imported_at: string; observed_at: string; status: string; original_name: string; row_count: number; error: { warnings?: { row: number; message: string }[] } };
export type MetricSummary = { observation_count: number; import_count: number; by_platform: Record<string, number>; by_pillar: Record<string, number>; top_content: { title: string; platform: string; metrics: Record<string, unknown>; observed_at: string }[]; metrics_by_platform: Record<string, Record<string, { count: number; min: number; max: number; mean: number }>>; observations: { title: string; platform: string; pillar: string; published_at: string | null; observed_at: string; metrics: Record<string, unknown>; source_ref: string }[]; data_quality: { acceptance_test_imports: number; real_imports: number; excluded_imports?: number }; limitations: string[] };
export const importMetrics = (payload: { platform: string; source_type: string; observed_at: string; original_name: string; rows: Record<string, unknown>[] }) => request<MetricImport>("/api/v1/metrics/imports", { method: "POST", body: JSON.stringify(payload) });
export const listMetricImports = () => request<MetricImport[]>("/api/v1/metrics/imports");
export const getMetricSummary = () => request<MetricSummary>("/api/v1/metrics/summary");
export type PerformanceInsight = {
  platform: string; dimension: string; label: string; metric: string; metric_label: string;
  sample_count: number; average: number; account_average: number; relative_change: number;
  status: "候选" | "观察"; ready_for_use: boolean; statement: string; evidence_observation_ids: string[];
};
export type PerformanceInsights = { insights: PerformanceInsight[]; usable: PerformanceInsight[]; limitations: string[]; data_quality: Record<string, number> };
export const getPerformanceInsights = (platform?: string) =>
  request<PerformanceInsights>(`/api/v1/metrics/insights${platform ? `?platform=${encodeURIComponent(platform)}` : ""}`);

// Migrated Easel capability contracts, rendered by CreatorOS pages rather than the reference UI.
export type WorkflowStage = { label: string; status: 'pending' | 'running' | 'completed' | 'blocked' | 'failed' | 'interrupted'; reason?: string; artifact?: string; started_at?: number; finished_at?: number; duration_seconds?: number; started?: number; finished?: number; duration_ms?: number; task?: string; current_task?: string; progress?: number };
export type WorkflowDebugEvent = {
  id?: number | string;
  at?: number | string;
  timestamp?: number | string;
  time?: number | string;
  stage?: string;
  platform?: string;
  task?: string;
  action?: string;
  event?: string;
  kind?: string;
  text?: string;
  message?: string;
  status?: string;
  level?: 'info' | 'success' | 'warning' | 'error' | string;
  duration_ms?: number;
  elapsed_ms?: number;
  elapsed_seconds?: number;
  duration_seconds?: number;
  tool?: string;
  details?: Record<string, unknown>;
};
// Compact workflow composition can expose the text accumulated so far while
// the provider is still responding. Keep this envelope optional so older
// servers and legacy jobs remain valid.
export type WorkflowStreamingOutput = string | {
  content?: string;
  text?: string;
  partial?: string;
  complete?: boolean;
  done?: boolean;
  status?: string;
  updated_at?: number;
  chars?: number;
};
export type WorkflowPlatformOutput = { status: string; directory: string; skill: string; media_kind: string; artifacts: string[]; checks: unknown[]; primary_text?: string; copy_text?: string; missing?: string[] };
export type WorkflowLiveStream = WorkflowStreamingOutput & { stage?: string; platform?: string; status?: string; error?: string; chars?: number; started_at?: number; finished_at?: number };
export type WorkflowJob = { id: string; topic: string; platforms: string[]; profile: string; status: 'queued' | 'running' | 'completed' | 'blocked' | 'failed' | 'interrupted'; current: string | null; current_task?: string; created: number; attempt_started?: number; attempt?: number; updated?: number; started_at?: number; finished_at?: number; duration_seconds?: number; budget_seconds?: number; execution_mode?: 'compact' | 'legacy' | string; debug_mode?: boolean; debug_events?: WorkflowDebugEvent[]; debug_log?: WorkflowDebugEvent[]; started?: number; finished?: number; duration_ms?: number; stages: Record<string, WorkflowStage>; streaming_outputs?: Record<string, WorkflowStreamingOutput>; live_stream?: WorkflowLiveStream; content_status?: string; published?: boolean; platform_outputs?: Record<string, WorkflowPlatformOutput>; execution_receipts?: unknown[] };
export const startWorkflow = (payload: { topic: string; platforms?: string[]; profile?: string; skill?: string; output_kind?: 'standard' | 'video'; debug_mode?: boolean; revision?: { draft: string; instruction: string } }) => request<WorkflowJob>('/api/workflow/run', { method: 'POST', body: JSON.stringify({ platforms: ['xiaohongshu', 'douyin', 'wechat-oa'], ...payload }) });
export const getWorkflow = (id: string) => request<WorkflowJob>(`/api/workflow/${encodeURIComponent(id)}`);
export const retryWorkflow = (id: string) => request<WorkflowJob>(`/api/workflow/${encodeURIComponent(id)}/retry`, { method: 'POST' });
export const listWorkflows = () => request<WorkflowJob[]>('/api/workflows');
export const readOfficialOutput = (path: string) => request<{ path: string; content: string; kind: string; isBinary?: boolean }>(`/api/output/${path.split('/').map(encodeURIComponent).join('/')}`);

export type OfficialSkill = { name: string; description: string; layer: string; needsApi: boolean; apiConfigured: boolean };
export const listOfficialSkills = () => request<OfficialSkill[]>('/api/skills');
export type SkillRunResult = { response: string };
export const runSkill = (payload: { skill: string; input: string; persona?: string }, signal?: AbortSignal) => request<SkillRunResult>('/api/skill', { method: 'POST', body: JSON.stringify(payload), signal });
export type ModelRow = {
  slot: string;
  order: number;
  name: string;
  sub?: string;
  type?: string;
  model: string;
  baseUrl: string;
  keyMasked: string;
  role: string;
  result: string;
  deletable?: boolean;
};
export type ModelChannelsResponse = { channels: { chat: { rows: ModelRow[] } }; primary: string };
export type ModelSaveRow = { slot: string; name?: string; model: string; baseUrl: string; key: string; primary?: boolean };
export type ModelSelftestResult = { baseUrl: string; ok: boolean; ms: number; detail?: string };
export type ModelDiscoveryRequest = { slot: string; name?: string; model?: string; baseUrl?: string; key?: string };
export type ModelDiscoveryResponse = { models: string[]; available: boolean; source: 'remote' | 'configured' | 'unavailable' | 'none'; detail?: string };
export const getModelChannels = () => request<ModelChannelsResponse>('/api/settings/models');
export const saveModelConfig = (rows: ModelSaveRow[]) => request<ModelChannelsResponse & { ok: boolean; note?: string }>('/api/settings/models/save', { method: 'POST', body: JSON.stringify({ channel: 'chat', rows }) });
export const discoverModels = (payload: ModelDiscoveryRequest) => request<ModelDiscoveryResponse>('/api/settings/models/discover', { method: 'POST', body: JSON.stringify(payload) });
export const selftestModel = () => request<{ channel: string; results: ModelSelftestResult[]; testedAt: number }>('/api/settings/models/selftest', { method: 'POST', body: JSON.stringify({ channel: 'chat' }) });
export type ModelGatewayStatus = { configured: boolean; gatewayOnline: boolean; gatewayUrl: string; configExists: boolean; profile: string; nextStep: string };
export const getModelGatewayStatus = () => request<ModelGatewayStatus>('/api/settings/models/status');
export type OfficialOutputNode = { name: string; type: 'dir' | 'file'; path: string; kind?: string; size?: number; mtime?: number; children?: OfficialOutputNode[]; fileCount?: number; meta?: Record<string, unknown> };
export const listOfficialOutputs = () => request<OfficialOutputNode[]>('/api/outputs');
export const officialOutputUrl = (path: string) => `/api/output/${path.split('/').map(encodeURIComponent).join('/')}`;

export type OfficialAccount = { platform: string; name: string; backend: string; supported: boolean; loggedIn: boolean; note: string };
export const listOfficialAccounts = () => request<OfficialAccount[]>('/api/accounts');
