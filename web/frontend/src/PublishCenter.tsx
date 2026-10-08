import { useEffect, useMemo, useState } from 'react';
import { createWechatDraftFromArtifact, getContentTask, listConnectors, listContentTasks, type Artifact, type ConnectorState, type ContentTask, type ContentTaskDetail } from './api';
import { connectorStateName, dateLabel, Empty, errorText, Message, PageHeader, stateName } from './components/shared';

type Navigate = (path: string) => void;
const platformName = (platform: string) => platform === 'wechat' ? '公众号' : platform === 'xiaohongshu' ? '小红书' : '抖音';
const platformClass = (platform: string) => platform === 'wechat' ? 'wechat' : platform === 'xiaohongshu' ? 'xhs' : 'douyin';
const artifactTitle = (artifact: Artifact) => {
  const content = artifact.current_revision?.content ?? {};
  const candidates = Array.isArray(content.title_candidates) ? content.title_candidates : [];
  return String(content.title ?? candidates[0] ?? '未命名版本');
};

/** Easel 发布中心的本地版本：集中查看三平台版本，再明确进入真实账号动作。 */
export function PublishCenterPage({ initialTaskId, navigate }: { initialTaskId?: string; navigate: Navigate }) {
  const [tasks, setTasks] = useState<ContentTask[]>([]);
  const [detail, setDetail] = useState<ContentTaskDetail | null>(null);
  const [connectors, setConnectors] = useState<ConnectorState[]>([]);
  const [notice, setNotice] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  const refresh = async (taskId?: string) => {
    const next = await listContentTasks();
    setTasks(next);
    const target = taskId || detail?.task.id || next[0]?.id;
    if (target) setDetail(await getContentTask(target));
    else setDetail(null);
  };
  useEffect(() => {
    void Promise.all([refresh(initialTaskId), listConnectors().then(setConnectors)]).catch(e => setError(errorText(e)));
  }, [initialTaskId]);

  const connectorByPlatform = useMemo(() => new Map(connectors.map(item => [item.platform, item])), [connectors]);
  const action = async (artifact: Artifact) => {
    if (!artifact.current_revision_id) return;
    setBusy(true); setError(''); setNotice('');
    try {
      if (artifact.platform === 'wechat') {
        const draft = await createWechatDraftFromArtifact(artifact.id, artifact.current_revision_id);
        navigate(`drafts/${draft.id}`);
        setNotice(`已转入本地公众号草稿 ${draft.id.slice(0, 8)}，未调用微信发布接口。`);
      } else {
        const connector = connectorByPlatform.get(artifact.platform);
        setNotice(connector?.state === 'read_succeeded' || connector?.state === 'submit_succeeded'
          ? `${platformName(artifact.platform)}已具备本地连接状态，请人工确认后提交。`
          : `${platformName(artifact.platform)}尚未连接；先去账号完成连接和读取。`);
      }
    } catch (e) { setError(errorText(e)); }
    finally { setBusy(false); }
  };

  return <>
    <PageHeader title="发布中心" description="把已确认的版本交付到公众号、小红书和抖音。这里保留每个平台的独立状态，真实发布始终需要账号连接和你的确认。">
      <button className="secondary" onClick={() => void refresh()}>刷新版本</button>
    </PageHeader>
    {notice && <Message>{notice}</Message>}
    {error && <Message error>{error}</Message>}
    <div className="publish-layout">
      <section className="panel publish-projects">
        <div className="section-title"><div><span className="kicker">内容项目</span><h2>{tasks.length ? `${tasks.length} 个项目` : '还没有项目'}</h2></div><button className="primary" onClick={() => navigate('workspace')}>新建内容</button></div>
        {tasks.length ? tasks.map(task => <button className={`task-line ${detail?.task.id === task.id ? 'selected' : ''}`} key={task.id} onClick={() => void getContentTask(task.id).then(setDetail).catch(e => setError(errorText(e)))}><span><strong>{task.title}</strong><small>{stateName(task.status)} · {dateLabel(task.updated_at)}</small></span><b>→</b></button>) : <Empty title="还没有可发布内容">先从一键工作流创建主题，确认写作计划并生成三平台版本。</Empty>}
      </section>
      <section className="panel publish-detail">
        {detail ? <>
          <div className="panel-title"><div><span className="kicker">发布前检查</span><h2>{detail.task.title}</h2></div><button className="secondary" onClick={() => navigate(`workspace/${detail.task.id}`)}>打开编辑</button></div>
          <div className="publish-checks"><span className={detail.latest_brief?.confirmation_status === 'confirmed' ? 'check ok' : 'check'}>写作计划 {detail.latest_brief?.confirmation_status === 'confirmed' ? '已确认' : '待确认'}</span><span className={detail.artifacts.length === 3 ? 'check ok' : 'check'}>三平台版本 {detail.artifacts.length}/3</span><span className="check">AI/素材：本地模板</span></div>
          {detail.artifacts.length === 0 ? <Empty title="还没有平台版本">回到工作流确认写作计划后，创建公众号、小红书、抖音三份独立版本。</Empty> : <div className="publish-platform-grid">{(['wechat', 'xiaohongshu', 'douyin'] as const).map(platform => {
            const artifact = detail.artifacts.find(item => item.platform === platform);
            const connector = connectorByPlatform.get(platform);
            return <article className={`publish-platform-card ${platformClass(platform)}`} key={platform}>
              <div className="publish-platform-head"><div><span className="kicker">{platformName(platform)}</span><h3>{artifact ? artifactTitle(artifact) : '尚未生成'}</h3></div><span className="status-pill">{artifact ? stateName(artifact.status) : '待生成'}</span></div>
              <p>{artifact ? `版本 ${artifact.current_revision?.revision_no ?? 0} · ${artifact.current_revision?.generation_kind === 'user_edit' ? '已编辑' : '本地模板'}` : '完成写作计划后生成'}</p>
              <div className="publish-platform-foot"><small>{connector ? `账号：${connectorStateName(connector.state)}` : '账号：未读取'}</small>{artifact && <button className="secondary" disabled={busy || !artifact.current_revision_id} onClick={() => void action(artifact)}>{platform === 'wechat' ? '转为公众号草稿' : '检查发布条件'}</button>}</div>
            </article>;
          })}</div>}
        </> : <Empty title="选择一个内容项目">查看三平台独立版本和发布前状态。</Empty>}
      </section>
    </div>
  </>;
}
