import { useEffect, useRef, useState } from 'react';
import { fetchWorkflowStatus, startWorkflow } from '../lib/api';
import type { WorkflowStatus } from '../lib/api';

const PLATFORMS = ['公众号', '掘金', '小红书'];

interface WorkflowPageProps { persona: string; }

export default function WorkflowPage({ persona }: WorkflowPageProps) {
  const [topic, setTopic] = useState('');
  const [platforms, setPlatforms] = useState(PLATFORMS);
  const [status, setStatus] = useState<WorkflowStatus | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => () => { if (timer.current) clearInterval(timer.current); }, []);

  const poll = (id: string) => {
    if (timer.current) clearInterval(timer.current);
    const tick = () => fetchWorkflowStatus(id).then((next) => {
      setStatus(next);
      if (next.state === 'done' || next.state === 'failed') {
        if (timer.current) clearInterval(timer.current);
        timer.current = null;
        setBusy(false);
      }
    }).catch((e) => setError(e instanceof Error ? e.message : '读取工作流状态失败'));
    tick();
    timer.current = setInterval(tick, 2000);
  };

  const run = async () => {
    const value = topic.trim();
    if (!value) { setError('请先填写主题'); return; }
    if (!platforms.length) { setError('至少选择一个目标平台'); return; }
    setError(''); setBusy(true); setStatus(null);
    try {
      const r = await startWorkflow({ topic: value, platforms, persona: persona || undefined });
      poll(r.id);
    } catch (e) {
      setBusy(false); setError(e instanceof Error ? e.message : '启动工作流失败');
    }
  };

  const toggle = (platform: string) => {
    setPlatforms((current) => current.includes(platform)
      ? current.filter((x) => x !== platform)
      : [...current, platform]);
  };

  return (
    <div className="page-scroll workflow-page">
      <div className="workflow-content">
      <div className="workflow-hero">
        <div><div className="eyebrow"><span className="eyebrow-dot" />内容生产线</div>
        <h1 className="page-title">把一个想法，做成一组内容</h1>
        <p className="page-subtitle">从线索核查到平台成稿，随波逐流帮你把每一步留下来。</p></div>
        <div className="workflow-hero-badge"><strong>6</strong><span>个阶段</span></div>
      </div>

      <div className="workflow-grid">
      <div className="card workflow-form-card" style={{ padding: 28, marginTop: 22 }}>
        <div className="section-kicker">从这里开始</div>
        <h2>这次想完成什么？</h2>
        <p className="card-lead">写下一个主题、问题或灵感，剩下的交给工作流。</p>
        <label className="field-label" htmlFor="workflow-topic">主题</label>
        <textarea
          id="workflow-topic"
          className="workflow-topic-input"
          value={topic}
          onChange={(e) => setTopic(e.target.value)}
          placeholder="例如：OpenAI 新模型对普通开发者有什么影响？"
          rows={4}
          disabled={busy}
        />
        <div className="field-label platform-label">交付到哪些平台</div>
        <div className="platform-picker">
          {PLATFORMS.map((platform) => (
            <button key={platform} className={`platform-pill ${platforms.includes(platform) ? 'selected' : ''}`}
              onClick={() => toggle(platform)} disabled={busy}
              aria-pressed={platforms.includes(platform)}>
              {platforms.includes(platform) ? '✓ ' : ''}{platform}
            </button>
          ))}
        </div>
        <div className="workflow-note">
          默认自动做到“发布前”。公众号、小红书发布仍需你确认；掘金生成成稿后人工发布，不伪造自动登录。
        </div>
        <button className="btn btn-primary workflow-run-btn" onClick={run}
          disabled={busy || !topic.trim() || platforms.length === 0}
          aria-describedby={error ? 'workflow-error' : undefined}>
          {busy ? '工作流执行中…' : '开始自动执行'} <span className="btn-arrow">→</span>
        </button>
        {error && <div id="workflow-error" className="workflow-error" role="alert"><span>!</span>{error}</div>}
      </div>

      <aside className="card workflow-stage-card">
        <div className="section-kicker">执行路径</div>
        <h2>六步完成</h2>
        <p className="card-lead">每一步都会留下文件，失败也不会丢。</p>
        <div className="stage-list">
          {['发现与核查', '选题与结构', '生成母稿', '平台改编', '质量检查', '归档交付'].map((label, index) => (
            <div className="stage-item" key={label}><span className="stage-index">{index + 1}</span><span className="stage-copy"><strong>{label}</strong><small>{['找线索，核来源', '定角度，搭骨架', '把想法写完整', '适配不同读者', '事实与表达复核', '留下可复用资产'][index]}</small></span></div>
          ))}
        </div>
      </aside>
      </div>

      {status && (
        <div className="card workflow-result-card" style={{ padding: 24, marginTop: 18 }}>
          <div className="result-head">
            <div><div className="section-kicker">实时进度</div><strong>{status.topic}</strong><div className="result-message">{status.message || status.current_name || '准备中…'}</div></div>
            <span className={`badge ${status.state === 'done' ? 'badge-ok' : ''}`}>{status.state === 'done' ? '已完成' : status.state === 'failed' ? '已阻断' : '执行中'}</span>
          </div>
          <div className="stage-list">
            {(['discover', 'plan', 'produce', 'adapt', 'quality', 'package']).map((key) => {
              const step = status.steps.find((s) => s.key === key);
              const label = ({ discover: '发现与核查', plan: '选题与结构', produce: '生成母稿', adapt: '平台改编', quality: '质量检查', package: '归档交付' } as Record<string, string>)[key];
              return <div key={key} className={`stage-item ${step?.state || 'idle'}`}>
                <span className="stage-index">{step?.state === 'done' ? '✓' : step?.state === 'failed' ? '!' : step?.state === 'running' ? '…' : '○'}</span>
                <span className="stage-copy"><strong>{label}</strong>{step?.state === 'running' && <small>处理中</small>}</span>
              </div>;
            })}
          </div>
          {status.topic_dir && <div className="result-path">产物目录：<code>outputs/{status.topic_dir}</code></div>}
          {status.error && <pre className="workflow-error-detail">{status.error}</pre>}
        </div>
      )}
      </div>
    </div>
  );
}
