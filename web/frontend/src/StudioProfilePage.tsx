import { useEffect, useMemo, useRef, useState } from 'react';
import { createProfileVersion, getProfile, type Platform, type ProfileSnapshot, type PlatformProfile } from './api';
import { errorText, Message } from './components/shared';
import { StudioIcon } from './components/StudioIcon';
import {
  createDefaultProfile,
  emptyPlatform,
  hasPlatformOverrides,
  joinList,
  platformKeys,
  platformLabels,
  resolvePlatformProfile,
  splitList,
} from './lib/profile';

const platformDetails: Record<Platform, { role: string; hint: string; mark: string }> = {
  wechat: { role: '深度解释与经验复盘', hint: '适合完整文章、观点和案例', mark: '微' },
  xiaohongshu: { role: '可收藏的步骤与清单', hint: '适合轻量分段、标题和配图', mark: '红' },
  douyin: { role: '短观点与真实观察', hint: '适合开场钩子、口播和分镜', mark: '音' },
};
const suggestions = {
  profession: ['内容创作者', '产品运营', '独立开发者', '品牌运营'],
  domain: ['人工智能', '产品设计', '工程实践', '创作者工具', '商业与品牌'],
  pillar: ['实用教程', '案例复盘', '行业观察', '方法拆解', '观点评论'],
  audience: ['正在解决实际问题的创作者', '产品经理与设计师', '独立开发者', '内容运营者'],
  tone: ['清晰直接，少用术语', '具体、克制、有现场感', '温和耐心，讲人话', '有判断，敢于取舍'],
  goal: ['建立信任', '获客', '知识沉淀', '建立个人品牌'],
  format: ['先说结论', '给出步骤', '补充边界', '用真实案例'],
  positioning: ['围绕真实问题，给出可执行方法', '深度解释与经验复盘', '可收藏的步骤和清单', '短观点与真实观察'],
};

const clone = <T,>(value: T) => JSON.parse(JSON.stringify(value)) as T;
const normalizeSnapshot = (value: ProfileSnapshot): ProfileSnapshot => {
  const defaults = createDefaultProfile();
  const defaultContentDefaults = defaults.content_defaults ?? { positioning: '', format_preferences: [] };
  return {
    ...defaults,
    ...value,
    identity: { ...defaults.identity, ...value.identity },
    voice: { ...defaults.voice, ...value.voice },
    content_defaults: { positioning: value.content_defaults?.positioning ?? defaultContentDefaults.positioning, format_preferences: value.content_defaults?.format_preferences ?? defaultContentDefaults.format_preferences },
    goals: { ...defaults.goals, ...value.goals },
    boundaries: { ...defaults.boundaries, ...value.boundaries },
    platforms: Object.fromEntries(platformKeys.map(platform => [platform, { ...emptyPlatform(), ...(value.platforms?.[platform] || {}) }])) as ProfileSnapshot['platforms'],
  };
};

