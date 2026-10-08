import { useEffect, useState } from 'react';
import { ApiError, changeTaskStatus, getWorkflow, listWorkflows, retryWorkflow, startWorkflow, confirmBrief, createArtifactRevision, createBrief, createContentTask, createWechatDraftFromArtifact, exportArtifact, generateArtifacts, getArtifactHistory, getContentTask, reviseBrief, uploadTaskFile, type BriefEdit, type ContentTaskDetail, type HistoryRevision } from './api';
import { Fields, ReadFields } from './components/Fields';
import { dateLabel, errorText, Message, PageHeader, stateName, useDirty } from './components/shared';

type Navigate = (path: string) => void;
const WORKFLOW_STAGES = [
  ['discovery', '核验素材'], ['topic', '整理主题'], ['master', '初稿'],
  ['adaptation', '按平台改写'], ['quality', '检查内容'], ['archive', '保存草稿'],
] as const;
type Dirty = (value: boolean) => void;
const platformName = (p: string) => p === 'wechat' ? '公众号' : p === 'xiaohongshu' ? '小红书' : '抖音';
const clone = <T,>(value: T) => JSON.parse(JSON.stringify(value)) as T;
const statuses = ['idea', 'researching', 'briefed', 'drafting', 'adapted', 'reviewing', 'archived'];

