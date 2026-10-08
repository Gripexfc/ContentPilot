import { useEffect, useMemo, useState } from 'react';
import { fetchWorkflows, fetchWorkflow, retryWorkflow, startWorkflow } from '../lib/api';
import type { WorkflowJob } from '../lib/api';

const STAGES = [
  ['discovery', '发现与核验'], ['topic', '选题与结构'], ['master', '主稿'],
  ['adaptation', '三平台适配'], ['quality', '质量检查'], ['archive', '归档交付'],
] as const;
const TARGETS = [
  ['xiaohongshu', '小红书'], ['douyin', '抖音'], ['wechat-oa', '公众号'],
] as const;

export default function WorkflowPage({ persona }: { persona: string }) {
  const [topic, setTopic] = useState('');
  const [targets, setTargets] = useState<string[]>(TARGETS.map(([key]) => key));
  const [job, setJob] = useState<WorkflowJob | null>(null);
  const [error, setError] = useState('');
  const busy = job?.status === 'running' || job?.status === 'queued';
  useEffect(() => { fetchWorkflows().then(jobs => { if (jobs[0]) { setJob(jobs[0]); setTopic(jobs[0].topic); setTargets(jobs[0].platforms); } }).catch(e => setError(String(e))); }, []);

  useEffect(() => {
    if (!job || !busy) return;
    const timer = window.setInterval(() => {
      fetchWorkflow(job.id).then(setJob).catch(e => setError(String(e)));
    }, 700);
    return () => window.clearInterval(timer);
  }, [job?.id, busy]);

  const statusText = useMemo(() => {
    if (!job) return '一次启动六阶段，状态会持续保存，可在失败后重试。';
    if (job.status === 'blocked') return '已阻断：缺少真实模型或研究网关，未生成模拟内容。';
    if (job.status === 'failed' || job.status === 'interrupted') return '执行失败或中断，已有产物保留，可从失败阶段重试。';
    if (job.status === 'completed') return '草稿已归档，事实、媒体和真人表达仍需人工审校。';
    return '正在执行，离开页面后可返回继续查看。';
  }, [job]);

  const run = async () => {
    if (!topic.trim() || !targets.length) return;
    setError('');
    try { setJob(await startWorkflow(topic.trim(), targets, persona)); }
    catch (e) { setError(e instanceof Error ? e.message : '工作流启动失败'); }
  };

  const retry = async () => {
    if (!job) return;
    setError('');
    try { setJob(await retryWorkflow(job.id)); }
    catch (e) { setError(e instanceof Error ? e.message : '重试失败'); }
  };

  return <div className="page workflow-page">
    <div className="page-header"><div><h2>一键工作流</h2><p className="muted">发现 → 选题 → 主稿 → 三平台适配 → 质量检查 → 归档交付</p></div></div>
    <section className="card" style={{ maxWidth: 760 }}>
      <label className="field-label" htmlFor="workflow-topic">主题或原始线索</label>
      <textarea id="workflow-topic" className="textarea" rows={4} value={topic} onChange={e => setTopic(e.target.value)} placeholder="输入一个主题、链接或需要核验的线索" disabled={busy} />
      <div className="field-label" style={{ marginTop: 18 }}>发布目标（只支持三端）</div>
      <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>{TARGETS.map(([key, label]) => <label key={key} className="checkbox-label"><input type="checkbox" checked={targets.includes(key)} disabled={busy} onChange={e => setTargets(v => e.target.checked ? [...v, key] : v.filter(x => x !== key))} /> {label}</label>)}</div>
      <div style={{ display: 'flex', gap: 10, marginTop: 18 }}><button className="btn btn-primary" disabled={busy || !topic.trim() || !targets.length} onClick={run}>{busy ? '执行中…' : '开始六阶段工作流'}</button>{job && ['blocked', 'failed', 'interrupted'].includes(job.status) && <button className="btn" onClick={retry}>重试</button>}</div>
      {error && <div className="error-text" role="alert">{error}</div>}
    </section>
    <section className="card" style={{ maxWidth: 760, marginTop: 16 }} aria-live="polite"><div className="workflow-status">{statusText}</div>{job && <div className="workflow-stages">{STAGES.map(([key, label], index) => { const stage = job.stages[key]; return <div className={`workflow-stage ${stage?.status || 'pending'}`} key={key}><div className="workflow-stage-index">{index + 1}</div><div><strong>{label}</strong><div className="muted">{stage?.status === 'completed' ? '已完成' : stage?.status === 'running' ? '执行中' : stage?.status === 'blocked' ? 'BLOCKED' : '等待中'}</div>{stage?.artifact && <a href={`#/outputs/${encodeURIComponent(stage.artifact)}`}>查看本阶段产物</a>}{stage?.reason && <div className="error-text">{stage.reason}</div>}</div></div>; })}</div>}</section>
  </div>;
}
