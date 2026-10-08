import { useEffect, useRef, useState } from 'react';
import { getProfile, runSkill, type ProfileSnapshot } from './api';
import { Message, errorText } from './components/shared';
import { StudioIcon } from './components/StudioIcon';
import { profilePrompt } from './lib/profile';

type Platform = 'wechat' | 'xiaohongshu' | 'douyin';
type SourceType = 'text' | 'url';

type BreakdownDraft = {
  version: 1 | 2;
  platform: Platform;
  sourceType: SourceType;
  input: string;
  useProfile: boolean;
  result: string;
  resultPlatform?: Platform;
  adaptedResult: string;
  adaptedPlatform?: Platform;
  savedAt: string;
};

const BREAKDOWN_DRAFT_KEY = 'creatoros:breakdown-draft-v1';
const platformKeys = new Set<Platform>(['wechat', 'xiaohongshu', 'douyin']);

const readBreakdownDraft = (): BreakdownDraft | null => {
  try {
    const raw = window.localStorage.getItem(BREAKDOWN_DRAFT_KEY);
    if (!raw) return null;
    const value = JSON.parse(raw) as Partial<BreakdownDraft>;
    if (value.version !== 1 && value.version !== 2 || !platformKeys.has(value.platform as Platform) || (value.sourceType !== 'text' && value.sourceType !== 'url')) return null;
    if (typeof value.input !== 'string' || typeof value.result !== 'string' || typeof value.useProfile !== 'boolean') return null;
    const adaptedResult = typeof value.adaptedResult === 'string' ? value.adaptedResult : '';
    if (!value.input.trim() && !value.result.trim() && !adaptedResult.trim() && !value.useProfile) return null;
    return {
      version: 2,
      platform: value.platform as Platform,
      sourceType: value.sourceType,
      input: value.input,
      useProfile: value.useProfile,
      result: value.result,
      resultPlatform: value.resultPlatform && platformKeys.has(value.resultPlatform as Platform) ? value.resultPlatform as Platform : value.platform as Platform,
      adaptedResult,
      adaptedPlatform: value.adaptedPlatform && platformKeys.has(value.adaptedPlatform as Platform) ? value.adaptedPlatform as Platform : value.platform as Platform,
      savedAt: typeof value.savedAt === 'string' ? value.savedAt : new Date().toISOString(),
    };
  } catch {
    return null;
  }
};

const removeBreakdownDraft = () => {
  try { window.localStorage.removeItem(BREAKDOWN_DRAFT_KEY); } catch { /* Local memory is optional. */ }
};

const platforms: Record<Platform, { label: string; mark: string; description: string; skill: string; writingSkill: string; dimensions: string[] }> = {
  wechat: { label: '公众号', mark: '微', description: '标题、开头、论证、阅读节奏和转发价值', skill: 'skill-competitor-analysis', writingSkill: 'social-content', dimensions: ['标题承诺与开头留人', '文章论证和段落节奏', '事实、案例与观点比例', '结尾互动和转发理由'] },
  xiaohongshu: { label: '小红书', mark: '红', description: '封面、前两行、卡片节奏、收藏和评论触发', skill: 'skill-competitor-analysis', writingSkill: 'xhs-note-creator', dimensions: ['封面与标题钩子', '前两行和卡片信息密度', '收藏价值与评论问题', '话题标签和人群共鸣'] },
  douyin: { label: '抖音', mark: '音', description: '前三秒、口播、镜头、完播和互动设计', skill: 'skill-competitor-analysis', writingSkill: 'video-script', dimensions: ['前三秒钩子与冲突', '口播节奏和镜头信息', '完播节点与情绪变化', '评论引导和二次传播'] },
};