export function ContentWorkspace({ taskId, navigate, onDirty }: { taskId: string; navigate: Navigate; onDirty: Dirty }) {
  const [detail, setDetail] = useState<ContentTaskDetail | null>(null);
  const [title, setTitle] = useState('');
  const [input, setInput] = useState('');
  const [inputType, setInputType] = useState<'theme' | 'url' | 'notes' | 'hotspot'>('theme');
  const [file, setFile] = useState<File | null>(null);
  const [createdId, setCreatedId] = useState('');
  const [notice, setNotice] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [briefDirty, setBriefDirty] = useState(false);
  const [artifactDirty, setArtifactDirty] = useState(false);
  const [workflowJob, setWorkflowJob] = useState<import('./api').WorkflowJob | null>(null);
  const [workflowError, setWorkflowError] = useState('');
  const [autosavedAt, setAutosavedAt] = useState('');
  const task = detail?.task;
  useDirty((!taskId && !!(title || input)) || briefDirty || artifactDirty, onDirty);
  useEffect(() => {
    if (taskId) return;
    const timer = window.setTimeout(() => {
      if (!title.trim() && !input.trim()) return;
      window.localStorage.setItem('creatoros:workspace-draft', JSON.stringify({ title, input, inputType }));
      setAutosavedAt(new Date().toLocaleTimeString('zh-CN', { hour12: false }));
    }, 650);
    return () => window.clearTimeout(timer);
  }, [taskId, title, input, inputType]);
  useEffect(() => {
    if (taskId || title || input) return;
    try {
      const raw = window.localStorage.getItem('creatoros:workspace-draft');
      if (!raw) return;
      const draft = JSON.parse(raw) as { title?: string; input?: string; inputType?: typeof inputType };
      if (draft.title) setTitle(draft.title);
      if (draft.input) setInput(draft.input);
      if (draft.inputType && ['theme', 'url', 'notes', 'hotspot'].includes(draft.inputType)) setInputType(draft.inputType);
      if (draft.title || draft.input) setAutosavedAt('已恢复本地草稿');
    } catch { /* local draft is an optional recovery aid */ }
  }, [taskId]);
  const load = async (id = taskId) => {
    const next = await getContentTask(id);
    setDetail(next); setTitle(next.task.title); setInput(next.inputs[0]?.text ?? '');
    const firstType = next.inputs[0]?.input_type;
    if (firstType && ['theme', 'url', 'notes', 'hotspot'].includes(firstType)) setInputType(firstType as typeof inputType);
    setError('');
  };
  useEffect(() => { if (taskId) void load().catch(e => setError(errorText(e))); }, [taskId]);
  useEffect(() => { if (taskId) return; void listWorkflows().then(items => items[0] && setWorkflowJob(items[0])).catch(() => {}); }, [taskId]);
  useEffect(() => {
    if (!workflowJob || !['queued', 'running'].includes(workflowJob.status)) return;
    const timer = window.setInterval(() => void getWorkflow(workflowJob.id).then(setWorkflowJob).catch(e => setWorkflowError(errorText(e))), 700);
    return () => window.clearInterval(timer);
  }, [workflowJob?.id, workflowJob?.status]);
  const launchWorkflow = () => void (async () => {
    if (!title.trim()) { setWorkflowError('请先填写主题'); return; }
    setWorkflowError('');
    try { setWorkflowJob(await startWorkflow({ topic: title.trim(), profile: 'creatoros' })); }
    catch (e) { setWorkflowError(errorText(e)); }
  })();
  const retryCurrentWorkflow = () => void (async () => {
    if (!workflowJob) return;
    setWorkflowError('');
    try { setWorkflowJob(await retryWorkflow(workflowJob.id)); }
    catch (e) { setWorkflowError(errorText(e)); }
  })();
  const run = async (action: () => Promise<void>) => {
    setBusy(true); setError('');
    try { await action(); } catch (e) { setError(errorText(e)); } finally { setBusy(false); }
  };
  const create = () => void run(async () => {
    if (!title.trim()) throw new Error('请先填写主题');
    if (file && (!file.size || file.size > 25 * 1024 * 1024)) throw new Error('请选择非空、25 MB 以内的文件');
    const id = createdId || (await createContentTask({ title, input_text: input, input_type: inputType })).id;
    setCreatedId(id);
    if (file) await uploadTaskFile(id, file);
    window.localStorage.removeItem('creatoros:workspace-draft');
    setTitle(''); setInput(''); setFile(null); setAutosavedAt(''); onDirty(false); navigate(`workspace/${id}`);
  });
  const makeBrief = () => void run(async () => {
    await createBrief(taskId); await load(); setNotice('写作计划草案已保存。补充读者问题、作者角度和来源后，再确认。');
  });
  const editBrief = (payload: Omit<BriefEdit, 'base_brief_id'>) => void run(async () => {
    await reviseBrief(taskId, { ...payload, base_brief_id: detail!.latest_brief!.id });
    await load(); setNotice('写作计划已保存为新版本，需要重新确认。');
  });
  const confirm = () => void run(async () => {
    await confirmBrief(taskId, detail!.latest_brief!.id); await load(); setNotice('写作计划已确认，可以创建三平台模板草稿。');
  });
  const generate = () => void run(async () => {
    await generateArtifacts(taskId); await load(); setNotice('三平台模板已分别保存，接下来可以逐份编辑。真实 AI 生成尚未接入。');
  });
  if (taskId && !task) return <><PageHeader title="正在打开任务" description="从本地读取已保存的素材、写作计划和平台版本。" />{error ? <Message error>{error} <button onClick={() => void run(() => load())}>重新读取</button></Message> : <p role="status">读取中…</p>}</>;
  return <>
    <PageHeader title={task?.title ?? '一键工作流'} description="从一个主题开始，经过发现、策划、创作、适配、检查和归档，再交付到公众号、小红书和抖音。每一步都会保存在本机。">
      <div className="header-actions">{task && <span className="state">{stateName(task.status)}</span>}{!task && <button className="primary" disabled={busy || !title.trim()} onClick={launchWorkflow}>开始一键工作流</button>}<button className="secondary" onClick={() => navigate('library')}>内容库</button></div>
    </PageHeader>
    {notice && <Message>{notice}</Message>}
    {error && <Message error>{error}{!task && <button className="link" onClick={() => navigate('profile')}>打开写作偏好</button>}</Message>}
    {!task && workflowJob && <section className="panel migrated-workflow"><div className="panel-title"><div><span className="kicker">CREATOROS FLOW</span><h2>一键执行六阶段</h2></div><span className={`state ${workflowJob.status === 'blocked' || workflowJob.status === 'failed' ? 'warning' : workflowJob.status === 'completed' ? 'success' : ''}`}>{workflowJob.status === 'blocked' ? '暂时无法继续' : workflowJob.status === 'completed' ? '本地草稿已保存' : workflowJob.status === 'failed' ? '处理失败' : '执行中'}</span></div><p className="muted">{workflowJob.status === 'blocked' ? '模型服务未配置或不可用，未生成模拟内容。配置后可从失败阶段重试。' : workflowJob.status === 'completed' ? '已保存为本地草稿，仍需事实核验、媒体制作和人工审校。' : '一次启动，状态持续写入本机。'}</p><div className="migrated-flow-grid">{WORKFLOW_STAGES.map(([key, label], i) => { const stage = workflowJob.stages[key]; return <div className={`migrated-flow-step ${stage?.status || 'pending'}`} key={key}><b>{String(i + 1).padStart(2, '0')}</b><strong>{label}</strong><small>{stage?.status === 'completed' ? '已完成' : stage?.status === 'running' ? '进行中' : stage?.status === 'blocked' ? '暂时无法继续' : stage?.status === 'failed' ? '失败' : '等待中'}</small>{stage?.reason && <span>{stage.reason}</span>}</div>; })}</div>{workflowError && <Message error>{workflowError}</Message>}{['blocked', 'failed', 'interrupted'].includes(workflowJob.status) && <button className="secondary" onClick={retryCurrentWorkflow}>从未完成阶段重试</button>}</section>}
    <section className="workspace-layout">
      <aside className="workflow"><div className="workflow-title">任务进度</div>
        {statuses.map((status, i) => <div className={`workflow-step ${task && statuses.indexOf(task.status) >= i ? 'done' : ''}`} key={status}><b>{i + 1}</b><span>{stateName(status)}</span></div>)}
        {task && <div className="workflow-actions">
          {task.status === 'adapted' && <button className="secondary" disabled={busy || artifactDirty} onClick={() => void run(async () => { await changeTaskStatus(task.id, 'reviewing'); await load(); })}>进入审阅</button>}
          {task.status === 'reviewing' && <button className="secondary" disabled={busy || artifactDirty} onClick={() => void run(async () => { await changeTaskStatus(task.id, 'archived'); await load(); })}>归档任务</button>}
          {task.status === 'archived' && <button className="secondary" disabled={busy} onClick={() => void run(async () => { await changeTaskStatus(task.id, 'reviewing'); await load(); })}>重新打开任务</button>}
        </div>}
      </aside>
      <section className="workspace-main">
        <section className="panel task-input">
          <div className="panel-title"><div><span className="kicker">输入</span><h2>{task ? '原始主题与素材' : '从一个主题开始'}</h2></div>{task && <span className="state">写作偏好已锁定</span>}</div>
          <label>主题<input maxLength={200} value={title} onChange={e => setTitle(e.target.value)} placeholder="例如：如何把一次失败的上线复盘写成方法" disabled={!!task || busy} /></label>
          {!task && <label>输入来源<select value={inputType} onChange={e => setInputType(e.target.value as typeof inputType)} disabled={busy}><option value="theme">手动主题</option><option value="url">网页链接</option><option value="notes">文章或会议记录</option></select></label>}
          <label>{inputType === 'url' ? '网页链接' : '原始素材'}<textarea maxLength={10000} rows={5} value={input} onChange={e => setInput(e.target.value)} placeholder={inputType === 'url' ? 'https://…（先保存链接，抓取与核验由后续连接方式处理）' : '粘贴文章、会议记录、自己的经历或线索。原文会保留在本地。'} disabled={!!task || busy} /></label>
          {!task && <label>上传文件（可选）<input type="file" accept="image/*,.pdf,.md,.markdown,.doc,.docx,video/*" onChange={e => setFile(e.target.files?.[0] ?? null)} disabled={busy} /><small className="field-help">文件只保存到本机数据目录，当前不做内容解析。</small></label>}
          {!task && <><button className="secondary" disabled={busy || !title.trim()} onClick={create}>{busy ? '保存中…' : '仅保存主题'}</button>{autosavedAt && <small className="save-hint" role="status">本机已自动保存输入 · {autosavedAt}</small>}</>}
          {task && <small>创建于 {dateLabel(task.created_at)} · 写作偏好版本 {task.profile_version_id.slice(0, 8)} · 原始输入保留供后续追溯</small>}
          {createdId && <Message>主题已保存。文件上传失败时可更换文件重试，不会重复创建任务。<button onClick={() => { onDirty(false); navigate(`workspace/${createdId}`); }}>打开已保存任务</button></Message>}
          {detail && <div className="source-inputs"><h3>任务素材（{detail.inputs.length}）</h3>{detail.inputs.map(row => <div className="trace-box" key={row.id}>
            <strong>{row.input_type === 'file' ? String(row.metadata.original_name) : row.input_type === 'hotspot' ? '热点线索' : row.input_type === 'url' ? '网页链接' : '原始素材'}</strong>
            <p>{row.text || '文件已保存，尚未解析内容。'}</p>
            {row.input_type === 'file' && <a className="link" href={`/api/v1/inputs/${row.id}/download`}>下载原文件</a>}
            <small>{row.parse_status === 'stored_only' ? '仅保存原文件 · 待人工提取' : '原文已保存 · 事实待核验'}</small>
          </div>)}{task?.status !== 'archived' && <label>补充素材文件<input type="file" disabled={busy} accept="image/*,.pdf,.md,.markdown,.doc,.docx,video/*" onChange={e => { const chosen = e.target.files?.[0]; if (chosen) void run(async () => { await uploadTaskFile(taskId, chosen); await load(); setNotice('素材已保存；已有写作计划不会自动覆盖，请人工补充引用。'); }); e.target.value = ''; }} /></label>}</div>}
        </section>
        {detail && <BriefEditor detail={detail} onGenerate={makeBrief} onEdit={editBrief} onConfirm={confirm} busy={busy} onDirty={setBriefDirty} />}
        {detail && <PlatformEditor detail={detail} reload={load} generate={generate} navigate={navigate} busy={busy} onDirty={setArtifactDirty} />}
      </section>
    </section>
  </>;
}

