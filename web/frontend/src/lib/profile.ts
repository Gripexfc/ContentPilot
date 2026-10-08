import type { Platform, PlatformProfile, ProfileSnapshot } from '../api';

export const splitList = (value: string): string[] =>
  [...new Set(value.split(/[、，,\n]/).map(item => item.trim()).filter(Boolean))];
export const joinList = (value: string[] | undefined): string => (value ?? []).join('、');
export const formatVersionLabel = (versionNo: number, createdAt: string): string =>
  `版本 ${versionNo} · ${new Date(createdAt).toLocaleString('zh-CN', { hour12: false })}`;
export const platformLabels = { wechat: '公众号', xiaohongshu: '小红书', douyin: '抖音' } as const;
export const platformKeys = Object.keys(platformLabels) as Platform[];
export const emptyPlatform = (): PlatformProfile => ({ positioning: '', audience: '', tone: '', format_preferences: [] });

// Defaults describe an editorial preference, never an invented identity or audience fact.
export const createDefaultProfile = (): ProfileSnapshot => ({
  identity: { display_name: '', profession: '', bio: '' }, experiences: [], domains: [],
  pillars: ['实用教程', '案例复盘'], readers: [],
  voice: { tone: '清晰直接，少用术语', examples: [] },
  content_defaults: { positioning: '围绕读者问题，提供实用方法和判断依据', format_preferences: ['先说明问题', '给出具体方法', '自然结束'] },
  goals: { priorities: ['建立信任'] },
  boundaries: { forbidden_words: [], sensitive_topics: [], unwanted_expressions: ['夸大承诺', '空泛套话'] },
  platforms: Object.fromEntries(platformKeys.map(key => [key, emptyPlatform()])), evidence_refs: [],
});

export const hasPlatformOverrides = (profile: ProfileSnapshot, platform: Platform) => {
  const value = profile.platforms[platform];
  return !!value && !!(value.positioning.trim() || value.audience.trim() || value.tone.trim() || value.format_preferences.length);
};

export const resolvePlatformProfile = (profile: ProfileSnapshot, platform: Platform): PlatformProfile => {
  const own = profile.platforms[platform] || emptyPlatform();
  return {
    positioning: own.positioning.trim() || profile.content_defaults?.positioning.trim() || '围绕读者问题，提供实用方法和判断依据',
    audience: own.audience.trim() || profile.readers.map(reader => `${reader.name}${reader.problems.length ? `（${reader.problems.join('、')}）` : ''}`).join('、') || '根据本次主题确定读者，不假设已有受众数据',
    tone: own.tone.trim() || profile.voice.tone.trim() || '清晰直接，少用术语',
    format_preferences: own.format_preferences.length ? own.format_preferences : profile.content_defaults?.format_preferences || [],
  };
};

// Shared by creation and reference analysis so the preview matches what is sent.
// Identity, private experiences and evidence locations remain out of model context.
export const profilePrompt = (profile: ProfileSnapshot | null, platform: Platform): string => {
  if (!profile) return '当前还没有完整的写作偏好，请保持具体、克制、不要虚构经历。';
  const effective = resolvePlatformProfile(profile, platform);
  return [
    `运营目标：${joinList(profile.goals.priorities) || '围绕本次任务提供帮助'}`,
    `内容领域：${joinList(profile.domains) || '以本次主题为准'}`,
    `常做内容：${joinList(profile.pillars) || '以本次任务为准'}`,
    `目标读者：${effective.audience}`,
    `内容定位：${effective.positioning}`,
    `表达语气：${effective.tone}`,
    `结构偏好：${joinList(effective.format_preferences) || '按平台自然表达'}`,
    `禁用词：${joinList(profile.boundaries.forbidden_words) || '无'}`,
    `避免表达：${joinList(profile.boundaries.unwanted_expressions) || '无'}`,
  ].join('\n');
};

export const toProfileForm = (source: ProfileSnapshot) => ({
  source,
  name: source.identity.display_name, role: source.identity.profession, bio: source.identity.bio,
  domains: joinList(source.domains), pillars: joinList(source.pillars), goals: joinList(source.goals.priorities),
  audience: source.readers[0]?.name || '', problems: (source.readers[0]?.problems || []).join('\n'),
  tone: source.voice.tone,
  positioning: source.content_defaults?.positioning || '',
  formats: joinList(source.content_defaults?.format_preferences),
  forbidden: joinList(source.boundaries.forbidden_words), sensitive: source.boundaries.sensitive_topics.join('\n'),
  unwanted: joinList(source.boundaries.unwanted_expressions), evidence: source.evidence_refs.join('\n'),
  platforms: Object.fromEntries(platformKeys.map(platform => {
    const value = source.platforms[platform] || emptyPlatform();
    return [platform, { ...value, formats: joinList(value.format_preferences) }];
  })) as Record<Platform, PlatformProfile & { formats: string }>,
});
export type ProfileForm = ReturnType<typeof toProfileForm>;
export const fromProfileForm = (form: ProfileForm): ProfileSnapshot => ({
  ...form.source,
  identity: { display_name: form.name.trim(), profession: form.role.trim(), bio: form.bio.trim() },
  domains: splitList(form.domains), pillars: splitList(form.pillars), goals: { priorities: splitList(form.goals) },
  readers: [...(form.audience.trim() ? [{ name: form.audience.trim(), problems: splitList(form.problems) }] : []), ...form.source.readers.slice(1)],
  voice: { ...form.source.voice, tone: form.tone.trim() },
  content_defaults: { positioning: form.positioning.trim(), format_preferences: splitList(form.formats) },
  boundaries: { forbidden_words: splitList(form.forbidden), sensitive_topics: form.sensitive.split('\n').map(v => v.trim()).filter(Boolean), unwanted_expressions: splitList(form.unwanted) },
  evidence_refs: form.evidence.split('\n').map(v => v.trim()).filter(Boolean),
  platforms: { ...form.source.platforms, ...Object.fromEntries(platformKeys.map(platform => {
    const value = form.platforms[platform];
    return [platform, { positioning: value.positioning.trim(), audience: value.audience.trim(), tone: value.tone.trim(), format_preferences: splitList(value.formats) }];
  })) },
});
