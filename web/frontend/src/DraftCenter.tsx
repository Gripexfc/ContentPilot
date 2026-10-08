import { useEffect, useMemo, useState } from 'react';
import { copyWechatDraft, createWechatDraft, getWechatDraft, listWechatDrafts, submitWechatDraft, updateWechatDraft, uploadWechatCover, type WechatDraft, type WechatDraftDetail } from './api';
import { dateLabel, Empty, errorText, Message, PageHeader, stateName, useDirty } from './components/shared';

const blank = { title: '', digest: '', author: '', content_html: '<p>从这里开始写公众号正文。</p>' };
type DraftForm = typeof blank;

export const isDraftDirty = (form: DraftForm, saved: DraftForm | null, hasDraft: boolean) =>
  hasDraft ? JSON.stringify(form) !== JSON.stringify(saved) : JSON.stringify(form) !== JSON.stringify(blank);

export const previewDocument = (content: string) => `<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src data: blob:; style-src 'unsafe-inline'; font-src data:; form-action 'none';"><style>body{margin:24px;color:#dce4f2;background:#0d1523;font:16px/1.85 Georgia,'Songti SC',serif}img{max-width:100%;height:auto}h1,h2,h3{color:#fff}p{margin:8px 0}</style></head><body>${content}</body></html>`;

const formOf = (draft: Pick<WechatDraft, 'title' | 'digest' | 'author' | 'content_html'>): DraftForm => ({
  title: draft.title, digest: draft.digest, author: draft.author, content_html: draft.content_html,
});

