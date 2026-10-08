import { useEffect, useState } from 'react';
import { ApiError, listQuickDrafts, type QuickDraft } from './api';
import { Message, errorText } from './components/shared';
import { StudioIcon } from './components/StudioIcon';

type Draft = {
  id: string;
  topic: string;
  title?: string;
  context?: string;
  source?: string;
  sourceUrl?: string;
  platform: string;
  mode: string;
  skill: string;
  output: string;
  createdAt: number;
  workflowId?: string | null;
  workflowArtifact?: string | null;
  taskId?: string | null;
  inputVersion?: number;
  persistenceState?: 'saved_input' | 'local_only';
};

const platformLabels: Record<string, string> = { wechat: '公众号', xiaohongshu: '小红书', douyin: '抖音' };
const modeLabels: Record<string, string> = { '文章': '文章', '配图': '配图方案', '内容+配图': '内容 + 配图方案' };

const readLocalDrafts = (): Draft[] => {
  try {
    const rows = JSON.parse(window.localStorage.getItem('creatoros:quick-drafts') || '[]');
    return Array.isArray(rows) ? rows : [];
  } catch {
    return [];
  }
};

const writeLocalDrafts = (rows: Draft[]) => {
  try {
    window.localStorage.setItem('creatoros:quick-drafts', JSON.stringify(rows));
    return true;
  } catch {
    return false;
  }
};

const fromServer = (row: QuickDraft): Draft => ({
  id: row.quick_draft_id,
  topic: row.title,
  title: row.title,
  context: row.context || "",
  source: typeof row.source?.label === 'string'
    ? row.source.label
    : typeof row.source?.url === 'string' ? row.source.url : '',
  sourceUrl: typeof row.source?.url === 'string' ? row.source.url : '',
  platform: row.platform,
  mode: row.mode,
  skill: row.skill,
  output: row.output,
  createdAt: new Date(row.updated_at || row.created_at).getTime() || Date.now(),
  workflowId: row.workflow_id,
  workflowArtifact: row.output_artifact,
  taskId: row.task_id,
  inputVersion: row.input_version,
  persistenceState: 'saved_input',
});

const libraryErrorText = (error: unknown) => {
  if (error instanceof ApiError && error.status === 404) {
    return '内容服务没有提供内容库接口。通常是后端进程还没重启，或当前页面没有连到 8000 端口；请重启知序后端后刷新。';
  }
  if (error instanceof ApiError && error.status >= 500) {
    return '内容服务暂时异常，请重启知序后端后刷新。未同步的本机草稿仍会保留。';
  }
  return `服务端内容暂时无法读取：${errorText(error)}`;
};

