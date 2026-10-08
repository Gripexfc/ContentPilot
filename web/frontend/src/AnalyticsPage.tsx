import { useEffect, useRef, useState, type KeyboardEvent } from 'react';
import {
  getMetricSummary,
  getPerformanceInsights,
  getWechatAnalytics,
  importMetrics,
  listMetricImports,
  type MetricImport,
  type MetricSummary,
  type PerformanceInsights,
  type WechatAnalytics,
} from './api';
import { dateLabel, errorText, Message, PageHeader } from './components/shared';
import { StudioIcon } from './components/StudioIcon';

const platformLabel = (value: string) => value === 'wechat' ? '公众号' : value === 'xiaohongshu' ? '小红书' : value === 'douyin' ? '抖音' : value;

const platformOptions = [
  { value: 'wechat', label: '公众号', description: '微信公众平台' },
  { value: 'xiaohongshu', label: '小红书', description: '创作者平台' },
  { value: 'douyin', label: '抖音', description: '创作者服务中心' },
];

function PlatformDropdown({ value, disabled, onChange }: {
  value: string;
  disabled?: boolean;
  onChange: (value: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState(0);
  const rootRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const optionRefs = useRef<Array<HTMLButtonElement | null>>([]);
  const selectedIndex = Math.max(0, platformOptions.findIndex(option => option.value === value));
  const selected = platformOptions[selectedIndex];
  const menuId = 'analytics-platform-menu';

  useEffect(() => {
    if (!open) return undefined;
    const isInside = (target: EventTarget | null) => target instanceof Node && Boolean(rootRef.current?.contains(target));
    const closeWhenOutside = (event: PointerEvent) => { if (!isInside(event.target)) setOpen(false); };
    const closeWhenScrolled = (event: Event) => { if (!isInside(event.target)) setOpen(false); };
    document.addEventListener('pointerdown', closeWhenOutside);
    window.addEventListener('scroll', closeWhenScrolled, true);
    return () => {
      document.removeEventListener('pointerdown', closeWhenOutside);
      window.removeEventListener('scroll', closeWhenScrolled, true);
    };
  }, [open]);

  useEffect(() => { if (open) setActiveIndex(selectedIndex); }, [open, selectedIndex]);
  useEffect(() => {
    if (open) optionRefs.current[activeIndex]?.scrollIntoView?.({ block: 'nearest' });
  }, [activeIndex, open]);

  const choose = (nextValue: string, index: number) => {
    onChange(nextValue);
    setActiveIndex(index);
    setOpen(false);
    requestAnimationFrame(() => triggerRef.current?.focus());
  };
  const openMenu = () => {
    if (disabled) return;
    setActiveIndex(selectedIndex);
    setOpen(true);
  };
  const handleKeyDown = (event: KeyboardEvent<HTMLButtonElement>) => {
    if (event.key === 'Escape') {
      if (open) { event.preventDefault(); setOpen(false); }
      return;
    }
    if (event.key === 'Tab') { if (open) setOpen(false); return; }
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault();
      if (!open) { openMenu(); return; }
      const direction = event.key === 'ArrowDown' ? 1 : -1;
      setActiveIndex(index => (index + direction + platformOptions.length) % platformOptions.length);
      return;
    }
    if (event.key === 'Home' && open) { event.preventDefault(); setActiveIndex(0); return; }
    if (event.key === 'End' && open) { event.preventDefault(); setActiveIndex(platformOptions.length - 1); return; }
    if ((event.key === 'Enter' || event.key === ' ') && open) {
      event.preventDefault();
      const option = platformOptions[activeIndex];
      if (option) choose(option.value, activeIndex);
    }
  };

  return <div className={`analytics-platform-select ${open ? 'is-open' : ''}`} ref={rootRef}>
    <button
      ref={triggerRef}
      type="button"
      className="analytics-platform-trigger"
      role="combobox"
      aria-haspopup="listbox"
      aria-expanded={open}
      aria-controls={menuId}
      aria-activedescendant={open ? `analytics-platform-option-${activeIndex}` : undefined}
      disabled={disabled}
      onClick={() => open ? setOpen(false) : openMenu()}
      onKeyDown={handleKeyDown}
    >
      <span className="analytics-platform-value"><strong>{selected.label}</strong><small>{selected.description}</small></span>
      <StudioIcon name="chevron-down" size={16} />
    </button>
    {open && <div id={menuId} className="analytics-platform-menu" role="listbox" aria-label="选择平台">
      {platformOptions.map((option, index) => <button
        id={`analytics-platform-option-${index}`}
        key={option.value}
        ref={node => { optionRefs.current[index] = node; }}
        type="button"
        role="option"
        aria-selected={option.value === value}
        className={index === activeIndex ? 'is-active' : ''}
        onMouseDown={event => event.preventDefault()}
        onMouseEnter={() => setActiveIndex(index)}
        onClick={() => choose(option.value, index)}
      >
        <span><strong>{option.label}</strong><small>{option.description}</small></span>
        {option.value === value && <StudioIcon name="check" size={16} />}
      </button>)}
    </div>}
  </div>;
}

const csvRows = (text: string): Record<string, unknown>[] => {
  const rows: string[][] = [];
  let row: string[] = [];
  let cell = '';
  let quoted = false;
  for (let i = 0; i < text.length; i += 1) {
    const char = text[i];
    const next = text[i + 1];
    if (char === '"' && quoted && next === '"') { cell += '"'; i += 1; continue; }
    if (char === '"') { quoted = !quoted; continue; }
    if (char === ',' && !quoted) { row.push(cell.trim()); cell = ''; continue; }
    if ((char === '\n' || char === '\r') && !quoted) {
      if (char === '\r' && next === '\n') i += 1;
      row.push(cell.trim());
      if (row.some(Boolean)) rows.push(row);
      row = [];
      cell = '';
      continue;
    }
    cell += char;
  }
  row.push(cell.trim());
  if (row.some(Boolean)) rows.push(row);
  const headers = rows.shift() ?? [];
  return rows.map(values => Object.fromEntries(headers.map((header, index) => [header, values[index] ?? ''])));
};

function IntegrationGuide() {
  const guides = [
    {
      platform: 'wechat', mark: '微', name: '公众号', note: '推荐官方接口；当前也可人工导出',
      steps: ['登录 mp.weixin.qq.com，进入“数据统计 / 内容分析”。', '选择复盘日期范围，导出图文阅读、分享、收藏等数据。', '回到本页“导入数据”，平台选“公众号”，上传 CSV/JSON。', '观察时间填平台数据对应日期，再点“导入并更新分析”。'],
      footer: '当前“读取公众号后台数据”是兼容路径；官方 API 接入完成后再作为默认同步方式。',
    },
    {
      platform: 'xiaohongshu', mark: '红', name: '小红书', note: '当前建议人工导出',
      steps: ['登录 creator.xiaohongshu.com，进入“数据中心 / 内容分析”。', '选择日期和笔记范围，导出阅读、点赞、收藏、评论等数据。', '回到本页“导入数据”，平台选“小红书”，上传 CSV/JSON。', '确认观察时间和标题后，点“导入并更新分析”。'],
      footer: '官方开放平台目前没有完整笔记表现数据接口，人工导入是可追溯的临时方案。',
    },
    {
      platform: 'douyin', mark: '音', name: '抖音', note: '当前建议人工导出',
      steps: ['登录 creator.douyin.com，进入“数据中心 / 作品分析”。', '选择日期和作品范围，导出播放、完播、点赞、评论等数据。', '回到本页“导入数据”，平台选“抖音”，上传 CSV/JSON。', '确认观察时间和标题后，点“导入并更新分析”。'],
      footer: 'OAuth/OpenAPI 是长期接入方向；当前不要把页面抓取当作定时同步。',
    },
  ];
  return <section className="analytics-card analytics-guide">
    <div className="analytics-section-heading">
      <div><span className="kicker">DATA ACCESS GUIDE</span><h2>三平台怎么把数据交给知序</h2></div>
      <span className="analytics-section-note">人工导入不会触碰账号登录态</span>
    </div>
    <p className="analytics-guide-intro">先在平台后台导出表现数据，再回到本页“导入数据”上传。平台后台的菜单名称可能随改版略有变化，按“数据中心 / 内容分析”一类入口查找即可。</p>
    <div className="analytics-guide-grid">
      {guides.map(guide => <article className="analytics-guide-card" key={guide.platform}>
        <div className="analytics-platform-head"><span className={`platform-mark ${guide.platform === 'xiaohongshu' ? 'xhs' : guide.platform}`}>{guide.mark}</span><div><strong>{guide.name}</strong><small>{guide.note}</small></div></div>
        <ol>{guide.steps.map(step => <li key={step}>{step}</li>)}</ol>
        <p>{guide.footer}</p>
      </article>)}
    </div>
    <p className="analytics-security-note">不要把密码、Cookie、AppSecret 粘贴到这里。导出的文件只在本机分析；数据缺失会保留为空，不会补成 0。</p>
  </section>;
}

export function AnalyticsPage() {
  const [summary, setSummary] = useState<MetricSummary | null>(null);
  const [insights, setInsights] = useState<PerformanceInsights | null>(null);
  const [imports, setImports] = useState<MetricImport[]>([]);
  const [wechatRead, setWechatRead] = useState<WechatAnalytics | null>(null);
  const [notice, setNotice] = useState('');
  const [busy, setBusy] = useState(false);
  const localDateTime = () => {
    const now = new Date();
    const pad = (value: number) => String(value).padStart(2, '0');
    return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}T${pad(now.getHours())}:${pad(now.getMinutes())}`;
  };
  const [platform, setPlatform] = useState('wechat');
  const [observedAt, setObservedAt] = useState(localDateTime);
  const [originalName, setOriginalName] = useState('manual.json');
  const [raw, setRaw] = useState('');
  const refresh = () => void Promise.all([getMetricSummary(), listMetricImports(), getPerformanceInsights()])
    .then(([nextSummary, nextImports, nextInsights]) => { setSummary(nextSummary); setImports(nextImports); setInsights(nextInsights); })
    .catch(error => setNotice(errorText(error)));
  useEffect(refresh, []);
  const importRows = async () => {
    try {
      setBusy(true);
      const text = raw.trim();
      const rows = text.startsWith('[') ? JSON.parse(text) as Record<string, unknown>[] : csvRows(text);
      if (!Array.isArray(rows) || !rows.length) throw new Error('没有解析到数据行');
      const sourceType = text.startsWith('[') ? 'manual_json' : 'manual_csv';
      const result = await importMetrics({ platform, source_type: sourceType, observed_at: new Date(observedAt).toISOString(), original_name: originalName, rows });
      setNotice(`已接收 ${result.row_count} 行${result.error?.warnings?.length ? `，${result.error.warnings.length} 行有警告` : ''}。这里只做结构性分析。`);
      setRaw('');
      refresh();
    } catch (error) {
      setNotice(errorText(error));
    } finally {
      setBusy(false);
    }
  };
  const readFile = async (file: File) => { setOriginalName(file.name); setRaw(await file.text()); };
  const readWechat = async () => {
    setBusy(true);
    setNotice('');
    try { setWechatRead(await getWechatAnalytics()); } catch (error) { setNotice(errorText(error)); } finally { setBusy(false); }
  };
  return <>
    <PageHeader title="账号分析" description="把各平台后台的表现数据放在同一处复盘。先看观察样本，再决定下一次内容实验。">
      <div className="analytics-header-actions">
        <button className="secondary" disabled={busy} onClick={() => void readWechat()}>读取公众号后台数据</button>
        <span className="state">CSV/JSON 可用 · 真实读取需 浏览器连接方式</span>
      </div>
    </PageHeader>
    <IntegrationGuide />
    {notice && <Message error={notice.includes('失败') || notice.includes('未')}>{notice}</Message>}
    {wechatRead && <section className="analytics-card analytics-read-card">
      <div className="analytics-section-heading"><div><span className="kicker">真实读取回执</span><h2>{wechatRead.posts} 篇发表记录</h2></div><span className="analytics-section-note">来源 {wechatRead.source} · {dateLabel(wechatRead.fetched_at)}</span></div>
      <div className="analytics-stat-list">{wechatRead.metrics.map(item => <div key={item.label}><span>{item.label}</span><strong>{item.value}</strong></div>)}</div>
      <div className="analytics-note-list">{wechatRead.limitations.map(item => <p key={item}>{item}</p>)}</div>
    </section>}
    <div className="analytics-workspace-grid">
      <section className="analytics-card analytics-import-card">
        <div className="analytics-section-heading"><div><span className="kicker">导入数据</span><h2>添加一次观察</h2></div><span className="analytics-section-note">支持 CSV 或 JSON</span></div>
        <div className="analytics-form-grid">
          <label>平台<PlatformDropdown value={platform} onChange={setPlatform} disabled={busy} /></label>
          <label>观察时间<input className="analytics-date-input" type="datetime-local" value={observedAt} onChange={event => setObservedAt(event.target.value)} disabled={busy} /></label>
          <label className="analytics-wide">选择文件<input type="file" accept=".csv,.json,application/json,text/csv" onChange={event => { const file = event.target.files?.[0]; if (file) void readFile(file); }} disabled={busy} /></label>
          <label className="analytics-wide">或粘贴数据<textarea rows={6} value={raw} onChange={event => setRaw(event.target.value)} placeholder={'CSV: title,pillar,阅读\n一次复盘,工程实践,1200\nJSON: [{"title":"一次复盘","pillar":"工程实践","阅读":1200}]'} disabled={busy} /></label>
        </div>
        <p className="analytics-field-help">每行至少提供 <code>title</code> 或 <code>content_ref</code>；其他列会原样保留为指标。缺失指标不会补成 0。</p>
        <button className="primary" disabled={busy || !raw.trim()} onClick={() => void importRows()}>{busy ? '导入中…' : '导入并更新分析'}</button>
      </section>
      <section className="analytics-card analytics-summary-card">
        <div className="analytics-section-heading"><div><span className="kicker">可解释摘要</span><h2>{summary?.observation_count ? `${summary.observation_count} 条观察` : '暂无数据'}</h2></div><span className="analytics-section-note">只比较账号自己的样本</span></div>
        {summary?.observation_count ? <>
          <div className="analytics-stat-grid"><article><small>导入批次</small><strong>{summary.import_count}</strong><span>按观察记录统计</span></article><article><small>平台分布</small><strong>{Object.entries(summary.by_platform).map(([key, value]) => `${platformLabel(key)} ${value}`).join(' · ')}</strong><span>没有行业基准</span></article><article><small>有效批次</small><strong>{summary.data_quality.real_imports}</strong><span>{summary.data_quality.acceptance_test_imports ? `另有 ${summary.data_quality.acceptance_test_imports} 批演练数据` : '均为导入记录'}</span></article></div>
          <div className="analytics-note-list"><strong>分析边界</strong>{summary.limitations.map(item => <p key={item}>{item}</p>)}</div>
          {insights?.insights.length ? <div className="analytics-summary-section"><div className="analytics-subheading"><h3>候选优化经验</h3><span>相关性观察</span></div><div className="analytics-observation-list">{insights.insights.slice(0, 8).map(item => <div key={`${item.platform}-${item.dimension}-${item.label}`}><strong>{item.ready_for_use ? '可供下次参考' : '继续观察'} · {item.label}</strong><span>{item.statement}</span></div>)}</div></div> : null}
        </> : <div className="analytics-empty"><strong>还没有可分析的观察</strong><p>导入真实的 CSV 或 JSON 后，这里才会显示内容表现分布。</p></div>}
      </section>
    </div>
    {summary?.observation_count ? <section className="analytics-card analytics-detail-card">
      <div className="analytics-section-heading"><div><span className="kicker">观察明细</span><h2>从数据里看出什么</h2></div><span className="analytics-section-note">不生成增长率或因果结论</span></div>
      <div className="analytics-detail-grid">
        <div><h3>平台指标范围</h3><div className="analytics-observation-list">{Object.entries(summary.metrics_by_platform).flatMap(([platformName, metrics]) => Object.entries(metrics).map(([metric, stats]) => <div key={`${platformName}-${metric}`}><strong>{platformLabel(platformName)} · {metric}</strong><span>{stats.count} 条 · 最小 {stats.min} · 最大 {stats.max} · 均值 {stats.mean.toFixed(2)}</span></div>))}</div></div>
        <div><h3>内容支柱观察数</h3><div className="analytics-observation-list">{Object.entries(summary.by_pillar).map(([pillar, count]) => <div key={pillar}><strong>{pillar}</strong><span>{count} 条观察</span></div>)}</div></div>
        <div><h3>本批最高观察值</h3><div className="analytics-observation-list">{summary.top_content.filter(item => Object.keys(item.metrics).length).slice(0, 5).map(item => <div key={`${item.platform}-${item.title}-${item.observed_at}`}><strong>{item.title}</strong><span>{platformLabel(item.platform)} · {Object.entries(item.metrics).map(([key, value]) => `${key} ${String(value)}`).join(' · ')}</span></div>)}</div></div>
        <div><h3>最近导入的观察</h3><div className="analytics-observation-list">{summary.observations.slice(0, 10).map(item => <div key={`${item.platform}-${item.title}-${item.observed_at}`}><strong>{item.title}</strong><span>{platformLabel(item.platform)} · {item.pillar || '未标注支柱'} · {dateLabel(item.observed_at)}</span></div>)}</div></div>
      </div>
    </section> : null}
    <section className="analytics-card analytics-history-card">
      <div className="analytics-section-heading"><div><span className="kicker">导入记录</span><h2>可追溯批次</h2></div><span className="analytics-section-note">保留来源和状态</span></div>
      {imports.length ? <div className="analytics-import-list">{imports.map(item => <div key={item.id}><strong>{item.original_name || '未命名导入'}</strong><span>{platformLabel(item.platform)} · {item.row_count} 行 · {item.status} · {dateLabel(item.imported_at)}{item.source_type === 'acceptance_test' ? ' · 演练数据' : ''}</span></div>)}</div> : <p className="analytics-muted">还没有导入记录。</p>}
    </section>
  </>;
}