type BriefDraft = Omit<BriefEdit, 'base_brief_id'>;
const briefDraft = (payload: Record<string, unknown>): BriefDraft => ({
  reader_problem: String(payload.reader_problem ?? ''), author_angle: String(payload.author_angle ?? ''),
  facts: Array.isArray(payload.facts) ? payload.facts as string[] : [],
  sources: Array.isArray(payload.sources) ? payload.sources as string[] : [],
  research_gaps: Array.isArray(payload.research_gaps) ? payload.research_gaps as string[] : [],
});
function BriefEditor({ detail, onGenerate, onEdit, onConfirm, busy, onDirty }: {
  detail: ContentTaskDetail; onGenerate: () => void; onEdit: (draft: BriefDraft) => void; onConfirm: () => void; busy: boolean; onDirty: Dirty;
}) {
  const brief = detail.latest_brief;
  const [draft, setDraft] = useState<BriefDraft>(() => briefDraft(brief?.payload ?? {}));
  const locked = detail.artifacts.length > 0;
  const dirty = !!brief && !locked && JSON.stringify(draft) !== JSON.stringify(briefDraft(brief.payload));
  useEffect(() => { setDraft(briefDraft(brief?.payload ?? {})); }, [brief?.id]);
  useDirty(dirty, onDirty);
  if (!brief) return <section className="panel"><span className="kicker">写作计划</span><h2>先建立内容方向</h2><p className="muted">根据已保存的写作偏好整理一份本地模板。事实和来源需要你补充与核验。</p><button className="primary" onClick={onGenerate} disabled={busy}>生成写作计划草案</button></section>;
  const sourceCount = Array.isArray(brief?.payload.sources) ? brief?.payload.sources.length : 0;
  const factCount = Array.isArray(brief?.payload.facts) ? brief?.payload.facts.length : 0;
  return <section className="panel brief-editor">
    <div className="panel-title"><div><span className="kicker">写作计划 v{brief.version_no}</span><h2>事实、判断和缺口分开</h2></div><span className={`state ${brief.confirmation_status === 'confirmed' ? 'success' : 'warning'}`}>{stateName(brief.confirmation_status)}</span></div>
    <div className="brief-evidence-strip"><span>来源 {sourceCount}</span><span>事实 {factCount}</span><span className={sourceCount === 0 ? 'warning-text' : ''}>{sourceCount === 0 ? '尚无来源，不能称为已核验' : '来源仍需人工核验'}</span></div>
    {locked ? <details><summary>查看本次创作采用的写作计划</summary><ReadFields value={draft} /><p className="hint">已有平台版本，保留当时确认的写作计划作为创作依据。</p></details> : <>
      <fieldset disabled={busy} className="editor-form"><Fields value={draft} onChange={v => setDraft(v as BriefDraft)} /></fieldset>
      <div className="action-row"><span className="hint">确认写作计划表示认可创作方向，来源仍需要人工核验。</span>{dirty && <button className="secondary" onClick={() => onEdit(draft)} disabled={busy}>保存写作计划新版本</button>}{brief.confirmation_status !== 'confirmed' && <button className="primary" onClick={onConfirm} disabled={busy || dirty}>确认写作计划</button>}</div>
    </>}
    {detail.briefs.length > 1 && <details className="history-detail"><summary>写作计划版本历史（{detail.briefs.length}）</summary>{detail.briefs.map(row => <details key={row.id}><summary>v{row.version_no} · {dateLabel(row.created_at)} · {stateName(row.confirmation_status)}</summary><ReadFields value={briefDraft(row.payload)} /></details>)}</details>}
  </section>;
}

