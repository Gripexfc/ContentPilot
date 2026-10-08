const names: Record<string, string> = {
  reader_problem: '读者要解决的问题', author_angle: '作者观点与角度', facts: '事实与证据', sources: '来源', research_gaps: '待核验内容',
  title: '标题', title_candidates: '标题候选', summary: '摘要', sections: '正文段落', heading: '小标题', body: '正文', fact_citations: '事实引用',
  cover_brief: '首图说明', body_image_briefs: '正文配图说明', ending_policy: '结尾规则', cover_copy: '封面文案', cards: '分页卡片', page: '页码', text: '文案', topics: '话题', image_prompts: '图片提示词',
  hook_3s: '3 秒开场', voiceover: '口播稿', shots: '分镜', scene: '镜头序号', seconds: '时长（秒）', visual: '画面', audio: '声音', subtitle: '字幕稿', visual_notes: '画面说明', broll_suggestions: 'B-roll 建议',
  voice_and_music: '配音与音乐', voice: '配音', music: '音乐', video_generation_flow: '视频流程建议', generation_kind: '内容来源',
};
export const fieldName = (key: string) => names[key] ?? key;
const object = (value: unknown): value is Record<string, unknown> => value !== null && typeof value === 'object' && !Array.isArray(value);
const blank = (value: unknown): unknown => typeof value === 'string' ? '' : typeof value === 'number' ? 1 : Array.isArray(value) ? [] : object(value) ? Object.fromEntries(Object.entries(value).map(([k,v]) => [k, blank(v)])) : '';

export function Fields({ value, onChange, label = '内容' }: { value: unknown; onChange: (value: unknown) => void; label?: string }) {
  if (Array.isArray(value)) {
    if (value.every(item => typeof item === 'string')) return <label>{label}<textarea rows={Math.max(2, Math.min(6, value.length))} value={value.join('\n')} onChange={e => onChange(e.target.value.split('\n'))} /><small>每行一项</small></label>;
    return <fieldset><legend>{label}</legend>{value.map((item, i) => <div className="repeat-row" key={i}><Fields label={`${label} ${i + 1}`} value={item} onChange={next => onChange(value.map((v, j) => j === i ? next : v))} /><button type="button" className="subtle" onClick={() => onChange(value.filter((_, j) => i !== j))}>移除{label} {i + 1}</button></div>)}<button type="button" onClick={() => onChange([...value, blank(value[0])])}>添加{label}</button></fieldset>;
  }
  if (object(value)) return <div className="field-stack">{Object.entries(value).filter(([key]) => !['generation_kind', 'ending_policy'].includes(key)).map(([key, item]) => <Fields key={key} label={fieldName(key)} value={item} onChange={next => onChange({ ...value, [key]: next })} />)}</div>;
  if (typeof value === 'number') return <label>{label}<input type="number" value={value} onChange={e => onChange(Number(e.target.value))} /></label>;
  if (typeof value === 'boolean') return <label><input type="checkbox" checked={value} onChange={e => onChange(e.target.checked)} />{label}</label>;
  return <label>{label}<textarea rows={label.includes('标题') ? 2 : 4} value={typeof value === 'string' ? value : ''} onChange={e => onChange(e.target.value)} /></label>;
}

export function ReadFields({ value, label }: { value: unknown; label?: string }) {
  if (value === null || value === undefined) return null;
  if (Array.isArray(value)) return <section className="reading-block">{label && <h3>{label}</h3>}{value.length ? value.map((item, i) => <ReadFields key={i} value={item} />) : <p className="muted">暂无记录</p>}</section>;
  if (object(value)) return <section className="reading-block">{label && <h3>{label}</h3>}{Object.entries(value).filter(([k]) => !['generation_kind','ending_policy'].includes(k)).map(([key, item]) => <ReadFields key={key} label={fieldName(key)} value={item} />)}</section>;
  return <div className="reading-field">{label && <h3>{label}</h3>}<p>{String(value) || '未填写'}</p></div>;
}