export function DraftCenterPage({ initialDraftId, onDirty }: { initialDraftId?: string; onDirty: (value: boolean) => void }) {
  const [items, setItems] = useState<WechatDraft[]>([]);
  const [selected, setSelected] = useState<WechatDraftDetail | null>(null);
  const [form, setForm] = useState<DraftForm>(blank);
  const [saved, setSaved] = useState<DraftForm | null>(null);
  const [notice, setNotice] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [needsConnector, setNeedsConnector] = useState(false);
  const dirty = isDraftDirty(form, saved, Boolean(selected));
  useDirty(dirty, onDirty);

  const selectDetail = (detail: WechatDraftDetail) => {
    const next = formOf(detail);
    setSelected(detail); setForm(next); setSaved(next);
  };
  const refresh = async (id?: string) => {
    const next = await listWechatDrafts();
    setItems(next);
    const target = id || selected?.id || next[0]?.id;
    if (target) selectDetail(await getWechatDraft(target));
    else { setSelected(null); setSaved(null); }
  };
  useEffect(() => { void refresh(initialDraftId).catch(e => setError(errorText(e))); }, [initialDraftId]);

  const run = async (fn: () => Promise<void>) => { setBusy(true); setError(''); setNotice(''); setNeedsConnector(false); try { await fn(); } catch (e) { setError(errorText(e)); } finally { setBusy(false); } };
  const set = (key: keyof DraftForm, value: string) => setForm(valueMap => ({ ...valueMap, [key]: value }));
  const guard = () => !dirty || window.confirm('当前草稿有未保存修改，继续会丢弃这些修改。确定继续吗？');
  const newDraft = () => { if (!guard()) return; setSelected(null); setForm(blank); setSaved(null); setNotice(''); setError(''); };
  const open = (id: string) => { if (!guard()) return; void run(async () => selectDetail(await getWechatDraft(id))); };
  const save = () => void run(async () => {
    if (selected?.status === 'submitted') throw new Error('已提交草稿不可直接修改，请复制为新草稿');
    const next = selected ? await updateWechatDraft(selected.id, form) : await createWechatDraft(form);
    await refresh(next.id); setNotice('公众号草稿已保存到本机；未调用微信写接口。');
  });
  const upload = (file: File) => void run(async () => {
    if (!selected) return;
    if (selected.status === 'submitted') throw new Error('已提交草稿不可更换封面，请复制为新草稿');
    if (file.size > 10 * 1024 * 1024) throw new Error('封面不能超过 10 MB');
    if (!['image/png', 'image/jpeg', 'image/webp'].includes(file.type)) throw new Error('封面必须是 PNG、JPEG 或 WebP 图片');
    const next = await uploadWechatCover(selected.id, file);
    const detail = await getWechatDraft(next.id);
    setSelected(detail); setNotice('封面已保存，编辑中的标题和正文保持不变。');
  });
  const submit = (fail: boolean) => void (async () => {
    setBusy(true); setError(''); setNotice(''); setNeedsConnector(false);
    try {
      if (!selected) return;
      if (dirty) throw new Error('请先保存当前修改，再提交已保存的草稿');
      const next = await submitWechatDraft(selected.id, fail);
      await refresh(next.id);
      setNotice(next.status === 'failed' ? '提交失败已记录，可点击重试。真实微信后台未被调用。' : next.submission_receipt ? '真实连接方式已返回提交回执；请人工核对后台草稿。' : '本地演示提交已记录，状态只是本地连接回执。');
    } catch (e) {
      const message = errorText(e);
      try { if (selected) await refresh(selected.id); } catch { /* keep the original failure visible */ }
      setError(message);
      setNeedsConnector(/配置|连接|读取|登录|会话/.test(message));
    } finally { setBusy(false); }
  })();
  const copy = () => void run(async () => { if (!selected) return; const next = await copyWechatDraft(selected.id); await refresh(next.id); setNotice('已复制为新草稿，原提交记录和来源追溯仍保留。'); });

  const preview = useMemo(() => previewDocument(form.content_html), [form.content_html]);
  return <>
    <PageHeader title="发布中心 · 公众号" description="公众号文章在这里完成封面、预览和草稿提交；本地记录可追溯，真实后台动作会单独显示回执，不执行群发。">
      <button className="primary" onClick={newDraft}>新建草稿</button>
    </PageHeader>
    {notice && <Message error={notice.includes('失败')}>{notice}</Message>}
    {error && <Message error>{error}{needsConnector && <button className="link" onClick={() => { window.location.hash = '/settings'; }}>去账号</button>}</Message>}
    <div className="draft-center">
      <section className="panel draft-list"><div className="section-title"><div><span className="kicker">本地草稿</span><h2>{items.length ? `${items.length} 篇` : '暂无草稿'}</h2></div><button className="link" onClick={() => { if (guard()) void run(() => refresh()); }}>刷新</button></div>
        {items.length ? items.map(item => <button className={`task-line ${selected?.id === item.id ? 'selected' : ''}`} key={item.id} onClick={() => open(item.id)}><span><strong>{item.title}</strong><small>{stateName(item.status)} · {item.author || '未填写作者'}</small></span><b>→</b></button>) : <Empty title="还没有公众号草稿">点击右上角新建，或从已保存的公众号产物转入。</Empty>}
      </section>
      <section className="panel draft-editor"><div className="panel-title"><div><span className="kicker">{selected ? `草稿 · ${stateName(selected.status)}` : '新草稿'}</span><h2>{selected?.title || '未命名公众号文章'}</h2></div>{selected?.status === 'submitted' && <span className="status-pill success">{selected.submission_receipt ? '真实连接方式已提交' : '本地演示已提交'}</span>}</div>
        {selected && <div className="draft-source">来源追溯：{selected.source_revision_id ? `任务 ${selected.source_task_id?.slice(0, 8)} · 产物 ${selected.source_artifact_id?.slice(0, 8)} · 版本 ${selected.source_revision_id.slice(0, 8)}` : '手动创建'} · 本地记录</div>}
        <fieldset className="form-grid" disabled={busy || selected?.status === 'submitted'}><label>标题<input maxLength={64} value={form.title} onChange={e => set('title', e.target.value)} placeholder="文章标题" /></label><label>作者<input maxLength={32} value={form.author} onChange={e => set('author', e.target.value)} placeholder="作者署名" /></label><label className="wide">摘要<input maxLength={120} value={form.digest} onChange={e => set('digest', e.target.value)} placeholder="给公众号后台的摘要" /></label><label className="wide">正文 HTML<textarea rows={16} value={form.content_html} onChange={e => set('content_html', e.target.value)} placeholder="支持公众号正文 HTML；保存前请自行检查标签。" /></label></fieldset>
        <div className="draft-actions"><button className="primary" disabled={busy || selected?.status === 'submitted' || !form.title.trim() || !dirty} onClick={save}>{busy ? '保存中…' : selected ? '保存修改' : '保存为本地草稿'}</button>{selected?.status === 'submitted' && <button className="secondary" disabled={busy} onClick={copy}>复制为新草稿</button>}{selected && selected.status !== 'submitted' && <><label className="file-action">上传封面<input type="file" accept="image/png,image/jpeg,image/webp" disabled={busy} onChange={e => { const file = e.target.files?.[0]; if (file) upload(file); e.target.value = ''; }} /></label><button className="secondary" disabled={busy || dirty || !selected.cover_url} onClick={() => submit(true)}>模拟失败演练</button><button className="primary" disabled={busy || dirty || !selected.cover_url} onClick={() => submit(false)}>{selected.status === 'failed' ? '重试提交' : '提交到当前连接方式'}</button></>}</div>
        <div className="draft-meta"><span>{selected?.cover_url ? '已上传封面' : '尚未上传封面'}</span><span>{dirty ? '有未保存修改' : '内容已保存'} · {selected ? `更新时间 ${dateLabel(selected.updated_at)}` : '等待保存'}</span></div>
      </section>
      <section className="panel draft-preview"><div className="preview-title"><strong>公众号预览</strong><small>隔离 HTML · 无脚本 / 外部请求</small></div>{selected?.cover_url ? <img className="draft-cover" src={selected.cover_url} alt="公众号草稿封面" /> : <div className="cover-empty">封面预览<br /><small>上传图片后显示</small></div>}<h2>{form.title || '未命名文章'}</h2><p className="draft-digest">{form.digest || '暂无摘要'}</p><iframe className="html-preview-frame" title="公众号正文隔离预览" sandbox="" srcDoc={preview} />{selected && <details className="draft-events"><summary>提交记录（{selected.events.length}）</summary>{selected.events.map(event => <p key={event.id}><strong>{event.operation}</strong> · {stateName(event.to_status)} · {dateLabel(event.created_at)}{event.error && <small>{event.error}</small>}</p>)}</details>}</section>
    </div>
  </>;
}