function PlatformEditor({ detail, reload, generate, navigate, busy, onDirty }: {
  detail: ContentTaskDetail; reload: () => Promise<void>; generate: () => void; navigate: Navigate; busy: boolean; onDirty: Dirty;
}) {
  const [selected, setSelected] = useState('wechat');
  const artifact = detail.artifacts.find(a => a.platform === selected);
  const [content, setContent] = useState<Record<string, unknown> | null>(() => artifact?.current_revision ? clone(artifact.current_revision.content) : null);
  const [base, setBase] = useState(artifact?.current_revision_id ?? '');
  const [reason, setReason] = useState('');
  const [history, setHistory] = useState<HistoryRevision[]>([]);
  const [error, setError] = useState('');
  const [conflict, setConflict] = useState(false);
  const [working, setWorking] = useState(false);
  const [notice, setNotice] = useState('');
  const locked = detail.task.status === 'archived';
  const dirty = !!content && JSON.stringify(content) !== JSON.stringify(artifact?.current_revision?.content ?? {});
  useDirty(dirty, onDirty);
  useEffect(() => {
    const next = artifact?.current_revision;
    setContent(next ? clone(next.content) : null); setBase(next?.id ?? ''); setReason(''); setHistory([]); setError(''); setConflict(false);
  }, [artifact?.current_revision_id, selected]);
  const save = async () => {
    if (!artifact || !content) return;
    setWorking(true); setError(''); setConflict(false);
    try {
      await createArtifactRevision(artifact.id, content, reason, base);
      await reload(); setNotice('平台新版本已保存，修改差异和待确认偏好已记录。');
    } catch (e) {
      setError(errorText(e)); setConflict(e instanceof ApiError && e.status === 409);
    } finally { setWorking(false); }
  };
  const readHistory = async () => {
    if (!artifact) return;
    setWorking(true); setError('');
    try { setHistory(await getArtifactHistory(artifact.id)); } catch (e) { setError(errorText(e)); } finally { setWorking(false); }
  };
  const readLatest = async () => {
    if (dirty && !window.confirm('读取最新版本会丢弃表单中尚未保存的修改。确定继续吗？')) return;
    setWorking(true);
    try { await reload(); } catch (e) { setError(errorText(e)); } finally { setWorking(false); }
  };
  const saveAsWechatDraft = async () => {
    if (!artifact?.current_revision_id || selected !== 'wechat') return;
    setWorking(true); setError('');
    try {
      const draft = await createWechatDraftFromArtifact(artifact.id, artifact.current_revision_id);
      onDirty(false); navigate(`drafts/${draft.id}`);
    } catch (e) { setError(errorText(e)); } finally { setWorking(false); }
  };
  if (!detail.artifacts.length) return <section className="panel"><span className="kicker">按平台改写</span><h2>确认方向，再分别起草</h2><p className="muted">当前使用本地模板。公众号长文、小红书卡片、抖音口播与分镜分别保存；真实 AI 生成尚未接入。</p><button className="primary" onClick={generate} disabled={busy || detail.latest_brief?.confirmation_status !== 'confirmed'}>创建三平台模板草稿</button></section>;
  const memory = detail.memories.find(m => m.scope.platform === selected);
  return <section className="panel platform-editor">
    <div className="panel-title"><div><span className="kicker">按平台改写</span><h2>{locked ? '已归档的平台内容' : '分别编辑，不复制正文'}</h2></div><span className="state warning">本地模板 · 未接入 AI</span></div>
    <div className="platform-tabs">{['wechat', 'xiaohongshu', 'douyin'].map(platform => {
      const row = detail.artifacts.find(a => a.platform === platform);
      return row && <button disabled={working} className={platform === selected ? 'active' : ''} key={row.id} onClick={() => {
        if (platform === selected) return;
        if (dirty && !window.confirm('当前平台有未保存的修改。确定丢弃并切换吗？')) return;
        setSelected(platform); setNotice('');
      }}>{platformName(platform)}<small>{stateName(row.status)} · v{row.current_revision?.revision_no ?? 0}</small></button>;
    })}</div>
    {notice && <Message>{notice}</Message>}
    {error && <Message error>{error}。你的表单修改仍然保留。{conflict && <button className="link" onClick={() => void readLatest()}>读取最新版本</button>}</Message>}
    {content && <div className="editor-columns">
      <div className="structured-editor"><fieldset className="editor-form" disabled={locked || busy || working}><Fields value={content} onChange={v => setContent(v as Record<string, unknown>)} label="平台内容" /><label>本次修改说明<input maxLength={500} value={reason} onChange={e => setReason(e.target.value)} placeholder="为什么保留这处修改？" /></label></fieldset>
        <div className="action-row">{!locked && <button className="primary" disabled={!dirty || busy || working} onClick={() => void save()}>{working ? '处理中…' : '保存平台版本'}</button>}{selected === 'wechat' && artifact?.current_revision_id && <button className="secondary" disabled={dirty || working} onClick={() => void saveAsWechatDraft()}>保存为本地公众号草稿</button>}<button className="secondary" disabled={working} onClick={() => void readHistory()}>查看版本历史</button><button className="link" disabled={working} onClick={() => exportArtifact(artifact!.id, 'markdown')}>导出 Markdown</button><button className="link" disabled={working} onClick={() => exportArtifact(artifact!.id, 'json')}>导出 JSON</button><button className="link" disabled={working} onClick={() => exportArtifact(artifact!.id, 'html')}>导出 HTML</button></div>
        {selected === 'wechat' && <p className="field-help">只能从当前已保存的公众号版本转入；当前有未保存修改时先保存版本。该动作只保存到知序本地草稿，不调用微信接口。</p>}
        {memory && <div className="memory-inline"><span className="kicker">写作偏好建议 · {stateName(memory.confirmation_status)}</span><p>{memory.statement}</p><button className="secondary" onClick={() => navigate('profile')}>查看写作偏好</button></div>}
      </div>
      <div className="preview"><div className="preview-title"><strong>阅读预览</strong><small>{artifact?.current_revision?.generation_kind === 'user_edit' ? '用户编辑版本' : '本地模板草稿'}</small></div><ReadFields value={content} /></div>
    </div>}
    {history.length > 0 && <div className="history-detail"><h3>平台版本历史</h3>{history.map(row => <details key={row.id}><summary>v{row.revision_no} · {dateLabel(row.created_at)} · {row.generation_kind === 'user_edit' ? '用户编辑' : '本地模板'}</summary>{row.edits.map(edit => <p key={edit.id}><code>{edit.path}</code>：{JSON.stringify(edit.before)} → {JSON.stringify(edit.after)}<small>{edit.reason}</small></p>)}<details><summary>查看这一版本的全文</summary><ReadFields value={row.content} /></details></details>)}</div>}
  </section>;
}