function SingleChoiceField({ id, label, hint, value, placeholder, choices, onChange }: {
  id: string; label: string; hint?: string; value: string; placeholder: string; choices: string[]; onChange: (value: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return undefined;
    const closeWhenOutside = (event: PointerEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener('pointerdown', closeWhenOutside);
    return () => document.removeEventListener('pointerdown', closeWhenOutside);
  }, [open]);
  const query = value.trim().toLocaleLowerCase();
  const matchingChoices = choices.filter(choice => !query || choice.toLocaleLowerCase().includes(query));
  const visibleChoices = matchingChoices.length ? matchingChoices : choices;
  return <div className="profile-field profile-choice-field">
    <label htmlFor={id}>{label}{hint && <small>{hint}</small>}</label>
    <div className="profile-choice-control" ref={rootRef} onBlur={event => {
      const next = event.relatedTarget as Node | null;
      if (!next || !rootRef.current?.contains(next)) setOpen(false);
    }}>
      <input id={id} value={value} onChange={event => onChange(event.target.value)} onFocus={() => choices.length && setOpen(true)} onClick={() => choices.length && setOpen(true)} onKeyDown={event => {
        if (event.key === 'Escape') setOpen(false);
        if (event.key === 'ArrowDown' && choices.length) { event.preventDefault(); setOpen(true); }
        if (event.key === 'Enter' && open && visibleChoices.length === 1) { event.preventDefault(); onChange(visibleChoices[0]); setOpen(false); }
      }} placeholder={placeholder} aria-autocomplete={choices.length ? 'list' : undefined} aria-expanded={choices.length ? open : undefined} aria-haspopup={choices.length ? 'listbox' : undefined} />
      {choices.length > 0 && <button type="button" className="profile-choice-toggle" aria-label={`展开${label}建议`} aria-expanded={open} onMouseDown={event => event.preventDefault()} onClick={() => setOpen(current => !current)}><StudioIcon name="chevron-down" size={14} /></button>}
      {choices.length > 0 && open && <div className="profile-choice-menu" role="listbox" aria-label={`${label}常用选项`}>{visibleChoices.map(choice => <button type="button" role="option" aria-selected={value === choice} key={choice} onMouseDown={event => event.preventDefault()} onClick={() => { onChange(choice); setOpen(false); }}>{choice}</button>)}</div>}
    </div>
  </div>;
}

function TagField({ id, label, hint, values, placeholder, suggestions: choices, onChange }: {
  id: string; label: string; hint?: string; values: string[]; placeholder: string; suggestions: string[]; onChange: (values: string[]) => void;
}) {
  const [draft, setDraft] = useState('');
  const add = (raw: string) => {
    const next = splitList(raw);
    if (!next.length) return;
    onChange([...new Set([...values, ...next])]);
    setDraft('');
  };
  const remove = (value: string) => onChange(values.filter(item => item !== value));
  return <div className="profile-field profile-tag-field">
    <label htmlFor={id}>{label}{hint && <small>{hint}</small>}</label>
    <div className="profile-tag-input">
      <div className="profile-tags" aria-live="polite">{values.map(value => <span key={value} className="profile-tag">{value}<button type="button" aria-label={`移除${value}`} onClick={() => remove(value)}>×</button></span>)}</div>
      <input id={id} value={draft} onChange={event => setDraft(event.target.value)} onKeyDown={event => { if (event.key === 'Enter' || event.key === ',' || event.key === '，' || event.key === '、') { event.preventDefault(); add(draft); } }} onBlur={() => add(draft)} placeholder={values.length ? '继续添加，回车确认' : placeholder} />
    </div>
    <div className="profile-suggestion-row" aria-label={`${label}常用选项`}>
      {choices.map(choice => <button type="button" key={choice} className={values.includes(choice) ? 'selected' : ''} onClick={() => add(choice)}>{choice}</button>)}
    </div>
  </div>;
}

function PlatformProfileCard({ platform, profile, onChange, onReset }: {
  platform: Platform; profile: ProfileSnapshot; onChange: (value: PlatformProfile) => void; onReset: () => void;
}) {
  const own = profile.platforms[platform] || emptyPlatform();
  const effective = resolvePlatformProfile(profile, platform);
  const overridden = hasPlatformOverrides(profile, platform);
  const update = (patch: Partial<PlatformProfile>) => onChange({ ...own, ...patch });
  return <fieldset className={`profile-platform-card ${overridden ? 'has-overrides' : ''}`}>
    <legend><span className={`platform-dot ${platform}`}>{platformDetails[platform].mark}</span><span><strong>{platformLabels[platform]}</strong><small>{platformDetails[platform].role}</small></span></legend>
    <p className="platform-card-hint">{platformDetails[platform].hint}</p>
    <div className="platform-state"><span className={overridden ? 'state-dot active' : 'state-dot'} />{overridden ? '已设置平台差异' : '正在使用共用配置'}{overridden && <button type="button" onClick={onReset}>恢复共用配置</button>}</div>
    <SingleChoiceField id={`${platform}-positioning`} label="平台定位" hint="选填，留空就沿用共用定位" value={own.positioning} placeholder={effective.positioning} choices={suggestions.positioning} onChange={value => update({ positioning: value })} />
    <SingleChoiceField id={`${platform}-audience`} label="平台读者" hint="选填，留空就沿用共用读者" value={own.audience} placeholder={effective.audience || '先在共用配置中填写'} choices={suggestions.audience} onChange={value => update({ audience: value })} />
    <SingleChoiceField id={`${platform}-tone`} label="平台语气" hint="选填，留空就沿用共用语气" value={own.tone} placeholder={effective.tone} choices={suggestions.tone} onChange={value => update({ tone: value })} />
    <TagField id={`${platform}-formats`} label="平台格式" hint="选填，留空就沿用共用格式" values={own.format_preferences} placeholder={joinList(effective.format_preferences) || '先在共用配置中填写'} suggestions={suggestions.format} onChange={format_preferences => update({ format_preferences })} />
    <div className="platform-effective"><small>当前生成实际会使用</small><span>{effective.positioning} · {effective.tone}</span></div>
  </fieldset>;
}

export function StudioProfilePage({ navigate }: { navigate: (path: string) => void }) {
  const [snapshot, setSnapshot] = useState<ProfileSnapshot>(createDefaultProfile);
  const [saved, setSaved] = useState<ProfileSnapshot>(createDefaultProfile);
  const [version, setVersion] = useState<number | null>(null);
  const [notice, setNotice] = useState('先设一套共用规则，再按平台补充差异；留空的平台字段会自动继承共用配置。');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const dirty = JSON.stringify(snapshot) !== JSON.stringify(saved);
  const completion = useMemo(() => {
    const values = [snapshot.identity.display_name, snapshot.identity.profession, snapshot.domains.join(''), snapshot.pillars.join(''), snapshot.readers[0]?.name || '', snapshot.voice.tone, snapshot.content_defaults?.positioning || '', snapshot.evidence_refs.join('')];
    return Math.round(values.filter(Boolean).length / values.length * 100);
  }, [snapshot]);

  useEffect(() => {
    void getProfile().then(result => {
      const next = normalizeSnapshot(result.current_version.snapshot);
      setSnapshot(next); setSaved(clone(next)); setVersion(result.current_version.version_no);
    }).catch(() => { /* First use keeps the editable operational defaults. */ });
  }, []);
  const setSnapshotValue = (patch: Partial<ProfileSnapshot>) => setSnapshot(current => ({ ...current, ...patch }));
  const setIdentity = (key: keyof ProfileSnapshot['identity'], value: string) => setSnapshotValue({ identity: { ...snapshot.identity, [key]: value } });
  const setCommon = (patch: Partial<NonNullable<ProfileSnapshot['content_defaults']>>) => setSnapshotValue({ content_defaults: { ...snapshot.content_defaults!, ...patch } });
  const setPlatform = (platform: Platform, value: PlatformProfile) => setSnapshot(current => ({ ...current, platforms: { ...current.platforms, [platform]: value } }));
  const save = async () => {
    if (!dirty || busy) return;
    setBusy(true); setError('');
    try {
      const result = await createProfileVersion({ snapshot, change_summary: version ? '更新共用与平台写作偏好' : '建立创作者写作偏好与运营默认配置' });
      const next = normalizeSnapshot(result.snapshot); setSnapshot(next); setSaved(clone(next)); setVersion(result.version_no); setNotice(`写作偏好 v${result.version_no} 已保存。之后每次生成都会使用这套共用规则和平台覆盖。`);
    } catch (e) { setError(errorText(e)); }
    finally { setBusy(false); }
  };
  return <>
    <div className="studio-page-heading profile-heading">
      <div><div className="page-kicker">PROFILE / 01</div><h1>我的写作偏好</h1><p>告诉知序你的经历、边界和表达习惯，后续生成可按这套偏好来写。</p></div>
      <div className="profile-heading-actions"><button className="quiet-button" onClick={() => navigate('create')}><StudioIcon name="pen" size={16} />进入内容工作区</button></div>
    </div>
    {notice && <Message>{notice}</Message>}{error && <Message error>{error}</Message>}
    <div className="profile-overview-strip" aria-label="写作偏好状态">
      <div className="profile-overview-stat"><span>写作偏好完整度</span><strong>{completion}%</strong><small>{version ? `当前版本 v${version}` : '还没有保存版本'}</small></div>
      <div className="profile-overview-stat profile-overview-stat-accent"><span>已关联证据</span><strong>{snapshot.evidence_refs.length}</strong><small>真实经历、案例和来源</small></div>
      <div className="profile-overview-stat profile-overview-stat-warning"><span>当前状态</span><strong>{dirty ? '待保存' : '已同步'}</strong><small>{dirty ? '保存后会创建新版本' : '可直接用于下一次创作'}</small></div>
    </div>
    <div className="profile-setup-flow" aria-label="写作偏好设置步骤"><span className="active"><b>1</b>共用规则</span><i>→</i><span><b>2</b>平台差异</span><i>→</i><span><b>3</b>保存并开始创作</span></div>
    <div className="profile-studio-layout">
      <section className="profile-studio-card">
        <div className="profile-card-head"><div><span className="page-kicker">CURRENT PROFILE {version ? `· V${version}` : '· FIRST SETUP'}</span><h2>{snapshot.identity.display_name || '先从一套默认规则开始'}</h2></div><span className="profile-completion">{completion}% 完整</span></div>
        <section className="profile-form-section"><div className="profile-section-title"><div><h3>先让系统认识你</h3><p>这些信息帮助内容保持真实；没有的内容可以先留空。</p></div><span>基础信息</span></div>
          <div className="profile-form-grid"><SingleChoiceField id="profile-name" label="怎么称呼你" value={snapshot.identity.display_name} onChange={value => setIdentity('display_name', value)} placeholder="例如：陈默" choices={[]} /><SingleChoiceField id="profile-profession" label="你的身份" value={snapshot.identity.profession} onChange={value => setIdentity('profession', value)} placeholder="例如：产品运营、内容创作者" choices={suggestions.profession} /></div>
          <div className="profile-field"><label htmlFor="profile-bio">你想被怎样认识<small>写清楚经历、擅长的事和不写的范围</small></label><textarea id="profile-bio" rows={3} value={snapshot.identity.bio} onChange={event => setIdentity('bio', event.target.value)} placeholder="例如：我长期做内容产品，喜欢把复杂问题讲成可以执行的步骤。" /></div>
          <div className="profile-form-grid"><TagField id="profile-domains" label="你长期关注什么" hint="可多选" values={snapshot.domains} onChange={domains => setSnapshotValue({ domains })} placeholder="输入一个领域，回车确认" suggestions={suggestions.domain} /><TagField id="profile-pillars" label="你反复讲哪几类问题" hint="可多选" values={snapshot.pillars} onChange={pillars => setSnapshotValue({ pillars })} placeholder="输入一个内容支柱，回车确认" suggestions={suggestions.pillar} /></div>
          <div className="profile-form-grid"><SingleChoiceField id="profile-audience" label="你写给谁看" value={snapshot.readers[0]?.name || ''} onChange={value => setSnapshotValue({ readers: value ? [{ name: value, problems: snapshot.readers[0]?.problems || [] }] : [] })} placeholder="例如：正在解决实际问题的创作者" choices={suggestions.audience} /><TagField id="profile-goals" label="希望达成什么" hint="运营目标，可多选" values={snapshot.goals.priorities} onChange={priorities => setSnapshotValue({ goals: { priorities } })} placeholder="选择一个目标，回车确认" suggestions={suggestions.goal} /></div>
        </section>
        <section className="profile-default-section"><div className="profile-section-title"><div><h3>共用内容规则</h3><p>这是三个平台的起点。你可以随时修改，平台没有单独设置的字段会跟着这里变化。</p></div><span>默认配置</span></div>
          <div className="profile-default-grid"><SingleChoiceField id="profile-default-positioning" label="默认内容定位" hint="所有平台都会参考" value={snapshot.content_defaults?.positioning || ''} onChange={value => setCommon({ positioning: value })} placeholder="例如：围绕真实问题，给出可执行方法" choices={suggestions.positioning} /><SingleChoiceField id="profile-default-tone" label="默认表达语气" hint="所有平台都会参考" value={snapshot.voice.tone} onChange={value => setSnapshotValue({ voice: { ...snapshot.voice, tone: value } })} placeholder="例如：清晰直接，少用术语" choices={suggestions.tone} /></div>
          <TagField id="profile-default-formats" label="默认内容格式" hint="所有平台都会参考，可多选" values={snapshot.content_defaults?.format_preferences || []} onChange={format_preferences => setCommon({ format_preferences })} placeholder="选择一个写作习惯，回车确认" suggestions={suggestions.format} />
          <div className="profile-form-grid"><TagField id="profile-forbidden" label="不想出现什么" hint="禁用词或表达，可多选" values={snapshot.boundaries.forbidden_words} onChange={forbidden_words => setSnapshotValue({ boundaries: { ...snapshot.boundaries, forbidden_words } })} placeholder="例如：绝对、保证、全网第一" suggestions={['夸大承诺', '厂商腔', '空泛套话']} /><TagField id="profile-unwanted" label="希望少用哪些表达" hint="会在生成前提醒模型" values={snapshot.boundaries.unwanted_expressions} onChange={unwanted_expressions => setSnapshotValue({ boundaries: { ...snapshot.boundaries, unwanted_expressions } })} placeholder="例如：先说结论，少用套话" suggestions={['堆砌形容词', '连续反问', '营销口号']} /></div>
        </section>
        <section className="profile-platform-section"><div className="profile-section-title"><div><h3>按平台调整</h3><p>只填写真正不同的地方；每张卡片底部会显示最终生效的规则。</p></div><span>可选覆盖</span></div><div className="profile-platforms">{platformKeys.map(platform => <PlatformProfileCard key={platform} platform={platform} profile={snapshot} onChange={value => setPlatform(platform, value)} onReset={() => setPlatform(platform, emptyPlatform())} />)}</div></section>
        <section className="profile-evidence-section"><div className="profile-section-title"><div><h3>留下可引用的素材</h3><p>只写你愿意公开使用的经历、案例、数据或截图位置。</p></div><span>证据范围</span></div><div className="profile-field"><label htmlFor="profile-evidence">真实经历、案例、数据</label><textarea id="profile-evidence" rows={3} value={snapshot.evidence_refs.join('\n')} onChange={event => setSnapshotValue({ evidence_refs: event.target.value.split('\n').map(value => value.trim()).filter(Boolean) })} placeholder="一行一条，例如：2026 年 9 月，完成一次本地内容工作流改造，可公开分享过程和结果。" /></div></section>
        <div className="profile-save-row"><span>{dirty ? '有未保存的修改' : '当前写作偏好已同步'}<small>保存会创建一个新的可回看的写作偏好版本。</small></span><button className="primary" disabled={!dirty || busy} onClick={() => void save()}>{busy ? '正在保存…' : '保存这套写作偏好'}</button></div>
      </section>
      <aside className="profile-guide-card"><div className="guide-mark"><StudioIcon name="spark" size={22} /></div><h2>设置时只需要记住三件事</h2><ol><li><strong>共用规则管方向</strong><span>定位、语气和格式是所有平台的默认起点，适合先把运营标准定下来。</span></li><li><strong>平台卡片只写差异</strong><span>公众号可以更完整，小红书更适合清单，抖音更看重开场和口播。</span></li><li><strong>留空也没关系</strong><span>没有单独设置的平台字段会继承共用配置；之后想调整，改完再保存一个新版本即可。</span></li></ol><div className="profile-guide-note"><strong>保存后会发生什么？</strong><span>下一次创作会引用当前版本。历史版本仍然保留，方便你比较和恢复。</span></div><button className="secondary" onClick={() => navigate('create')}>去生成一篇试试<StudioIcon name="arrow" size={15} /></button></aside>
    </div>
  </>;
}