export function StudioLibraryPage({ navigate }: { navigate: (path: string) => void }) {
  const [drafts, setDrafts] = useState<Draft[]>([]);
  const [selected, setSelected] = useState<Draft | null>(null);
  const [loadError, setLoadError] = useState('');
  const [reloadToken, setReloadToken] = useState(0);

  useEffect(() => {
    let mounted = true;
    const localRows = readLocalDrafts();
    setDrafts(localRows);
    void listQuickDrafts().then(serverRows => {
      if (!mounted) return;
      const merged = new Map<string, Draft>(serverRows.map(row => [row.quick_draft_id, fromServer(row)]));
      localRows.forEach(row => {
        const local = { ...row, persistenceState: row.persistenceState || 'local_only' } as Draft;
        const server = merged.get(row.id);
        // A failed sync leaves a local-only copy with the same id as an older
        // server version. Keep the newer local work visible after a reload.
        if (!server || (local.persistenceState === 'local_only' && local.createdAt > server.createdAt)) merged.set(row.id, local);
      });
      const next = Array.from(merged.values()).sort((a, b) => b.createdAt - a.createdAt);
      setDrafts(next);
      setSelected(current => current ? next.find(row => row.id === current.id) || current : null);
      setLoadError('');
    }).catch(error => { if (mounted) setLoadError(libraryErrorText(error)); });
    return () => { mounted = false; };
  }, [reloadToken]);

  const removeLocalCopy = (id: string) => {
    const next = readLocalDrafts().filter(item => item.id !== id);
    if (!writeLocalDrafts(next)) {
      setLoadError('本机存储暂时不可写，未能移除副本；请检查浏览器存储权限后重试。');
      return;
    }
    setDrafts(rows => rows.filter(item => item.id !== id));
    if (selected?.id === id) setSelected(null);
  };

  const continueEditing = (draft: Draft) => {
    // Keep the hand-off envelope complete even when it came from an older
    // local-only schema that used `title` instead of `topic`.
    const topic = (draft.topic || draft.title || '').trim();
    const envelope = { ...draft, topic: topic || '未命名草稿', title: topic || '未命名草稿' };
    try {
      window.localStorage.setItem('creatoros:editing-draft', JSON.stringify(envelope));
    } catch {
      setLoadError('本机存储暂时不可写，无法打开编辑器；请检查浏览器存储权限后重试。');
      return;
    }
    navigate('create');
  };

  const startNew = () => {
    try {
      for (const key of ['creatoros:editing-draft', 'creatoros:selected-hotspot', 'creatoros:compose-form']) {
        window.localStorage.removeItem(key);
      }
    } catch {
      setLoadError('本机存储暂时不可写，已打开空白创作页；本次内容不会自动恢复。');
    }
    navigate('create');
  };

  return <>
    <div className="studio-page-heading library-heading"><div><h1>我的内容</h1><p>服务端保存的内容会在刷新后继续出现；尚未同步的草稿仍保留在本机。</p></div><button className="primary" onClick={startNew}><StudioIcon name="plus" size={16} />开始新创作</button></div>
    {loadError && <Message error><span>{loadError}</span><button className="link" onClick={() => setReloadToken(value => value + 1)}>重试</button></Message>}
    {drafts.length ? <div className="library-studio-layout"><section className="library-draft-list"><div className="library-list-meta"><span>{drafts.length} 个快速草稿</span><span>服务端内容 + 本机恢复</span></div>{drafts.map(item => <button key={item.id} className={`library-draft-row ${selected?.id === item.id ? 'selected' : ''}`} onClick={() => setSelected(item)}><span className="library-draft-icon"><StudioIcon name={item.mode === '配图' ? 'image' : 'file'} size={18} /></span><span><strong>{item.topic}</strong><small>{platformLabels[item.platform] || item.platform} · {modeLabels[item.mode] || item.mode} · {item.persistenceState === 'saved_input' ? `内容库第 ${item.inputVersion || 1} 版` : '仅保存在本机'}</small></span><StudioIcon name="chevron" size={15} /></button>)}</section><section className="library-draft-detail">{selected ? <><div className="detail-top"><div><span className="detail-tag">{platformLabels[selected.platform] || selected.platform} · {modeLabels[selected.mode] || selected.mode}</span><h2>{selected.topic}</h2><p>使用能力：{selected.skill} · {new Date(selected.createdAt).toLocaleString('zh-CN')}</p></div>{selected.persistenceState === 'local_only' && <button className="quiet-button" onClick={() => removeLocalCopy(selected.id)}>移除本机副本</button>}</div>{selected.persistenceState === 'saved_input' && <p className="hint">已保存为内容库输入，第 {selected.inputVersion || 1} 版；它仍是可编辑草稿，尚未提交平台。</p>}<pre>{selected.output}</pre><div className="detail-actions"><button className="primary" onClick={() => continueEditing(selected)}>继续编辑</button><button className="secondary" onClick={() => { const blob = new Blob([selected.output], { type: 'text/markdown;charset=utf-8' }); const link = document.createElement('a'); link.href = URL.createObjectURL(blob); link.download = `${selected.topic.slice(0, 24) || 'creatoros-草稿'}.md`; link.click(); URL.revokeObjectURL(link.href); }}><StudioIcon name="download" size={15} />下载 Markdown</button></div></> : <div className="library-detail-empty"><StudioIcon name="file" size={28} /><h2>选择一篇内容</h2><p>查看草稿全文，继续修改或下载。</p></div>}</section></div> : <div className="studio-empty"><span className="empty-mark"><StudioIcon name="pen" size={24} /></span><h2>还没有保存的内容</h2><p>从热点开始，生成你的第一篇文章或一组配图方案。</p><button className="primary" onClick={() => navigate('hotspots')}>去看热点<StudioIcon name="arrow" size={16} /></button></div>}
  </>;
}
