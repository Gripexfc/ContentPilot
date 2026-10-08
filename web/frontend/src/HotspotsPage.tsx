import { useCallback, useEffect, useRef, useState } from 'react';
import { createHotspot, getTrends, listHotspots, type Hotspot, type TrendBoard, type TrendItem, type TrendSourceKey } from './api';
import { Message, errorText } from './components/shared';
import { StudioIcon } from './components/StudioIcon';

const SOURCES: { key: TrendSourceKey; label: string; mark: string; description: string }[] = [
  { key: 'douyin', label: '抖音', mark: '抖', description: '捕捉正在发生的流行' },
  { key: 'weibo', label: '微博', mark: '微', description: '发现大家关心的新鲜事' },
  { key: 'zhihu', label: '知乎', mark: '知', description: '从好问题找到好角度' },
];
const statusLabel = { fresh: '已更新', cached: '已缓存', stale: '更新失败 · 旧榜单', unavailable: '暂不可用' };
const safeLink = (url: string) => /^https?:\/\//i.test(url) ? url : undefined;

function FeedSkeleton() {
  return <div className="feed-skeleton-list" aria-label="正在加载热点" role="status">
    {Array.from({ length: 5 }, (_, index) => <div className="feed-skeleton-row" key={index}><span /><div><i /><i /><b /></div></div>)}
  </div>;
}