const promptFor = (platform: Platform, input: string, sourceType: 'text' | 'url', profile: ProfileSnapshot | null, useProfile: boolean) => {
  const current = platforms[platform];
  return [`你是${current.label}平台的爆款内容拆解与原创策划专家。`, `目标平台：${current.label}。只按该平台的用户阅读和分发逻辑分析，不要输出泛泛的跨平台建议。`, `输入类型：${sourceType === 'url' ? '网页链接，能访问时先读取原文；不能访问就明确写“来源未读取”' : '用户粘贴的参考内容'}。`, `重点拆解：${current.dimensions.join('；')}。`, '请严格按下面结构输出：', '一、参考内容回执：标题/来源/平台/可确认数据；没有数据就写“无公开数据”，不要猜测。', '二、平台爆款拆解：逐项说明具体证据、作用和局限。', '三、可迁移的内容公式：抽象成结构和决策规则，不复述原文句子。', '四、原创边界：列出不能直接复制的表达、事实和独特叙事，并说明需要补充的个人材料或一手来源。', '五、结合我的账号给出 3 个原创选题：每个包含标题方向、我的切入角度、适合的内容形式和第一步素材。', '六、生成前检查清单：事实来源、原创增量、平台限制、写作偏好一致性。', '重要规则：参考内容只用于学习结构和选题规律；禁止逐句仿写、拼接原文、虚构阅读量/点赞量/完播率，也不要把参考作者的经历写成我的经历。', useProfile ? profilePrompt(profile, platform) : '本次不读取账号写作偏好，只输出通用原创方向。', `参考内容：\n${input.trim()}`].filter(Boolean).join('\n\n');
};

const adaptationPromptFor = (platform: Platform, input: string, sourceType: SourceType, analysis: string, profile: ProfileSnapshot | null, useProfile: boolean) => {
  const current = platforms[platform];
  const sourceInstruction = sourceType === 'url'
    ? '输入是网页链接。模型能访问时先读取原文；无法访问时明确写“来源未读取”，不要凭链接猜内容。'
    : '输入是用户粘贴的参考内容，只使用输入中可确认的事实。';
  return [
    `你是${current.label}平台的二次创作编辑，负责把一篇参考内容改成用户自己的可编辑成稿。`,
    `目标平台：${current.label}。${sourceInstruction}`,
    '这不是另起炉灶：保留参考内容的主题、核心事实、信息层级、论证方向、段落数量和大致篇幅，让读者仍能获得相近的信息价值；只做必要的顺序微调，不要大幅扩展或删减，更不要把内容改得面目全非。',
    '必须完成原创增量：重新写标题、开头、段落句式、过渡和结尾；在不改变信息骨架的前提下改写表达；把参考作者的独特案例、原话、数据和经历替换成用户可核验的表达。没有用户材料时写“待补充我的案例/来源”，不要编造。',
    '防抄袭规则：禁止逐句改词、翻译、拼接原句或复刻独特金句；禁止把参考作者身份、经历或结论写成用户亲历；禁止虚构来源、阅读量、点赞量、收藏量或完播率。保留相同主题不等于复制表达。',
    '请只输出一篇完整的目标平台成稿，不要解释改写过程，不要输出“参考内容”“改写说明”或分析报告。',
    current.label === '公众号' ? '公众号要求：给出一个标题和完整正文，保留清晰段落与自然结尾。' : current.label === '小红书' ? '小红书要求：输出标题、正文和适量话题标签，保持可读的卡片/笔记节奏。' : '抖音要求：输出可直接使用的口播/分镜脚本，保留原主题的核心信息和节奏。',
    useProfile && profile ? profilePrompt(profile, platform) : '本次不读取账号写作偏好，使用清晰、克制、可核验的通用表达。',
    analysis.trim() ? `拆解得到的结构提示（只参考结构和决策，不复制其中句子）：
${analysis.trim().slice(0, 7000)}` : '',
    `参考内容：
${input.trim()}`,
  ].filter(Boolean).join('\n\n');
};

