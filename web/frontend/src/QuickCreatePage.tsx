import { useEffect, useMemo, useRef, useState } from 'react';
import { getProfile, getWorkflow, listMemories, listOfficialSkills, listQuickDrafts, listWorkflows, readOfficialOutput, retryWorkflow, saveQuickDraft, startWorkflow, type Memory, type OfficialSkill, type ProfileSnapshot, type WorkflowDebugEvent, type WorkflowJob, type WorkflowStreamingOutput } from './api';
import { Message, errorText } from './components/shared';
import { StudioIcon } from './components/StudioIcon';
import { profilePrompt } from './lib/profile';

type Platform = 'wechat' | 'xiaohongshu' | 'douyin';
type Mode = '文章' | '配图' | '内容+配图';
type ModeOption = '文章' | '配图';
type OutputKind = 'standard' | 'video';
type Draft = { id: string; topic: string; title?: string; context?: string; source?: string; sourceUrl?: string; platform: Platform; mode: Mode; skill: string; output: string; createdAt: number; workflowId?: string | null; workflowArtifact?: string | null; taskId?: string | null; inputVersion?: number; persistenceState?: 'saved_input' | 'local_only' };
type OutputMetadata = { platform: Platform; mode: Mode; skill: string; workflowId: string | null; workflowArtifact: string | null; source: string; sourceUrl: string };
type ComposeFormSnapshot = { outputKind?: OutputKind; topic?: string; context?: string; source?: string; sourceUrl?: string; platform?: Platform; mode?: Mode; skill?: string; workflowId?: string | null; workflowArtifact?: string | null; feedback?: 'keep' | 'adjust'; feedbackNote?: string };
type LearningFeedback = { reaction: 'keep' | 'adjust'; note: string; platform: Platform; mode: Mode; createdAt: number };
const platforms: Record<Platform, { label: string; short: string; detail: string }> = {
  wechat: { label: '公众号', short: '图文文章', detail: '完整文章 · 配图 · 可复制的公众号排版' },
  xiaohongshu: { label: '小红书', short: '图文笔记', detail: '整套卡片 · 发布文案 · 话题与校验' },
  douyin: { label: '抖音', short: '脚本', detail: '开头有钩子 · 口播顺 · 分镜清楚' },
};
const articleSkills: Record<Platform, string[]> = {
  wechat: ['social-content', 'gzh-design'],
  xiaohongshu: ['xhs-note-creator'],
  douyin: ['video-script', 'auto-short-video'],
};
const imageSkills = ['card-design', 'card-xiaohongshu', 'infographic', 'poster-hero', 'comparison-card'];
const labels: Record<string, string> = { 'skill-wechat-publisher': '公众号完整创作', 'gzh-design': '公众号排版', 'auto-short-video': '短视频完整制作', 'social-content': '社媒原生内容', 'skill-article-outline': '文章结构', copywriting: '文案写作', 'xhs-note-creator': '小红书笔记', 'video-script': '视频脚本', 'card-design': '卡片设计', 'card-xiaohongshu': '小红书卡片', infographic: '信息图', 'poster-hero': '竖版海报', 'comparison-card': '对比图' };
const allowedSkills = (mode: Mode, platform: Platform) => mode === '配图' ? imageSkills : articleSkills[platform];
const modeIncludes = (mode: Mode, option: ModeOption) => mode === '内容+配图' || mode === option;
const defaultSkill = (mode: Mode, platform: Platform) => allowedSkills(mode, platform)[0];
const readJson = <T,>(key: string): T | null => { try { return JSON.parse(window.localStorage.getItem(key) || 'null') as T | null; } catch { return null; } };
const readArray = <T,>(key: string): T[] => { const value = readJson<unknown>(key); return Array.isArray(value) ? value as T[] : []; };
const removeStorage = (key: string) => { try { window.localStorage.removeItem(key); } catch { /* A private or restricted store should not block the editor. */ } };
const writeStorage = (key: string, value: unknown) => {
  try { window.localStorage.setItem(key, JSON.stringify(value)); return ''; }
  catch { return '本机存储空间不足或不可写，已继续尝试服务端保存。'; }
};
const feedbackPrompt = (rows: LearningFeedback[], platform?: Platform, mode?: Mode) => rows.filter(item => (!platform || item.platform === platform) && (!mode || item.mode === mode)).slice(0, 6).map(item => `${item.reaction === 'keep' ? '保留当前表达' : '调整当前表达'}${item.note ? `：${item.note}` : ''}`).join('；');
const stageLabels: Record<string, string> = { intake: '整理需求', research: '研究素材', plan: '规划内容', produce: '创作与制作', media: '制作媒体', validate: '校验产物', delivery: '整理交付', discovery: '核验素材', topic: '整理主题', master: '生成初稿', adaptation: '按平台改写', quality: '检查内容', archive: '保存草稿' };
const platformFinalFiles: Record<Platform, string> = { wechat: '08-gzh-final.md', xiaohongshu: '09-xhs-final.md', douyin: '10-douyin-final.md' };
const platformOutputLabels: Record<Platform, Record<Mode, string>> = {
  wechat: { 文章: '图文文章', 配图: '配图', '内容+配图': '图文文章' },
  xiaohongshu: { 文章: '整套笔记', 配图: '卡片', '内容+配图': '整套笔记' },
  douyin: { 文章: '脚本', 配图: '封面与配图', '内容+配图': '脚本与配图' },
};
const workflowStages = ['discovery', 'topic', 'master', 'adaptation', 'quality', 'archive'] as const;
const compactWorkflowStages = [
  { key: 'discovery', label: '核验素材', keys: ['discovery'] as const },
  { key: 'generation', label: '生成内容', keys: ['topic', 'master', 'adaptation'] as const },
  { key: 'delivery', label: '检查与保存', keys: ['quality', 'archive'] as const },
] as const;

const mediaUrl = (path: string) => `/api/media/${path.split('/').map(encodeURIComponent).join('/')}`;
const isImageArtifact = (path: string) => /\.(?:png|jpe?g|webp|gif)$/i.test(path);
const isVideoArtifact = (path: string) => /\.(?:mp4|webm|mov)$/i.test(path);
const artifactLabel = (path: string) => isImageArtifact(path) ? '图片 / 卡片' : isVideoArtifact(path) ? '视频文件' : /\.html?$/i.test(path) ? '公众号排版 / HTML' : /(?:script|storyboard|douyin)/i.test(path) ? '脚本 / 分镜' : /\.json$/i.test(path) ? '元数据 / 校验记录' : /\.md$/i.test(path) ? '文案 / 研究稿' : '产物文件';
const readableStatus = (status?: string) => ({ completed: '已完成', ready: '已完成', draft: '草稿', draft_ready: '草稿已生成', passed: '通过', pass: '通过', ok: '通过', failed: '未通过', fail: '未通过', blocked: '待补齐', pending: '待处理', running: '处理中', skipped: '未执行' }[status || ''] || status || '待检查');
const checkSummary = (value: unknown) => {
  if (typeof value === 'string') return value;
  if (!value || typeof value !== 'object') return String(value ?? '');
  const check = value as Record<string, unknown>;
  const name = String(check.name || check.label || check.script || check.kind || '产物校验');
  const status = check.status ? readableStatus(String(check.status)) : check.ok === true || check.returncode === 0 || check.exit_code === 0 ? '通过' : check.ok === false ? '未通过' : '已记录';
  return `${name}：${status}${check.reason || check.message ? ` · ${String(check.reason || check.message)}` : ''}`;
};