export function HotspotsPage({ navigate }: { navigate: (path: string) => void }) {
  const [boards, setBoards] = useState<TrendBoard[]>([]);
  const [saved, setSaved] = useState<Hotspot[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [query, setQuery] = useState('');
  const [source, setSource] = useState<TrendSourceKey | 'all'>('all');
  const [expanded, setExpanded] = useState<string[]>([]);
  const controller = useRef<AbortController>();
  const load = useCallback(async (refresh = false) => {
    controller.current?.abort(); const abort = new AbortController(); controller.current = abort;
    setLoading(true); setError('');
    try { const response = await getTrends(SOURCES.map(row => row.key), refresh, abort.signal); if (!abort.signal.aborted) setBoards(response.trends); }
    catch (e) { if (!abort.signal.aborted) setError(`热点读取失败：${errorText(e)}`); }
    finally { if (!abort.signal.aborted) setLoading(false); }
  }, []);
  useEffect(() => { void load(); void listHotspots().then(setSaved).catch(e => setError(errorText(e))); return () => controller.current?.abort(); }, [load]);
  const selectTopic = (row: { title: string; summary: string; canonical_url: string; source_name: string }) => {
    window.localStorage.setItem('creatoros:selected-hotspot', JSON.stringify({ title: row.title, summary: row.summary, url: row.canonical_url, source: row.source_name }));
    window.localStorage.removeItem('creatoros:editing-draft'); window.localStorage.removeItem('creatoros:compose-form'); navigate('create');
  };
  const choose = async (board: TrendBoard, item: TrendItem) => {
    if (busy) return;
    const existing = saved.find(value => value.canonical_url === item.url);
    // 先把选题交给创作页，再尝试写入热点库。这样本地 API 暂时不可用时，
    // “写这个”仍然能完成用户最直接的下一步。
    const selected = existing || {
      title: item.title,
      canonical_url: item.url,
      source_name: `${board.label}热榜`,
      summary: item.summary,
    };
    selectTopic(selected);
    if (existing) return;
    setBusy(true); setError('');
    try {
      const row = await createHotspot({ title: item.title, canonical_url: item.url, source_name: `${board.label}热榜`, source_kind: 'hotlist', summary: item.summary, fact_status: 'unverified', heat_status: 'listed', relevance_reason: '', platform_fit: {}, needs_human_review: true, evidence: [{ evidence_type: 'hotlist', source_url: board.source_url || item.url, claim: `收录于${board.label}热榜`, value: { rank: item.rank, hot: item.hot, fetched_at: board.fetched_at }, verification_status: 'unverified' }] });
      setSaved(current => [row, ...current.filter(value => value.canonical_url !== row.canonical_url)]);
    } catch (e) {
      // 选题内容已经写入本地创作页，保存失败只作为提示，不阻断创作。
      setError(`已进入创作页，热点暂未同步：${errorText(e)}`);
    } finally { setBusy(false); }
  };
  const startBlank = () => { window.localStorage.removeItem('creatoros:selected-hotspot'); window.localStorage.removeItem('creatoros:editing-draft'); window.localStorage.removeItem('creatoros:compose-form'); navigate('create'); };
  return <>
    <div className="studio-page-heading"><div><h1>今天，想写点什么？</h1><p>发现值得聊的话题，把一时的灵感变成你的下一篇内容。</p></div><button className="secondary" disabled={loading} onClick={() => void load(true)}><StudioIcon name="refresh" size={16} />{loading ? '更新中' : '刷新热点'}</button></div>
    <div className="inspiration-strip"><div className="strip-mark"><StudioIcon name="pen" size={22} /></div><div><strong>已经有一个想法？</strong><p>写下一句话，交给创作助手展开。</p></div><button className="text-action" onClick={startBlank}>直接创作<StudioIcon name="arrow" size={17} /></button></div>
    {error && <Message error>{error}<button className="link" onClick={() => void load(true)}>重新加载</button></Message>}
    <div className="discovery-toolbar"><div className="source-tabs" aria-label="筛选热点来源">{[{ key: 'all', label: '全部热点' }, ...SOURCES].map(row => <button key={row.key} aria-pressed={source === row.key} className={source === row.key ? 'active' : ''} onClick={() => setSource(row.key as typeof source)}>{row.label}</button>)}</div><label className="studio-search"><StudioIcon name="search" size={17} /><input aria-label="搜索热点" placeholder="搜索感兴趣的话题" value={query} onChange={e => setQuery(e.target.value)} /></label></div>
    <section className={`discovery-grid ${source !== 'all' ? 'single-source' : ''}`} aria-label="实时热榜" aria-busy={loading}>
      {SOURCES.filter(s => source === 'all' || s.key === source).map(s => {
        const board = boards.find(b => b.platform === s.key);
        const filtered = (board?.items || []).filter(item => item.title.toLowerCase().includes(query.trim().toLowerCase()));
        const visible = expanded.includes(s.key) || query ? filtered : filtered.slice(0, 6);
        return <article className="discovery-board" key={s.key}>
          <header className="discovery-board-head"><span className={`source-mark ${s.key}`}>{s.mark}</span><div><h2>{s.label}热榜</h2><p>{s.description}</p></div><span className={`feed-status ${board?.status === 'stale' || board?.status === 'unavailable' ? 'warning' : ''}`}>{loading ? '读取中' : statusLabel[board?.status || 'unavailable']}</span></header>
          <ol className="discovery-list">{visible.map(item => <li key={item.id}>
            <span className={`discovery-rank ${item.rank <= 3 ? 'rank-top' : ''}`}>{String(item.rank).padStart(2, '0')}</span>
            <div className="discovery-row-content"><a href={safeLink(item.url)} target="_blank" rel="noreferrer">{item.title}</a><div className="discovery-row-bottom"><span>{item.hot ? `${item.hot} · 热度` : '热度未提供'}</span><button disabled={busy} onClick={() => board && void choose(board, item)} aria-label={`创作：${item.title}`}>写这个<StudioIcon name="arrow" size={14} /></button></div></div>
          </li>)}</ol>
          {!visible.length && (loading ? <FeedSkeleton /> : <div className="feed-empty">{query ? '没有匹配的话题，换个关键词试试。' : '这个来源暂时不可用，可以尝试其他来源。'}</div>)}
          <footer className="discovery-board-foot"><span>{board?.fetched_at ? `${new Date(board.fetched_at).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })} 获取` : '等待更新'}</span>{filtered.length > 6 && !query && <button onClick={() => setExpanded(rows => rows.includes(s.key) ? rows.filter(key => key !== s.key) : [...rows, s.key])}>{expanded.includes(s.key) ? '收起' : '更多话题'}<StudioIcon name="chevron" size={13} /></button>}</footer>
        </article>;
      })}
    </section>
    <p className="source-disclaimer"><StudioIcon name="link" size={14} />热点来自公开榜单，仅作选题线索；点击话题标题可查看原始来源。</p>
    <section className="recent-topics"><div className="studio-section-heading"><h2>接着上次的灵感</h2><span>{saved.length ? `${saved.length} 个已选话题` : '选过的话题会留在这里'}</span></div>{saved.length ? <div className="recent-topic-list">{saved.slice(0, 3).map(row => <button key={row.id} onClick={() => selectTopic(row)}><StudioIcon name="file" size={18} /><span><strong>{row.title}</strong><small>{row.source_name}</small></span><StudioIcon name="arrow" size={16} /></button>)}</div> : <div className="quiet-empty">遇到喜欢的热点，点一下「写这个」。下次回来，还能继续。</div>}</section>
  </>;
}