const titleFromDraft = (value: string, fallback: string) => {
  const line = value.split(/\r?\n/).map(item => item.trim()).find(item => item && !/^[-*_]+$/.test(item));
  return (line || fallback).replace(/^#+\s*/, '').replace(/^(标题|题目|title)\s*[:：]\s*/i, '').slice(0, 80) || fallback;
};

export function BreakdownPage({ navigate }: { navigate: (path: string) => void }) {
  const [initialDraft] = useState<BreakdownDraft | null>(() => readBreakdownDraft());
  const [platform, setPlatform] = useState<Platform>(() => initialDraft?.platform ?? 'wechat');
  const [sourceType, setSourceType] = useState<SourceType>(() => initialDraft?.sourceType ?? 'text');
  const [input, setInput] = useState(() => initialDraft?.input ?? '');
  const [profile, setProfile] = useState<ProfileSnapshot | null>(null);
  const [useProfile, setUseProfile] = useState(() => initialDraft?.useProfile ?? false);
  const [result, setResult] = useState(() => initialDraft?.result ?? '');
  const [resultPlatform, setResultPlatform] = useState<Platform>(() => initialDraft?.resultPlatform ?? initialDraft?.platform ?? 'wechat');
  const [adaptedResult, setAdaptedResult] = useState(() => initialDraft?.adaptedResult ?? '');
  const [adaptedPlatform, setAdaptedPlatform] = useState<Platform>(() => initialDraft?.adaptedPlatform ?? initialDraft?.platform ?? 'wechat');
  const [busy, setBusy] = useState(false);
  const [adaptBusy, setAdaptBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const controller = useRef<AbortController | null>(null);
  const adaptController = useRef<AbortController | null>(null);
  const slowNoticeTimer = useRef<number | null>(null);
  const timeoutTimer = useRef<number | null>(null);
  const adaptSlowNoticeTimer = useRef<number | null>(null);
  const adaptTimeoutTimer = useRef<number | null>(null);
  const current = platforms[platform];
  const skillRequestTimeoutMs = 330_000;

  useEffect(() => {
    void getProfile().then(response => setProfile(response.current_version.snapshot)).catch(() => setProfile(null));
    return () => {
      controller.current?.abort();
      adaptController.current?.abort();
      if (slowNoticeTimer.current !== null) window.clearTimeout(slowNoticeTimer.current);
      if (timeoutTimer.current !== null) window.clearTimeout(timeoutTimer.current);
      if (adaptSlowNoticeTimer.current !== null) window.clearTimeout(adaptSlowNoticeTimer.current);
      if (adaptTimeoutTimer.current !== null) window.clearTimeout(adaptTimeoutTimer.current);
    };
  }, []);

  useEffect(() => {
    if (initialDraft && (initialDraft.input.trim() || initialDraft.result.trim() || initialDraft.adaptedResult.trim())) {
      setNotice('已恢复上次参考拆解草稿；内容仅保存在本机，可继续编辑。');
    }
  }, [initialDraft]);

  useEffect(() => {
    if (!input.trim() && !result.trim() && !adaptedResult.trim() && !useProfile) {
      removeBreakdownDraft();
      return;
    }
    try {
      const draft: BreakdownDraft = {
        version: 2,
        platform,
        sourceType,
        input,
        useProfile,
        result,
        resultPlatform,
        adaptedResult,
        adaptedPlatform,
        savedAt: new Date().toISOString(),
      };
      window.localStorage.setItem(BREAKDOWN_DRAFT_KEY, JSON.stringify(draft));
    } catch {
      // A private or full browser store must not block the breakdown flow.
    }
  }, [platform, sourceType, input, useProfile, result, resultPlatform, adaptedResult, adaptedPlatform]);

  const run = async () => {
    if (!input.trim() || busy) return;
    // Keep the last usable analysis visible while a retry is in flight. A
    // failed request should not turn a recoverable result into a blank panel.
    setBusy(true); setError(''); setNotice('');
    const abort = new AbortController();
    controller.current?.abort();
    controller.current = abort;
    slowNoticeTimer.current = window.setTimeout(() => {
      if (!abort.signal.aborted) setNotice('模型仍在处理拆解，首次响应可能需要几十秒；请稍候，页面不会丢失已有结果。');
    }, 15_000);
    timeoutTimer.current = window.setTimeout(() => abort.abort(), skillRequestTimeoutMs);
    try {
      const response = await runSkill({ skill: current.skill, input: promptFor(platform, input, sourceType, profile, useProfile), persona: undefined }, abort.signal);
      if (!abort.signal.aborted) {
        setResult(response.response);
        setResultPlatform(platform);
        setNotice('拆解完成，可以复制或下载结果。');
      }
    } catch (e) {
      if ((e as Error)?.name === 'AbortError') {
        setError('拆解等待已超时或已停止。请检查模型服务后重试；已有结果已保留。');
      } else {
        setError(errorText(e));
      }
    } finally {
      if (slowNoticeTimer.current !== null) window.clearTimeout(slowNoticeTimer.current);
      if (timeoutTimer.current !== null) window.clearTimeout(timeoutTimer.current);
      if (controller.current === abort) controller.current = null;
      setBusy(false);
    }
  };

  const adapt = async () => {
    if (!input.trim() || busy || adaptBusy) return;
    setAdaptBusy(true); setError(''); setNotice('');
    const abort = new AbortController();
    adaptController.current?.abort();
    adaptController.current = abort;
    adaptSlowNoticeTimer.current = window.setTimeout(() => {
      if (!abort.signal.aborted) setNotice('模型正在重写参考内容，首次响应可能需要几十秒；已有拆解结果会保留。');
    }, 15_000);
    adaptTimeoutTimer.current = window.setTimeout(() => abort.abort(), skillRequestTimeoutMs);
    try {
      const response = await runSkill({
        skill: current.writingSkill,
        input: adaptationPromptFor(platform, input, sourceType, result, profile, useProfile),
        persona: undefined,
      }, abort.signal);
      if (!abort.signal.aborted) {
        setAdaptedResult(response.response);
        setAdaptedPlatform(platform);
        setNotice(`已生成${current.label}版本：主题和信息骨架已保留，表达与原创增量已重写。请补充自己的来源和案例后再发布。`);
      }
    } catch (e) {
      if ((e as Error)?.name === 'AbortError') setError('二次创作等待已超时或已停止；已有结果已保留。');
      else setError(errorText(e));
    } finally {
      if (adaptSlowNoticeTimer.current !== null) window.clearTimeout(adaptSlowNoticeTimer.current);
      if (adaptTimeoutTimer.current !== null) window.clearTimeout(adaptTimeoutTimer.current);
      if (adaptController.current === abort) adaptController.current = null;
      setAdaptBusy(false);
    }
  };

  const copy = async () => {
    if (!result) return;
    await navigator.clipboard?.writeText(result);
    setNotice('拆解结果已复制，可以粘贴到开始创作。');
  };

  const copyAdapted = async () => {
    if (!adaptedResult) return;
    await navigator.clipboard?.writeText(adaptedResult);
    setNotice('我的版本已复制，可以继续编辑或带入内容工作区。');
  };

  const download = () => {
    if (!result) return;
    const resultLabel = platforms[resultPlatform].label;
    const blob = new Blob([`# ${resultLabel}爆款拆解\n\n${result}`], { type: 'text/markdown;charset=utf-8' });
    const link = document.createElement('a'); link.href = URL.createObjectURL(blob); link.download = `${resultLabel}-爆款拆解.md`; link.click(); URL.revokeObjectURL(link.href);
  };

  const downloadAdapted = () => {
    if (!adaptedResult) return;
    const adaptedLabel = platforms[adaptedPlatform].label;
    const blob = new Blob([adaptedResult], { type: 'text/markdown;charset=utf-8' });
    const link = document.createElement('a'); link.href = URL.createObjectURL(blob); link.download = `${titleFromDraft(adaptedResult, `${adaptedLabel}-二次创作`).replace(/[\\/:*?"<>|]/g, '_')}.md`; link.click(); URL.revokeObjectURL(link.href);
  };

  const continueInWorkspace = () => {
    if (!adaptedResult.trim()) return;
    const adaptedLabel = platforms[adaptedPlatform].label;
    const sourceUrl = sourceType === 'url' && /^https?:\/\//i.test(input.trim()) ? input.trim() : '';
    const draft = {
      id: `reference-${Date.now()}`,
      topic: titleFromDraft(adaptedResult, `${adaptedLabel}二次创作`),
      context: `参考来源：${sourceUrl || '用户粘贴内容'}\n\n已完成二次创作：保留主题与信息骨架，已重写标题、表达、段落组织和结尾。发布前请补充自己的来源、案例，并完成人工审校。`,
      source: sourceUrl || `参考拆解 · ${adaptedLabel}`,
      sourceUrl,
      platform: adaptedPlatform,
      mode: '文章' as const,
      skill: platforms[adaptedPlatform].writingSkill,
      output: adaptedResult,
      createdAt: Date.now(),
      workflowId: null,
      workflowArtifact: null,
      persistenceState: 'local_only' as const,
    };
    try {
      window.localStorage.setItem('creatoros:editing-draft', JSON.stringify(draft));
      window.localStorage.removeItem('creatoros:selected-hotspot');
      window.localStorage.removeItem('creatoros:compose-form');
      navigate('create');
    } catch {
      setError('无法把草稿带入内容工作区；请先复制文本后继续。');
    }
  };

  const clearDraft = () => {
    setResult('');
    setAdaptedResult('');
    setInput('');
    setUseProfile(false);
    removeBreakdownDraft();
    setNotice('本页参考拆解和二次创作内容已清空。');
  };

  const resultLabel = platforms[resultPlatform].label;
  const adaptedLabel = platforms[adaptedPlatform].label;

  return <><div className="studio-page-heading breakdown-heading"><div><div className="page-kicker">REFERENCE BREAKDOWN</div><h1>先拆清楚，再写自己的。</h1><p>针对不同平台拆解爆款内容：看清它为什么有效，再找到属于你的原创角度。</p></div><button className="quiet-button" onClick={() => navigate('hotspots')}><StudioIcon name="compass" size={16} />回到热点</button></div>{notice && <Message>{notice}</Message>}{error && <Message error>{error}<button className="link" onClick={() => navigate('settings')}>去模型设置</button></Message>}<div className="breakdown-layout"><section className="breakdown-input-panel"><div className="composer-panel-head"><span className="step-badge">01</span><div><h2>选择要拆的平台</h2><p>同一篇内容，在不同平台的爆点不一样。</p></div></div><div className="platform-picker">{(Object.keys(platforms) as Platform[]).map(key => <button type="button" key={key} className={platform === key ? 'selected' : ''} onClick={() => { setPlatform(key); if (result && key !== resultPlatform) setNotice(`当前结果来自${resultLabel}，切换后请重新拆解以生成${platforms[key].label}版本。`); }}><span className={`platform-dot ${key}`}>{platforms[key].mark}</span><span><strong>{platforms[key].label}</strong><small>{platforms[key].description}</small></span>{platform === key && <StudioIcon name="check" size={16} />}</button>)}</div><div className="composer-divider" /><div className="composer-panel-head"><span className="step-badge">02</span><div><h2>放入参考内容</h2><p>可以贴正文，也可以先放原文链接。</p></div></div><div className="breakdown-source-tabs"><button className={sourceType === 'text' ? 'active' : ''} onClick={() => setSourceType('text')}>粘贴内容</button><button className={sourceType === 'url' ? 'active' : ''} onClick={() => setSourceType('url')}>网页链接</button></div><textarea className="breakdown-input" value={input} onChange={e => setInput(e.target.value)} placeholder={sourceType === 'url' ? 'https://…\n模型可访问时会尝试读取原文；访问失败会明确标记。' : '把对标账号的爆款文章、笔记、口播稿或卡片文案粘贴进来…'} rows={13} /><label className="profile-consent"><input type="checkbox" checked={useProfile} onChange={e => setUseProfile(e.target.checked)} disabled={!profile} /><span><strong>{profile ? '结合我的写作偏好生成原创角度' : '暂无可用写作偏好'}</strong><small>只发送平台定位、读者和语气，不把参考作者身份写进你的内容。</small></span></label><button className="primary breakdown-submit" disabled={busy || adaptBusy || !input.trim()} onClick={() => void run()}><StudioIcon name="spark" size={17} />{busy ? '正在拆解…' : `拆解这条${current.label}内容`}</button>{busy && <button className="secondary breakdown-cancel" onClick={() => controller.current?.abort()}>停止等待</button>}<small className="truth-note">没有可用模型服务时会明确阻断，不会生成虚假的拆解数据。</small><small className="truth-note">输入和结果会自动保存在本机，切换页面或刷新后可以继续。</small><div className="adaptation-callout"><div className="composer-panel-head"><span className="step-badge">03</span><div><h2>基于参考，生成我的版本</h2><p>保留主题、核心事实和信息骨架，重写表达、段落组织与原创增量。</p></div></div><button className="secondary adaptation-submit" disabled={busy || adaptBusy || !input.trim()} onClick={() => void adapt()}><StudioIcon name="spark" size={16} />{adaptBusy ? '正在生成我的版本…' : `生成${current.label}二次创作`}</button>{adaptBusy && <button className="quiet-button adaptation-cancel" onClick={() => adaptController.current?.abort()}>停止等待</button>}<small className="truth-note">不会逐句替换或拼接原文；独特案例、数据和经历需要换成你能核验的材料。</small></div></section><section className="breakdown-output-panel"><div className="output-panel-head"><div><span className="page-kicker">PLATFORM ANALYSIS</span><h2>{result ? `${resultLabel}拆解结果` : '拆解结果会出现在这里'}</h2></div>{result && <span className="ready-state"><span />可复制</span>}</div>{result ? <><textarea className="breakdown-result" value={result} onChange={e => setResult(e.target.value)} aria-label={`${resultLabel}爆款拆解结果`} /><div className="output-actions"><button className="primary" onClick={() => void copy()}><StudioIcon name="check" size={15} />复制拆解</button><button className="secondary" onClick={download}><StudioIcon name="download" size={15} />下载 Markdown</button><button className="quiet-button" onClick={clearDraft}>清空</button></div></> : <div className="output-placeholder" role={busy ? 'status' : undefined} aria-live="polite"><span><StudioIcon name="spark" size={23} /></span><h3>{busy ? '模型正在返回拆解' : '还没有参考内容'}</h3><p>{busy ? '首次响应可能需要几十秒；超过 5 分钟会自动停止并提示重试。' : '先选平台，再贴一条你想研究的爆款内容。'}</p></div>}{(adaptedResult || adaptBusy) && <section className="adapted-result-card" aria-live="polite"><div className="adapted-result-head"><div><span className="page-kicker">MY VERSION</span><h3>{adaptBusy ? '正在生成我的版本' : `${adaptedLabel}二次创作`}</h3><p>保持参考内容的核心价值，同时完成可识别的表达和内容增量。</p></div>{adaptedResult && <span className="ready-state"><span />可编辑</span>}</div>{adaptedResult ? <><textarea className="adapted-result" value={adaptedResult} onChange={e => setAdaptedResult(e.target.value)} aria-label="我的二次创作结果" /><div className="output-actions"><button className="primary" onClick={() => void copyAdapted()}><StudioIcon name="check" size={15} />复制我的版本</button><button className="secondary" onClick={downloadAdapted}><StudioIcon name="download" size={15} />下载 Markdown</button><button className="secondary" onClick={continueInWorkspace}>带入内容工作区</button><button className="quiet-button" onClick={() => setAdaptedResult('')}>清空</button></div><small className="adapted-boundary">这是一份基于参考的本地草稿，不代表已完成事实核验、真人表达审校或平台发布检查。</small></> : <div className="adapted-placeholder"><span><StudioIcon name="spark" size={19} /></span><p>模型正在重写表达，页面会保留现有拆解结果。</p></div>}</section>}</section></div></>;
}