type StreamingPreview = { content: string; complete: boolean };
const normalizeStreamingOutput = (value: WorkflowStreamingOutput | undefined): StreamingPreview | null => {
  if (!value) return null;
  if (typeof value === 'string') return value ? { content: value, complete: false } : null;
  const content = String(value.content ?? value.text ?? value.partial ?? '');
  if (!content) return null;
  return {
    content,
    complete: value.complete === true || value.done === true || value.status === 'completed',
  };
};
// Legacy jobs still use the six-stage contract. Compact jobs receive a server
// budget; the fallback keeps older jobs observable without imposing a client
// deadline that is shorter than the old serial workflow.
const LEGACY_WORKFLOW_MAX_WAIT_SECONDS = 35 * 60;
const isGatewayBlocked = (message: string) => /模型\/研究网关|网关未配置|网关不可用|余额不足|额度|欠费|arrearage|overdue|账户状态|billing|insufficient balance|API Key/i.test(message);
const formatDuration = (seconds: number) => {
  const safe = Math.max(0, Math.floor(seconds));
  const minutes = Math.floor(safe / 60);
  const remaining = safe % 60;
  return minutes ? `${minutes}分${String(remaining).padStart(2, '0')}秒` : `${remaining}秒`;
};
const formatDebugTime = (value?: number | string | null) => {
  if (value == null || value === '') return '';
  const raw = typeof value === 'number' ? value : Number(value);
  if (Number.isFinite(raw)) {
    const ms = raw > 100000000000 ? raw : raw * 1000;
    return new Date(ms).toLocaleTimeString('zh-CN', { hour12: false });
  }
  const parsed = new Date(String(value));
  return Number.isNaN(parsed.getTime()) ? String(value) : parsed.toLocaleTimeString('zh-CN', { hour12: false });
};
const debugEventText = (event: WorkflowDebugEvent) => String(event.message || event.text || event.task || event.action || event.event || event.tool || event.kind || event.status || '系统事件');
const debugEventDuration = (event: WorkflowDebugEvent) => {
  const milliseconds = Number(event.duration_ms ?? event.elapsed_ms ?? (event.duration_seconds != null ? event.duration_seconds * 1000 : event.elapsed_seconds != null ? event.elapsed_seconds * 1000 : NaN));
  return Number.isFinite(milliseconds) && milliseconds >= 0 ? formatDuration(milliseconds / 1000) : '';
};
const timestampMs = (value?: number | null) => {
  if (!value || !Number.isFinite(value)) return 0;
  return value > 100000000000 ? value : value * 1000;
};
const workflowStatus = (status: WorkflowJob['status']) => ({ queued: '排队中', running: '正在处理', completed: '已完成', blocked: '暂时无法继续', failed: '处理失败', interrupted: '已停止等待' }[status]);
const workflowErrorText = (error: unknown) => {
  const message = errorText(error);
  if (/402|余额不足|额度|欠费|arrearage|overdue|账户状态|billing|insufficient balance|insufficient credit|temporarily disabled/i.test(message)) return '模型账户欠费或状态异常。请到服务商控制台处理欠费并开启额度，或到“模型设置”更换可用 API Key；当前主题和素材已保留。';
  if (/context[ _-]?length|maximum context|prompt (?:is )?too long|stopreason[^\n]*length|上下文.{0,4}(过长|超限)/i.test(message)) return '这次生成内容太长，超过了模型单次处理上限。已保留当前主题和素材，请减少补充素材或重试，系统会从未完成阶段继续。';
  if (isGatewayBlocked(message)) return '模型服务还没准备好，暂时不能生成。请先到“模型设置”保存并测试模型；当前主题和素材已保留，配置完成后可以重新生成。';
  if (/failed to fetch|networkerror|load failed/i.test(message)) return '生成过程暂时中断，本地服务没有响应。当前主题和素材已保留，请确认 CreatorOS 服务仍在运行后重试。';
  if (/平台终稿未生成/i.test(message)) return '平台终稿没有生成，当前主题和素材已保留。请重试平台适配；如果仍失败，请检查模型服务。';
  if (/timeout|超时/i.test(message)) return '生成等待超时，当前主题和素材已保留。请稍后重试，或先检查模型服务。';
  return message || '这次没有生成成功，当前主题和素材已保留，请稍后重试。';
};

export function QuickCreatePage({ navigate }: { navigate: (path: string) => void }) {
  const [outputKind, setOutputKind] = useState<OutputKind>('standard');
  const outputEdited = useRef(false);
  const [previousOutput, setPreviousOutput] = useState(''); const [platform, setPlatform] = useState<Platform>('wechat'); const [mode, setMode] = useState<Mode>('文章'); const [topic, setTopic] = useState(''); const [context, setContext] = useState(''); const [skills, setSkills] = useState<OfficialSkill[]>([]); const [skill, setSkill] = useState(defaultSkill('文章', 'wechat')); const [output, setOutput] = useState(''); const [generatedOutput, setGeneratedOutput] = useState(''); const [notice, setNotice] = useState(''); const [error, setError] = useState(''); const [busy, setBusy] = useState(false); const [saving, setSaving] = useState(false); const [stage, setStage] = useState(''); const [showAdvanced, setShowAdvanced] = useState(false); const [source, setSource] = useState(''); const [sourceUrl, setSourceUrl] = useState(''); const [draftId, setDraftId] = useState(''); const [workflowId, setWorkflowId] = useState<string | null>(null); const [workflowArtifact, setWorkflowArtifact] = useState<string | null>(null); const [workflowJob, setWorkflowJob] = useState<WorkflowJob | null>(null); const [workflowWatching, setWorkflowWatching] = useState(false); const [workflowStartedAt, setWorkflowStartedAt] = useState<number | null>(null); const [workflowClock, setWorkflowClock] = useState(() => Date.now()); const [generatedMeta, setGeneratedMeta] = useState<OutputMetadata | null>(null); const [profile, setProfile] = useState<ProfileSnapshot | null>(null); const [profileVersion, setProfileVersion] = useState<number | null>(null); const [memories, setMemories] = useState<Memory[]>([]); const [useProfile, setUseProfile] = useState(false); const [feedback, setFeedback] = useState<'keep' | 'adjust' | ''>(''); const [feedbackNote, setFeedbackNote] = useState(''); const [feedbackSaved, setFeedbackSaved] = useState(false); const [gatewayBlocked, setGatewayBlocked] = useState(false); const [formReady, setFormReady] = useState(false); const [debugMode, setDebugMode] = useState(() => readJson<boolean>('creatoros:workflow-debug') === true);
  // StrictMode re-runs effects during development. Handoff envelopes are
  // consumed once, so the second setup must not fall back to an empty form.
  const handoffInitialized = useRef(false);
  // A server rehydrate may finish after the user starts typing. Keep edits
  // made in the form authoritative over late metadata.
  const userEdited = useRef(false);
  const workflowRecoveryInitialized = useRef(false);
  const pendingWorkflow = useRef<ComposeFormSnapshot | null>(null);
  const workflowWatchRef = useRef(false);
  const workflowStopRequestedRef = useRef(false);
  // A boolean is not enough when a user stops one run and starts another: the
  // old poller could become active again after its in-flight request returns.
  // Every watcher therefore owns a monotonically increasing run token.
  const workflowRunRef = useRef(0);
  const workflowProgressRef = useRef<HTMLElement | null>(null);
  const [finalMissing, setFinalMissing] = useState(false);
  const [qualityReview, setQualityReview] = useState('');
  const [streamingPreview, setStreamingPreview] = useState('');
  const [streamingComplete, setStreamingComplete] = useState(false);
  useEffect(() => {
    if (handoffInitialized.current) {
      // The listener still needs to be registered after StrictMode's effect
      // cleanup/setup cycle; only the one-shot handoff read is gated.
      const reset = () => { workflowRunRef.current += 1; workflowWatchRef.current = false; userEdited.current = false; outputEdited.current = false; setOutputKind('standard'); pendingWorkflow.current = null; setWorkflowWatching(false); setWorkflowStartedAt(null); setDraftId(''); setWorkflowId(null); setWorkflowArtifact(null); setWorkflowJob(null); setGeneratedMeta(null); setQualityReview(''); setStreamingPreview(''); setStreamingComplete(false); setPreviousOutput(''); setTopic(''); setContext(''); setOutput(''); setSource(''); setSourceUrl(''); setNotice(''); setError(''); setGatewayBlocked(false); setShowAdvanced(false); setPlatform('wechat'); setMode('文章'); setSkill(defaultSkill('文章', 'wechat')); setUseProfile(false); setFeedback(''); setFeedbackNote(''); setFeedbackSaved(false); setGeneratedOutput(''); setFormReady(true); };
      window.addEventListener('creatoros:new-content', reset);
      return () => window.removeEventListener('creatoros:new-content', reset);
    }
    handoffInitialized.current = true;
    const hotspot = readJson<{ title?: string; summary?: string; source?: string; url?: string }>('creatoros:selected-hotspot');
    const editing = readJson<Draft>('creatoros:editing-draft');
    const savedForm = readJson<ComposeFormSnapshot>('creatoros:compose-form');
    // These entries are hand-off envelopes, not durable page state. Consume
    // them after the first mount so a later click on “新创作” cannot reopen
    // an old hotspot or draft unexpectedly.
    removeStorage('creatoros:selected-hotspot');
    removeStorage('creatoros:editing-draft');
    if (editing) {
      outputEdited.current = Boolean(editing.output);
      pendingWorkflow.current = editing.workflowId ? { workflowId: editing.workflowId, workflowArtifact: editing.workflowArtifact, topic: editing.topic || editing.title, context: editing.context, platform: editing.platform, mode: editing.mode, skill: editing.skill } : null;
      const editingSourceUrl = editing.sourceUrl || (/^https?:\/\//i.test(editing.source || '') ? editing.source || '' : '');
      setDraftId(editing.id); setTopic((editing.topic || editing.title || '未命名草稿').trim()); setContext(editing.context || ''); setSource(editing.source || ''); setSourceUrl(editingSourceUrl); setPlatform(editing.platform); setMode(editing.mode); setSkill(editing.skill); setOutput(editing.output); setWorkflowId(editing.workflowId || null); setWorkflowArtifact(editing.workflowArtifact || null);
      setGeneratedMeta({ platform: editing.platform, mode: editing.mode, skill: editing.skill, workflowId: editing.workflowId || null, workflowArtifact: editing.workflowArtifact || null, source: editing.source || '', sourceUrl: editingSourceUrl });
      // The local hand-off is intentionally disposable and older local-only
      // copies may miss metadata. Rehydrate from the durable content record
      // when available so Continue editing always restores topic/platform/mode.
      void listQuickDrafts().then(rows => {
        if (userEdited.current) return;
        const durable = rows.find(row => row.quick_draft_id === editing.id || (editing.workflowId && row.workflow_id === editing.workflowId));
        if (!durable || userEdited.current) return;
        const durableSource = typeof durable.source?.label === 'string' ? durable.source.label : typeof durable.source?.url === 'string' ? durable.source.url : '';
        const durableUrl = typeof durable.source?.url === 'string' ? durable.source.url : '';
        setTopic(durable.title || editing.topic || editing.title || '未命名草稿'); setContext(durable.context || editing.context || ''); setSource(durableSource || editing.source || ''); setSourceUrl(durableUrl || editingSourceUrl); setPlatform(durable.platform); setMode(durable.mode); setSkill(durable.skill); setWorkflowId(durable.workflow_id || editing.workflowId || null); setWorkflowArtifact(durable.output_artifact || editing.workflowArtifact || null);
        setGeneratedMeta({ platform: durable.platform, mode: durable.mode, skill: durable.skill, workflowId: durable.workflow_id || editing.workflowId || null, workflowArtifact: durable.output_artifact || editing.workflowArtifact || null, source: durableSource || editing.source || '', sourceUrl: durableUrl || editingSourceUrl });
      }).catch(() => { /* Local hand-off remains a valid fallback when the service is unavailable. */ });
    } else if (hotspot) {
      setTopic(hotspot.title || ''); setContext(hotspot.summary || ''); setSource(hotspot.source || hotspot.url || ''); setSourceUrl(hotspot.url || '');
    } else if (savedForm) {
      // Keep the original form for legacy recovery before the persistence
      // effect writes this mount's initial empty state.
      pendingWorkflow.current = savedForm;
      setOutputKind(savedForm.outputKind === 'video' ? 'video' : 'standard'); setTopic(savedForm.topic || ''); setContext(savedForm.context || ''); setSource(savedForm.source || ''); setSourceUrl(savedForm.sourceUrl || ''); if (savedForm.platform) setPlatform(savedForm.platform); if (savedForm.mode) setMode(savedForm.mode); if (savedForm.skill) setSkill(savedForm.skill); if (savedForm.feedback) { setFeedback(savedForm.feedback); setFeedbackNote(savedForm.feedbackNote || ''); } if (savedForm.workflowId) { setWorkflowId(savedForm.workflowId); setWorkflowArtifact(savedForm.workflowArtifact || null); }
    }
    setFormReady(true);
    void listOfficialSkills().then(setSkills).catch(e => setError(errorText(e)));
    const reset = () => { workflowRunRef.current += 1; workflowWatchRef.current = false; userEdited.current = false; outputEdited.current = false; setOutputKind('standard'); pendingWorkflow.current = null; setWorkflowWatching(false); setWorkflowStartedAt(null); setDraftId(''); setWorkflowId(null); setWorkflowArtifact(null); setWorkflowJob(null); setGeneratedMeta(null); setQualityReview(''); setStreamingPreview(''); setStreamingComplete(false); setPreviousOutput(''); setTopic(''); setContext(''); setOutput(''); setSource(''); setSourceUrl(''); setNotice(''); setError(''); setGatewayBlocked(false); setShowAdvanced(false); setPlatform('wechat'); setMode('文章'); setSkill(defaultSkill('文章', 'wechat')); setUseProfile(false); setFeedback(''); setFeedbackNote(''); setFeedbackSaved(false); setGeneratedOutput(''); setFormReady(true); };
    window.addEventListener('creatoros:new-content', reset); return () => window.removeEventListener('creatoros:new-content', reset);
  }, []);
  useEffect(() => {
    if (!workflowJob || !['queued', 'running'].includes(workflowJob.status)) return;
    setWorkflowClock(Date.now());
    const timer = window.setInterval(() => setWorkflowClock(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [workflowJob?.id, workflowJob?.status]);
  useEffect(() => {
    if (busy) workflowProgressRef.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }, [busy]);
  useEffect(() => { void getProfile().then(result => { setProfile(result.current_version.snapshot); setProfileVersion(result.current_version.version_no); }).catch(() => setProfile(null)); void listMemories().then(items => setMemories(items.filter(item => item.confirmation_status === 'confirmed'))).catch(() => setMemories([])); }, []);
  useEffect(() => { const allowed = allowedSkills(mode, platform); setSkill(current => allowed.includes(current) ? current : defaultSkill(mode, platform)); }, [mode, platform]);
  useEffect(() => { if (formReady) writeStorage('creatoros:compose-form', { topic, context, source, sourceUrl, platform, mode, skill, outputKind, workflowId, workflowArtifact, feedback: feedback || undefined, feedbackNote }); }, [formReady, topic, context, source, sourceUrl, platform, mode, skill, outputKind, workflowId, workflowArtifact, feedback, feedbackNote]);
  useEffect(() => { writeStorage('creatoros:workflow-debug', debugMode); }, [debugMode]);
  const availableSkills = useMemo(() => { const allowed = allowedSkills(mode, platform); const listed = skills.filter(item => allowed.includes(item.name)); return listed.length ? listed : allowed.map(name => ({ name, description: '', layer: 'CREATOROS', needsApi: false, apiConfigured: false })); }, [mode, platform, skills]);
  const workflowPlatform = (value: Platform) => value === 'wechat' ? 'wechat-oa' : value;
  const syncStreamingPreview = (job: WorkflowJob, requestedPlatform: Platform) => {
    const raw = job.streaming_outputs?.[workflowPlatform(requestedPlatform)] || (job.live_stream?.stage === 'adaptation' || job.live_stream?.stage === 'master' ? job.live_stream : undefined);
    const preview = normalizeStreamingOutput(raw);
    if (!preview) return;
    setStreamingPreview(preview.content);
    setStreamingComplete(preview.complete);
    // Keep the partial response separate from the editable result. The final
    // artifact is the only value that can be saved or downloaded.
  };
  const applyWorkflowOutput = async (job: WorkflowJob, requestedPlatform: Platform, requestedMode: Mode, requestedSkill: string, requestedSource: string, requestedSourceUrl: string, runToken: number) => {
    const platformResult = job.platform_outputs?.[workflowPlatform(requestedPlatform)];
    const qualityPath = job.stages.quality?.artifact;
    const quality = qualityPath ? (await readOfficialOutput(qualityPath).catch(() => null))?.content || '' : '';
    const adaptationPath = job.stages.adaptation?.artifact || '';
    const legacyPath = adaptationPath.includes('/') ? `${adaptationPath.slice(0, adaptationPath.lastIndexOf('/') + 1)}${platformFinalFiles[requestedPlatform]}` : '';
    const finalPath = platformResult?.primary_text || legacyPath;
    const finalOutput = finalPath ? await readOfficialOutput(finalPath).catch(() => null) : null;
    // The editable panel shows the platform's primary artifact (note/script/article).
    // copy_text remains the concise publish-copy fallback when a primary artifact
    // is unavailable, so a card set is not silently reduced to its caption.
    const next = finalOutput?.content?.trim() || platformResult?.copy_text?.trim() || '';
    if (workflowRunRef.current !== runToken || !workflowWatchRef.current) return;
    setQualityReview([quality, ...(platformResult?.checks || []).map(checkSummary), ...(platformResult?.missing || []).map(item => `待补齐：${item}`)].filter(Boolean).join('\n\n'));
    if (!next) { setFinalMissing(true); if (job.status === 'completed') throw new Error(`平台终稿未生成（${platforms[requestedPlatform].label}）。请从未完成阶段重试。`); return; }
    setFinalMissing(false);
    setWorkflowArtifact(finalPath || null); setGeneratedMeta({ platform: requestedPlatform, mode: requestedMode, skill: platformResult?.skill || requestedSkill, workflowId: job.id, workflowArtifact: finalPath || null, source: requestedSource, sourceUrl: requestedSourceUrl });
    setGeneratedOutput(next); setStreamingPreview(next); setStreamingComplete(true);
    if (outputEdited.current) { setNotice('最新产物已载入，已保留你编辑过的正文。原始产物可在下方查看和下载。'); return; }
    setOutput(next); setPreviousOutput(''); setFeedback(''); setFeedbackNote(''); setFeedbackSaved(false);
    const needsChanges = platformResult ? platformResult.status !== 'completed' && platformResult.status !== 'ready' || Boolean(platformResult.missing?.length) : /需修改|blocked|不建议发布|待核验|需人工复核|未执行/i.test(quality);
    setNotice(`已载入${platforms[requestedPlatform].label}${platformOutputLabels[requestedPlatform][requestedMode]}。${needsChanges ? '部分制作或校验尚未完成，请查看产物状态。' : '产物和校验结果已单独保存，当前仍为本地草稿。'}`);
  };
  const watchWorkflow = async (initial: WorkflowJob, metadata: { platform: Platform; mode: Mode; skill: string; source: string; sourceUrl: string }, inheritedToken?: number) => {
    let job = initial;
    const runToken = inheritedToken ?? (workflowRunRef.current + 1);
    workflowRunRef.current = runToken;
    workflowWatchRef.current = true;
    setWorkflowWatching(true);
    setWorkflowId(job.id); setWorkflowJob(job); syncStreamingPreview(job, metadata.platform);
    // Retries keep the original creation timestamp for auditability. The
    // elapsed clock shown to the user must start at the current attempt,
    // otherwise a retry can immediately look like a one-hour hang.
    const startedTimestamp = job.attempt_started || job.started_at || job.started || (job.attempt && job.attempt > 1 ? (job.updated || job.created) : job.created);
    const startedAt = timestampMs(startedTimestamp);
    setWorkflowStartedAt(startedAt || Date.now());
    // The server timestamp includes queue time, so reopening the page does not
    // grant a second full client timeout. A small grace period covers the final
    // status write and one poll round trip.
    const budgetSeconds = Math.max(60, Number(job.budget_seconds) || LEGACY_WORKFLOW_MAX_WAIT_SECONDS);
    const deadline = (startedAt || Date.now()) + budgetSeconds * 1000 + 30_000;
    while ((job.status === 'queued' || job.status === 'running') && workflowWatchRef.current && workflowRunRef.current === runToken && Date.now() < deadline) {
      setWorkflowJob(job); syncStreamingPreview(job, metadata.platform); setStage(stageLabels[job.current || Object.entries(job.stages).find(([, value]) => value.status === 'running')?.[0] || ''] || '内容生成');
      await new Promise(resolve => window.setTimeout(resolve, 500));
      if (!workflowWatchRef.current || workflowRunRef.current !== runToken) return;
      job = await getWorkflow(job.id);
      setWorkflowJob(job);
      syncStreamingPreview(job, metadata.platform);
    }
    if (!workflowWatchRef.current || workflowRunRef.current !== runToken) return;
    setWorkflowJob(job); syncStreamingPreview(job, metadata.platform);
    if ((job.status === 'queued' || job.status === 'running') && Date.now() >= deadline) {
      // Fetch one last snapshot at the boundary so a job that settled between
      // polls is shown with its real terminal reason instead of a client-side
      // timeout message.
      job = await getWorkflow(job.id).catch(() => job);
      setWorkflowJob(job); syncStreamingPreview(job, metadata.platform);
      if (job.status === 'queued' || job.status === 'running') {
        // This is a local observer timeout, not a server failure. Keep the
        // active job and recovery controls visible so the user can reconnect
        // without creating a duplicate run.
        workflowWatchRef.current = false;
        setWorkflowWatching(false);
        setNotice(`本地等待已暂停（服务端预算 ${formatDuration(budgetSeconds)}）。任务仍在后台处理，主题和素材已保留，可稍后继续查看状态。`);
        return;
      }
    }
    if (job.status !== 'completed') {
      if (job.platform_outputs) await applyWorkflowOutput(job, metadata.platform, metadata.mode, metadata.skill, metadata.source, metadata.sourceUrl, runToken);
      const failedEntry = Object.entries(job.stages).find(([, value]) => value.status === 'blocked' || value.status === 'failed' || value.status === 'interrupted');
      const failedStage = failedEntry?.[1];
      const reason = failedStage?.reason || '内容任务未完成，请检查模型服务后重试。';
      if (/本阶段调用模型失败/.test(reason)) {
        throw new Error(`${stageLabels[failedEntry?.[0] || ''] || '当前'}阶段未完成，模型没有返回有效结果；可从该阶段重试。`);
      }
      throw new Error(reason);
    }
    await applyWorkflowOutput(job, metadata.platform, metadata.mode, metadata.skill, metadata.source, metadata.sourceUrl, runToken);
    workflowWatchRef.current = false;
    setWorkflowWatching(false);
    setStage('');
  };
  const stopWatchingWorkflow = () => {
    if (!workflowJob && !busy) return;
    workflowRunRef.current += 1;
    workflowWatchRef.current = false;
    workflowStopRequestedRef.current = true;
    setWorkflowWatching(false);
    setBusy(false);
    setStage('');
    setNotice('已停止等待，主题和素材已保留。后台任务可能仍在继续，你可以稍后继续查看状态。');
  };
  const resumeWorkflow = async () => {
    if (!workflowJob || !['queued', 'running'].includes(workflowJob.status) || busy) return;
    setBusy(true); setError(''); setNotice(''); setGatewayBlocked(false); setStage('重新连接工作流');
    try {
      await watchWorkflow(workflowJob, { platform, mode, skill, source, sourceUrl });
    } catch (e) {
      const message = errorText(e); setStage(''); setGatewayBlocked(isGatewayBlocked(message)); setError(workflowErrorText(e));
      workflowWatchRef.current = false; setWorkflowWatching(false);
    } finally { setBusy(false); }
  };
  useEffect(() => {
    if (workflowRecoveryInitialized.current) return;
    workflowRecoveryInitialized.current = true;
    const saved = readJson<ComposeFormSnapshot>('creatoros:compose-form');
    const pending = pendingWorkflow.current || saved;
    const targetTopic = (pending?.topic || saved?.topic || '').trim();
    if (!targetTopic) return;
    const targetPlatform = pending?.platform || saved?.platform || 'wechat';
    const targetMode = pending?.mode || saved?.mode || '文章';
    const targetSkill = pending?.skill || saved?.skill || defaultSkill(targetMode, targetPlatform);
    const targetId = pending?.workflowId || null;
    let cancelled = false;
    void (async () => {
      try {
        let job: WorkflowJob | null = targetId ? await getWorkflow(targetId).catch(() => null) : null;
        if (!job) {
          const normalized = targetTopic.toLowerCase();
          const rows = await listWorkflows();
          job = rows.find(item => item.platforms?.includes(workflowPlatform(targetPlatform)) && item.topic?.split('\n')[0]?.trim().toLowerCase() === normalized) || null;
        }
        if (!job || cancelled || userEdited.current) return;
        setWorkflowId(job.id); setWorkflowJob(job); setBusy(job.status === 'queued' || job.status === 'running');
        try {
          await watchWorkflow(job, { platform: targetPlatform, mode: targetMode, skill: targetSkill, source, sourceUrl });
        } catch (e) {
          if (!cancelled) { const message = errorText(e); setStage(''); setBusy(false); setGatewayBlocked(isGatewayBlocked(message)); setError(workflowErrorText(e)); workflowWatchRef.current = false; setWorkflowWatching(false); }
        } finally { if (!cancelled) setBusy(false); }
      } catch (e) { if (!cancelled) setError(`工作流恢复失败：${errorText(e)}`); }
    })();
    // StrictMode performs an extra cleanup/setup cycle. Reset the guard so
    // the second setup can own recovery instead of leaving it cancelled.
    return () => { cancelled = true; workflowRecoveryInitialized.current = false; };
  }, []);
  const persistFeedback = (targetPlatform: Platform, targetMode: Mode, announce = true) => {
    if (!feedback) return '';
    const row: LearningFeedback = { reaction: feedback, note: feedbackNote.trim(), platform: targetPlatform, mode: targetMode, createdAt: Date.now() };
    const previous = readArray<LearningFeedback>('creatoros:learning-feedback');
    const same = (item: LearningFeedback) => item.reaction === row.reaction && item.note === row.note && item.platform === row.platform && item.mode === row.mode;
    const storageError = writeStorage('creatoros:learning-feedback', [row, ...previous.filter(item => !same(item))].slice(0, 20));
    if (storageError) { if (announce) setError(storageError); return storageError; }
    setFeedbackSaved(true);
    if (announce) setNotice('这条建议已保存，下次生成时会参考。');
    return '';
  };
  const generate = async (adjustment?: string) => {
    const adjustmentText = adjustment?.trim() || '';
    if (adjustmentText && (!feedback || feedback !== 'adjust')) { setError('请先选择“需要调整”，再填写具体修改要求。'); return; }
    if (adjustmentText && !feedbackNote.trim()) { setError('请先写下希望调整的地方，例如“把第三段写得更具体”。'); return; }
    if (workflowIsActive) { setNotice('已有生成任务在后台处理中，请继续查看状态或等待它完成。'); return; }
    if (!topic.trim()) { setError('先输入一个主题，或者回到热点页选一个话题。'); return; }
    // A new run must never look like it produced the previous draft. Clear the
    // editable result and metadata before the request starts; the progress
    // card is the source of truth until this run completes.
    const runToken = workflowRunRef.current + 1;
    workflowRunRef.current = runToken;
    workflowStopRequestedRef.current = false;
    workflowWatchRef.current = true;
    const originalOutput = output;
    outputEdited.current = false;
    const originalDraftId = draftId;
    const revisionWasTruncated = adjustmentText && originalOutput.length > 8000;
    setPreviousOutput(adjustmentText ? originalOutput : '');
    setWorkflowWatching(true); setWorkflowStartedAt(Date.now()); setBusy(true); setError(''); setNotice(adjustmentText ? `正在按你的修改要求重新生成，原稿会暂时保留。${revisionWasTruncated ? '原稿超过 8000 字，本次只按前 8000 字调整。' : ''}` : ''); setGatewayBlocked(false); setStage(adjustmentText ? '按意见调整' : '准备工作流'); setOutput(adjustmentText ? originalOutput : ''); setStreamingPreview(''); setStreamingComplete(false); setGeneratedOutput(''); setGeneratedMeta(null); setWorkflowArtifact(null); setWorkflowJob(null); setWorkflowId(null); setDraftId(adjustmentText ? originalDraftId : ''); setQualityReview(''); setFinalMissing(false);
    const requestedPlatform = platform;
    const requestedMode = mode;
    const requestedOutputKind = platform === 'douyin' ? outputKind : 'standard';
    const requestedSkill = requestedOutputKind === 'video' ? 'auto-short-video' : skill;
    const requestedSource = source;
    const requestedSourceUrl = sourceUrl;
    const platformLabel = platforms[requestedPlatform].label;
    const workflowPlatform = requestedPlatform === 'wechat' ? 'wechat-oa' : requestedPlatform;
    const safeProfile = useProfile ? (profilePrompt(profile, requestedPlatform) + (memories.length ? '；已确认偏好：' + memories.slice(0, 2).map(item => item.statement).join('；') : '')).slice(0, 900) : '';
    const currentFeedback = feedback ? feedbackPrompt([{ reaction: feedback, note: feedbackNote.trim(), platform: requestedPlatform, mode: requestedMode, createdAt: Date.now() }], requestedPlatform, requestedMode) : '';
    const revisionDraft = adjustmentText ? originalOutput.trim().slice(0, 8000) : '';
    const previousFeedback = feedbackPrompt(readArray<LearningFeedback>('creatoros:learning-feedback'), requestedPlatform, requestedMode);
    const feedbackForThisRun = [previousFeedback, currentFeedback].filter(Boolean).join('；');
    if (feedback) { persistFeedback(requestedPlatform, requestedMode, false); if (!adjustmentText) { setFeedback(''); setFeedbackNote(''); setFeedbackSaved(false); } }
    const workflowTopic = [topic.trim(), context.trim() ? '补充素材：' + context.trim() : '', requestedSourceUrl ? '参考链接：' + requestedSourceUrl : '', `输出类型：${requestedMode}`, requestedOutputKind === 'video' ? '交付要求：抖音竖屏成片，9:16，1080×1920；依照 Easel auto-short-video 完成真实媒体制作。需要尚未授权的按量付费时先返回制作计划与待确认状态，不自动发起付费请求。' : requestedPlatform === 'douyin' ? '交付要求：抖音脚本与分镜，不把脚本称为视频文件。' : '交付要求：执行该平台 Easel 完整生成流程，返回实际文案、媒体、排版与校验产物；缺少配置或素材时明确列出缺项。', '事实约束：不虚构亲测、店铺、价格、数据或经历。无法核验的关键信息列入独立研究记录和待补材料，不把内部检查说明混入发布正文。', feedbackForThisRun ? '最近反馈：' + feedbackForThisRun : ''].filter(Boolean).join('\n\n');
    try {
      const job = await startWorkflow({ topic: workflowTopic, platforms: [workflowPlatform], profile: safeProfile, skill: requestedSkill, output_kind: requestedOutputKind, debug_mode: debugMode, revision: adjustmentText ? { draft: revisionDraft, instruction: adjustmentText.slice(0, 1000) } : undefined });
      setWorkflowId(job.id); setWorkflowJob(job);
      writeStorage('creatoros:compose-form', { topic, context, source: requestedSource, sourceUrl: requestedSourceUrl, platform: requestedPlatform, mode: requestedMode, skill: requestedSkill, outputKind: requestedOutputKind, workflowId: job.id, workflowArtifact: null });
      if (!workflowWatchRef.current || workflowRunRef.current !== runToken) {
        // The user may stop waiting while the POST is still in flight. Keep
        // the returned job attached so it can be resumed after the request
        // finishes; a newer run keeps ownership when its token is greater.
        if (workflowStopRequestedRef.current && workflowRunRef.current === runToken + 1) {
          setNotice('工作流已创建，已停止前台等待。可点击“继续查看状态”查看结果。');
        }
        return;
      }
      await watchWorkflow(job, { platform: requestedPlatform, mode: requestedMode, skill: requestedSkill, source: requestedSource, sourceUrl: requestedSourceUrl }, runToken);
    } catch (e) { const message = errorText(e); if (adjustmentText && originalOutput) { setOutput(originalOutput); setGeneratedOutput(originalOutput); } setPreviousOutput(''); setStage(''); setGatewayBlocked(isGatewayBlocked(message)); setError(workflowErrorText(e)); workflowWatchRef.current = false; setWorkflowWatching(false); } finally { setBusy(false); }
  };
  const retryCurrentWorkflow = async () => {
    if (!workflowId || busy) return;
    setBusy(true); setError(''); setNotice(''); setGatewayBlocked(false); setFinalMissing(false); setStreamingPreview(''); setStreamingComplete(false); setStage('准备重试');
    try {
      const job = await retryWorkflow(workflowId);
      setWorkflowJob(job);
      await watchWorkflow(job, { platform, mode, skill, source, sourceUrl });
    } catch (e) { const message = errorText(e); setStage(''); setGatewayBlocked(isGatewayBlocked(message)); setError(workflowErrorText(e)); workflowWatchRef.current = false; setWorkflowWatching(false); }
    finally { setBusy(false); }
  };
  const save = async () => {
    if (!output || saving) return;
    const id = draftId || crypto.randomUUID(); setDraftId(id); setSaving(true); setError('');
    const now = Date.now();
    const metadata = generatedMeta || { platform, mode, skill, workflowId, workflowArtifact, source, sourceUrl };
    const rows = readArray<Draft>('creatoros:quick-drafts');
    const item: Draft = { id, topic, context, source: metadata.source, sourceUrl: metadata.sourceUrl, platform: metadata.platform, mode: metadata.mode, skill: metadata.skill, output, createdAt: now, workflowId: metadata.workflowId, workflowArtifact: metadata.workflowArtifact, persistenceState: 'local_only' };
    let localError = '';
    try {
      localError = writeStorage('creatoros:quick-drafts', [item, ...rows.filter(row => row.id !== id)].slice(0, 30));
      const feedbackError = persistFeedback(metadata.platform, metadata.mode, false);
      if (feedbackError) localError = feedbackError || localError;
    } catch {
      localError = '本机存储空间不足或不可写，已继续尝试服务端保存。';
    }
    try {
      const persisted = await saveQuickDraft({ quick_draft_id: id, topic, context, source: metadata.source || metadata.sourceUrl ? { label: metadata.source, url: metadata.sourceUrl || metadata.source } : {}, platform: metadata.platform, mode: metadata.mode, skill: metadata.skill, workflow_id: metadata.workflowId, output, output_artifact: metadata.workflowArtifact });
      const saved: Draft = { ...item, persistenceState: 'saved_input', taskId: persisted.task_id, inputVersion: persisted.input_version, createdAt: new Date(persisted.created_at).getTime() || now };
      const syncError = writeStorage('creatoros:quick-drafts', [saved, ...readArray<Draft>('creatoros:quick-drafts').filter(row => row.id !== id)].slice(0, 30));
      if (syncError) { setNotice('已保存到内容库，但本机恢复副本未更新。'); setError(syncError); }
      else { setNotice(`已保存到内容库（第 ${persisted.input_version} 版），可在刷新后继续编辑。`); if (localError) setError(localError); }
    } catch (e) {
      if (localError) { setNotice('服务端未同步，本机也未保存。'); setError(`保存失败：${localError} 服务端：${errorText(e)}`); }
      else { setNotice('已保存在本机；服务端尚未同步。'); setError(`内容库未同步：${errorText(e)}`); }
    } finally { setSaving(false); }
  };
  const download = () => { if (!output) return; const blob = new Blob([output], { type: 'text/markdown;charset=utf-8' }); const link = document.createElement('a'); link.href = URL.createObjectURL(blob); link.download = `${topic.slice(0, 24) || 'creatoros-草稿'}.md`; link.click(); URL.revokeObjectURL(link.href); };
  const markComposerEdited = () => { userEdited.current = true; setError(''); setGatewayBlocked(false); setGeneratedMeta(null); setQualityReview(''); if (!busy && workflowId && !workflowIsActive) { setWorkflowId(null); setWorkflowArtifact(null); setWorkflowJob(null); } };
  const workflowIsActive = Boolean(workflowJob && ['queued', 'running'].includes(workflowJob.status));
  const workflowServerStartedAt = workflowJob ? timestampMs(workflowJob.attempt_started || workflowJob.started_at || workflowJob.started || workflowJob.created) : 0;
  const workflowServerFinishedAt = workflowJob ? timestampMs(workflowJob.finished_at || workflowJob.finished) : 0;
  const workflowElapsed = workflowJob?.duration_seconds != null || workflowJob?.duration_ms != null
    ? Math.max(0, Math.floor(workflowJob.duration_seconds ?? (workflowJob.duration_ms || 0) / 1000))
    : workflowJob && !workflowIsActive && workflowServerStartedAt && workflowServerFinishedAt
      ? Math.max(0, Math.floor((workflowServerFinishedAt - workflowServerStartedAt) / 1000))
      : workflowServerStartedAt
        ? Math.max(0, Math.floor((workflowClock - workflowServerStartedAt) / 1000))
        : workflowStartedAt ? Math.max(0, Math.floor((workflowClock - workflowStartedAt) / 1000)) : 0;
  const workflowSlow = workflowIsActive && workflowElapsed >= 120;
  const workflowCurrentKey = workflowJob?.current || (workflowJob ? Object.entries(workflowJob.stages).find(([, value]) => value.status === 'running' || value.status === 'failed' || value.status === 'blocked' || value.status === 'interrupted')?.[0] : '');
  const workflowCurrentLabel = workflowJob?.stages[workflowCurrentKey || '']?.label || stageLabels[workflowCurrentKey || ''] || stage || '准备工作流';
  const currentStage = workflowJob?.stages[workflowCurrentKey || ''];
  const stageStartedAt = timestampMs(currentStage?.started_at || currentStage?.started);
  const stageFinishedAt = timestampMs(currentStage?.finished_at || currentStage?.finished);
  const workflowStageElapsed = currentStage?.duration_seconds != null || currentStage?.duration_ms != null
    ? Math.max(0, Math.floor(currentStage.duration_seconds ?? (currentStage.duration_ms || 0) / 1000))
    : currentStage && !workflowIsActive && stageStartedAt && stageFinishedAt
      ? Math.max(0, Math.floor((stageFinishedAt - stageStartedAt) / 1000))
      : stageStartedAt
        ? Math.max(0, Math.floor((workflowClock - stageStartedAt) / 1000))
        : workflowJob?.updated ? Math.max(0, Math.floor((workflowClock - timestampMs(workflowJob.updated)) / 1000)) : workflowElapsed;
  const workflowTimingLabel = workflowIsActive
    ? `当前阶段已用 ${formatDuration(workflowStageElapsed)}`
    : workflowJob
      ? `任务耗时 ${formatDuration(workflowElapsed)}`
      : '';
  const workflowDebugEvents = useMemo(() => {
    if (!workflowJob) return [] as WorkflowDebugEvent[];
    const source = workflowJob.debug_events || workflowJob.debug_log || [];
    return source.filter(Boolean).slice(-160);
  }, [workflowJob?.debug_events, workflowJob?.debug_log]);
  const currentTask = String(workflowJob?.current_task || currentStage?.current_task || currentStage?.task || '').trim();
  const stageDetail = (item: typeof currentStage) => {
    if (!item) return '';
    const started = timestampMs(item.started_at || item.started);
    const finished = timestampMs(item.finished_at || item.finished);
    const seconds = item.duration_seconds != null || item.duration_ms != null
      ? Number(item.duration_seconds ?? (item.duration_ms || 0) / 1000)
      : started && finished ? (finished - started) / 1000 : started ? (workflowClock - started) / 1000 : 0;
    return seconds > 0 ? formatDuration(seconds) : '';
  };
  const hasStreamingPreview = Boolean(streamingPreview && !output);
  const streamingFailed = hasStreamingPreview && Boolean(workflowJob && ['failed', 'blocked', 'interrupted'].includes(workflowJob.status));
  const streamingSettled = hasStreamingPreview && streamingComplete && !busy;
  const easelWorkflow = workflowJob?.execution_mode === 'easel-agent-v1';
  const platformResult = workflowJob?.platform_outputs?.[workflowPlatform(generatedMeta?.platform || platform)];
  const outputArtifacts = Array.from(new Set(platformResult?.artifacts || []));
  const resultLabel = platform === 'douyin' && outputKind === 'video' ? '成片' : platformOutputLabels[platform][mode];
  const compactWorkflow = Boolean(workflowJob?.execution_mode?.startsWith('compact'));
  const displayedWorkflowStages = easelWorkflow && workflowJob ? Object.entries(workflowJob.stages).map(([key, value]) => ({ key, label: value.label || stageLabels[key] || key, keys: [key] })) : compactWorkflow ? compactWorkflowStages : workflowStages.map(key => ({ key, label: stageLabels[key], keys: [key] as const }));
  const workflowStageState = (keys: readonly string[]) => {
    const items = keys.map(key => workflowJob?.stages[key]).filter(Boolean);
    const blocked = items.some(item => item?.status === 'blocked' || item?.status === 'failed' || item?.status === 'interrupted');
    const active = items.some(item => item?.status === 'running') || (workflowJob?.current ? keys.includes(workflowJob.current) : false);
    const done = items.length > 0 && items.every(item => item?.status === 'completed');
    return { done, active: !done && active, blocked };
  };
  return <>
    <div className="studio-page-heading create-heading">
      <div><div className="page-kicker">WORKSPACE / 02</div><h1>内容工作区</h1><p>按平台完成研究、创作、媒体制作和检查，带走文案与真实产物。</p></div>
      <div className="create-heading-actions">
        <button type="button" className={`secondary debug-log-toggle${debugMode ? ' enabled' : ''}`} role="switch" aria-checked={debugMode} aria-label="调试日志" onClick={() => setDebugMode(current => !current)}><span className="debug-log-indicator" aria-hidden="true" />调试日志：{debugMode ? '已开启' : '已关闭'}</button>
        <button className="quiet-button" disabled={busy} onClick={() => navigate('hotspots')}><StudioIcon name="compass" size={16} />回到热点</button>
      </div>
    </div>
    {debugMode && !workflowJob && <p className="debug-mode-note" role="status">调试日志已开启。开始生成后，执行步骤、任务和耗时会显示在创作进度下方。</p>}
    <div className="profile-context-strip"><div><span className="page-kicker">PROFILE CONTEXT</span><strong>{profile ? `写作偏好 v${profileVersion || '?'} 已就绪` : '还没有保存写作偏好'}</strong><small>{profile ? '生成前可选择把平台语气与已确认偏好发送给当前模型服务。' : '先建立写作偏好，内容会更稳定地像你。'}</small></div><button className="secondary" disabled={busy} onClick={() => navigate('profile')}>{profile ? '调整写作偏好' : '建立写作偏好'}<StudioIcon name="arrow" size={14} /></button></div>
    {notice && <Message>{notice}</Message>}
    {error && <Message error>{error}{gatewayBlocked && <button className="link" onClick={() => navigate('settings')}>去模型设置</button>}</Message>}
    {(workflowJob || busy) && <section ref={workflowProgressRef} className={`composer-workflow${compactWorkflow ? ' compact' : ''}`} aria-label={easelWorkflow ? '完整创作流程进度' : compactWorkflow ? '三段创作进度' : '六阶段创作进度'} aria-busy={busy || workflowWatching} aria-live="polite">
      <div className="composer-workflow-head"><div><div className="composer-workflow-title">创作进度 · {busy ? '进行中' : finalMissing ? '缺少平台终稿' : workflowJob ? workflowStatus(workflowJob.status) : '正在连接模型服务'}</div><p>{workflowJob ? `当前阶段：${workflowCurrentLabel} · ${workflowTimingLabel}${currentTask ? ` · ${currentTask}` : ''}` : '正在连接模型服务并创建内容任务，页面不会静默等待。'}</p></div><div className="composer-workflow-meta"><strong>{formatDuration(workflowElapsed)}</strong><small>本次处理用时</small></div></div>
      {debugMode && workflowJob && <p className="debug-mode-note">{workflowJob.debug_mode ? '正在显示本次任务的执行步骤和耗时。' : '正在显示已有记录；详细调试记录将在下次新建任务时启用。'}</p>}
      {workflowJob ? <ol>{displayedWorkflowStages.map((group, index) => { const state = workflowStageState(group.keys); const item = workflowJob.stages[group.key]; return <li className={state.done ? 'done' : state.blocked ? 'blocked' : state.active ? 'active' : ''} key={group.key}><b>{state.done ? '✓' : state.blocked ? '!' : index + 1}</b><span>{group.label}<small>{state.active ? `进行中${stageDetail(item) ? ` · ${stageDetail(item)}` : ''}` : state.done ? `已完成${stageDetail(item) ? ` · ${stageDetail(item)}` : ''}` : state.blocked ? '需要重试' : '待开始'}</small>{debugMode && item?.current_task && <em>{item.current_task}</em>}</span></li>; })}</ol> : <div className="composer-workflow-preparing"><span className="workflow-pulse" />正在创建内容任务，通常几秒内会显示第一阶段。</div>}
      {workflowSlow && busy && <div className="composer-workflow-warning">已经等待 {formatDuration(workflowElapsed)}，模型可能仍在处理；你可以停止等待，稍后继续查看状态。</div>}
      {debugMode && workflowJob && <details className="workflow-debug-panel" open><summary>系统执行日志（{workflowDebugEvents.length} 条）</summary>{workflowDebugEvents.length ? <ol>{workflowDebugEvents.map((event, index) => <li className={`debug-${event.level || 'info'}`} key={`${String(event.id ?? index)}-${index}`}><time>{formatDebugTime(event.at ?? event.timestamp ?? event.time)}</time><strong>{event.stage ? `${stageLabels[event.stage] || event.stage} · ` : ''}{debugEventText(event)}</strong>{event.tool && <code>{event.tool}</code>}{debugEventDuration(event) && <small>{debugEventDuration(event)}</small>}{event.details && <pre>{JSON.stringify(event.details, null, 2)}</pre>}</li>)}</ol> : <p>正在等待后端记录第一条事件……</p>}</details>}
      <div className="composer-workflow-actions">{busy && <button type="button" className="secondary" onClick={stopWatchingWorkflow}>停止等待</button>}{!busy && workflowIsActive && <button type="button" className="secondary" onClick={() => void resumeWorkflow()}>继续查看状态</button>}{!busy && workflowJob && !workflowIsActive && (finalMissing || workflowJob.status !== 'completed') && <button type="button" className="secondary" onClick={() => void retryCurrentWorkflow()}>{finalMissing ? '从平台改写重试' : '从未完成阶段重试'}</button>}</div>
    </section>}
    {qualityReview && <details className="quality-review"><summary>查看发布前质量检查（不会混入正文或下载文件）</summary><pre>{qualityReview}</pre></details>}
    <div className="composer-layout">
      <section className="composer-panel">
        <div className="composer-panel-head"><span className="step-badge">01</span><div><h2>先说说你想写什么</h2><p>一句话就够，越接近你的真实想法越好。</p></div></div>
        <label className="composer-label">主题<input autoFocus disabled={busy} value={topic} onChange={e => { markComposerEdited(); setTopic(e.target.value); }} placeholder="例如：为什么大家开始重新重视线下体验" /></label>
        {source && <div className="source-attribution" role="note" title="用于记录选题出处，不会直接改变生成内容"><span className="source-attribution-icon"><StudioIcon name="link" size={12} /></span><span className="source-attribution-label">选题出处</span><strong>{source}</strong><small>仅作记录</small></div>}
        <label className="composer-label">补充素材 <span>可选</span><textarea disabled={busy} rows={6} value={context} onChange={e => { markComposerEdited(); setContext(e.target.value); }} placeholder="粘贴热点摘要、链接要点、自己的观点或素材…" /></label>
        <div className="composer-divider" />
        <div className="composer-panel-head"><span className="step-badge">02</span><div><h2>你准备发到哪里</h2><p>不同平台，会用不同的说法。</p></div></div>
        <div className="platform-picker">{(Object.keys(platforms) as Platform[]).map(key => <button type="button" disabled={busy} key={key} className={platform === key ? 'selected' : ''} onClick={() => { markComposerEdited(); setPlatform(key); }}><span className={`platform-dot ${key}`}>{key === 'wechat' ? '微' : key === 'xiaohongshu' ? '红' : '音'}</span><span><strong>{platforms[key].label}</strong><small>{platforms[key].short}</small></span>{platform === key && <StudioIcon name="check" size={16} />}</button>)}</div>
        <div className="composer-divider" />
        <div className="composer-panel-head"><span className="step-badge">03</span><div><h2>你要带走什么</h2><p>{platform === 'douyin' ? '先选脚本，或继续制作成片。' : '完整内容会包含平台需要的配图和排版。'}</p></div></div>
        <div className="result-picker" role="group" aria-label="选择交付内容"><button type="button" disabled={busy} aria-pressed={modeIncludes(mode, '文章')} className={modeIncludes(mode, '文章') ? 'selected' : ''} onClick={() => { markComposerEdited(); setMode('文章'); }}><StudioIcon name="file" size={18} /><span><strong>{platform === 'wechat' ? '整套公众号文章' : platform === 'xiaohongshu' ? '整套小红书笔记' : '抖音脚本'}</strong><small>{platform === 'wechat' ? '正文、配图和可复制的 HTML 排版' : platform === 'xiaohongshu' ? '卡片、发布文案、标题与话题' : '口播、分镜、字幕与封面方案，不含视频'}</small></span>{modeIncludes(mode, '文章') && <StudioIcon name="check" size={16} />}</button><button type="button" disabled={busy} aria-pressed={mode === '配图'} className={mode === '配图' ? 'selected' : ''} onClick={() => { markComposerEdited(); setMode('配图'); setOutputKind('standard'); }}><StudioIcon name="image" size={18} /><span><strong>只做配图</strong><small>按素材制作封面、卡片或信息图</small></span>{mode === '配图' && <StudioIcon name="check" size={16} />}</button></div>
        {platform === 'douyin' && mode !== '配图' && <label className="profile-consent"><input type="checkbox" checked={outputKind === 'video'} disabled={busy} onChange={e => { markComposerEdited(); setOutputKind(e.target.checked ? 'video' : 'standard'); }} /><span><strong>继续生成成片</strong><small>制作 9:16 竖屏视频；可能需要媒体模型配置。按量付费环节会先给出计划，等待单独确认。</small></span></label>}
        <small className="selection-summary">将生成：{platforms[platform].label}{resultLabel}。</small>
        <div className="media-capability-note" role="note"><StudioIcon name="image" size={16} /><span><strong>{platform === 'douyin' && outputKind !== 'video' ? '脚本完成与视频完成分别显示' : '按真实产物显示完成状态'}</strong><small>只有实际生成并检查过的文件才会出现在产物列表；缺少素材或能力会保留待补齐状态。</small></span></div>
        <details className="advanced-skill" open={showAdvanced} onToggle={e => setShowAdvanced((e.currentTarget as HTMLDetailsElement).open)}><summary><span>更换写作方式</span><small>当前推荐：{labels[skill] || skill}</small></summary><select disabled={busy} value={skill} onChange={e => { markComposerEdited(); setSkill(e.target.value); }}>{availableSkills.map(item => <option key={item.name} value={item.name}>{labels[item.name] || item.name}{item.needsApi && !item.apiConfigured ? ' · 需配置' : ''}</option>)}</select></details>
        <label className="profile-consent"><input type="checkbox" checked={useProfile} onChange={e => setUseProfile(e.target.checked)} disabled={busy || !profile} /><span><strong>{profile ? `本次使用写作偏好 v${profileVersion || '?'}` : '暂无可用写作偏好'}</strong><small>仅发送平台风格、读者和已确认偏好到当前模型服务；身份与经历留在本机。</small></span></label>
        <label className="debug-preference"><input type="checkbox" checked={debugMode} onChange={e => setDebugMode(e.target.checked)} disabled={busy} /><span><strong>开启调试模式</strong><small>显示系统正在执行的步骤、任务、工具和耗时，设置会保存在本机。</small></span></label>
        <button className="primary composer-submit" disabled={busy || workflowIsActive || !topic.trim()} onClick={() => void generate()}><StudioIcon name="spark" size={18} />{busy ? '正在' + (stage || '创作') + '…' : workflowIsActive ? '已有任务处理中…' : `生成${platforms[platform].label}${resultLabel}`}</button><small className="truth-note">使用 Easel 的平台生成流程完成创作与检查；只生成本地产物，发布由你另行决定。</small>
      </section>
      <section className="output-panel"><div className="output-panel-head"><div><span className="page-kicker">YOUR DRAFT</span><h2>{output ? busy ? '上一份草稿（新生成中）' : '这就是你的草稿' : hasStreamingPreview ? streamingFailed ? '未完成预览' : streamingSettled ? '生成完成，正在载入终稿' : '正在实时生成' : '成稿会出现在这里'}</h2>{busy && previousOutput && <small className="output-preserved-note">原稿已保留；新结果完成后会替换这里。</small>}{hasStreamingPreview && <small className="streaming-preview-note">已收到 {streamingPreview.length.toLocaleString()} 字{streamingFailed ? '，本次未完成，不能保存' : '，任务完成后可编辑、保存和下载'}</small>}</div>{output && <span className="ready-state"><span />{busy ? '等待新结果' : '可编辑'}</span>}{hasStreamingPreview && !output && <span className="streaming-state"><span />{streamingFailed ? '未完成' : '实时接收'}</span>}</div>
        {output ? <><textarea disabled={busy} className="output-editor" value={output} onChange={e => { userEdited.current = true; outputEdited.current = true; setError(''); setOutput(e.target.value); }} aria-label="生成结果" /><div className="learning-feedback"><div><strong>给下次生成留个建议</strong><small>这不会直接修改当前正文；选择后点“保存建议”，下次生成时会参考。</small>{feedback && <small className="feedback-status" role="status">{feedbackSaved ? '这条建议已保存，下次生成时会参考。' : '已选择，还没保存。'}</small>}</div><div className="feedback-buttons"><button type="button" disabled={busy} aria-pressed={feedback === 'keep'} className={feedback === 'keep' ? 'selected' : ''} onClick={() => { setFeedback('keep'); setFeedbackSaved(false); setNotice('已选择“像我”。如需记录，请点击“保存建议”。'); }}>像我</button><button type="button" disabled={busy} aria-pressed={feedback === 'adjust'} className={feedback === 'adjust' ? 'selected' : ''} onClick={() => { setFeedback('adjust'); setFeedbackSaved(false); setNotice('已选择“需要调整”。写下具体问题后，可以按这条意见重新生成。'); }}>需要调整</button>{feedback === 'adjust' && <button type="button" disabled={busy || !feedbackNote.trim()} onClick={() => void generate(feedbackNote)}>按这条意见重新生成</button>}{feedback && <button type="button" disabled={busy || feedbackSaved} onClick={() => { persistFeedback(platform, mode); }}>保存建议</button>}</div>{feedback && <input disabled={busy} value={feedbackNote} onChange={e => { setFeedbackNote(e.target.value); setFeedbackSaved(false); }} placeholder={feedback === 'keep' ? '哪一点最像你？可选' : '例如：把第三段写得更具体，删掉广告口吻'} />}</div><div className="output-actions"><button className="primary" disabled={saving || busy} onClick={() => void save()}><StudioIcon name="check" size={15} />{saving ? '正在保存…' : '保存到我的内容'}</button><button className="secondary" disabled={busy} onClick={download}><StudioIcon name="download" size={15} />下载 Markdown</button><button className="quiet-button" disabled={busy} onClick={() => { outputEdited.current = true; setOutput(''); }}>清空</button></div></> : hasStreamingPreview ? <><textarea disabled readOnly className="output-editor streaming-output" value={streamingPreview} aria-label="实时生成预览" /><p className="streaming-preview-footnote">这是模型正在返回的预览，尚未写入最终稿文件。</p></> : <div className="output-placeholder"><span><StudioIcon name="spark" size={23} /></span><h3>准备好了吗？</h3><p>左侧选好主题、平台和交付组合，点击生成，内容会在这里出现。</p></div>}
        {output && busy && streamingPreview && <section className="live-stream-panel" aria-live="polite"><div><strong>实时生成预览</strong><small>新内容正在分段返回，原稿仍保留在上方</small></div><textarea disabled readOnly className="output-editor streaming-output" value={streamingPreview} aria-label="新内容实时生成预览" /><p className="streaming-preview-footnote">已收到 {streamingPreview.length.toLocaleString()} 字，任务完成并通过校验后才会替换原稿。</p></section>}
        {platformResult && <section className="quality-review" aria-label="真实产物与校验"><h3>已生成的产物</h3><p>{readableStatus(platformResult.status)} · {platformResult.media_kind === 'script' ? '脚本，不含视频文件' : platformResult.media_kind === 'video' ? '视频制作' : platformResult.media_kind === 'image' ? '图文卡片' : '平台内容包'}</p>{platformResult.missing?.length ? <ul>{platformResult.missing.map((item, index) => <li key={`${item}-${index}`}>待补齐：{item}</li>)}</ul> : null}{outputArtifacts.length ? <ul>{outputArtifacts.map(path => <li key={path} style={{ marginBottom: 14 }}><a href={mediaUrl(path)} target="_blank" rel="noopener noreferrer">{artifactLabel(path)} · {path.split('/').pop()}</a> <a href={mediaUrl(path)} download>下载</a>{isImageArtifact(path) && <a href={mediaUrl(path)} target="_blank" rel="noopener noreferrer" style={{ display: 'block', marginTop: 8 }}><img src={mediaUrl(path)} alt={`已生成图片：${path.split('/').pop()}`} loading="lazy" style={{ maxWidth: '100%', maxHeight: 320, objectFit: 'contain', borderRadius: 4 }} /></a>}{isVideoArtifact(path) && <video src={mediaUrl(path)} controls preload="metadata" style={{ display: 'block', maxWidth: '100%', maxHeight: 360, marginTop: 8 }} />}</li>)}</ul> : <p>还没有可下载的产物文件。</p>}{Boolean(platformResult.checks?.length) && <details><summary>查看产物校验</summary><ul>{platformResult.checks.map((check, index) => <li key={index}>{checkSummary(check)}</li>)}</ul></details>}{easelWorkflow && <small>本次流程：{platformResult.skill || '平台创作流程'} · 已记录 {workflowJob?.execution_receipts?.length || 0} 条执行回执。</small>}</section>}
      </section>
    </div>
  </>;
}
