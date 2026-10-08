import type { ModelRow } from '../api';

export type ModelProviderId = 'deepseek' | 'openai' | 'anthropic' | 'siliconflow' | 'openrouter' | 'aliyun' | 'custom';
export type ModelSlot = 'openai' | 'anthropic' | 'custom';

export type ModelProviderPreset = {
  id: ModelProviderId;
  label: string;
  description: string;
  slot: ModelSlot;
  /** Provider key used when the backend stores compatible custom providers. */
  providerName?: string;
  baseUrl: string;
  models: string[];
  supportsBaseUrl: boolean;
};

/**
 * The list is deliberately short. It is a starting point for a first setup,
 * not a claim that these are the only supported providers or model IDs.
 */
export const MODEL_PROVIDER_PRESETS: ModelProviderPreset[] = [
  {
    id: 'deepseek',
    label: 'DeepSeek',
    description: '国内直连，默认带出聊天模型',
    slot: 'openai',
    baseUrl: 'https://api.deepseek.com',
    models: ['deepseek-v4-pro', 'deepseek-flash'],
    supportsBaseUrl: true,
  },
  {
    id: 'openai',
    label: 'OpenAI',
    description: '官方 OpenAI API',
    slot: 'openai',
    baseUrl: 'https://api.openai.com/v1',
    models: ['gpt-6-astra', 'gpt-6.1-sol', 'gpt-6-luna'],
    supportsBaseUrl: true,
  },
  {
    id: 'anthropic',
    label: 'Anthropic',
    description: 'Claude 官方 API',
    slot: 'anthropic',
    baseUrl: '',
    models: ['claude-opus-5-5', 'claude-sonnet-5-5', 'claude-haiku-4-5-20251001'],
    supportsBaseUrl: false,
  },
  {
    id: 'siliconflow',
    label: '硅基流动',
    description: '兼容接口，模型选择多',
    slot: 'openai',
    baseUrl: 'https://api.siliconflow.cn/v1',
    models: ['deepseek-ai/DeepSeek-V3', 'Qwen/Qwen3-32B'],
    supportsBaseUrl: true,
  },
  {
    id: 'openrouter',
    label: 'OpenRouter',
    description: '一个 Key 使用多家模型',
    slot: 'openai',
    baseUrl: 'https://openrouter.ai/api/v1',
    models: ['openai/gpt-6.1-sol', 'deepseek/deepseek-v4-pro'],
    supportsBaseUrl: true,
  },
  {
    id: 'aliyun',
    label: '阿里云百炼',
    description: '兼容接口，支持百炼免费额度模型',
    slot: 'custom',
    providerName: 'aliyun-bailian',
    baseUrl: 'https://dashscope.aliyuncs.com/compatible-mode/v1',
    models: ['qwen3.7-flash-2026-07-15', 'qwen3.8-flash', 'deepseek-v4-flash-0731', 'qwen3.8-max-0902'],
    supportsBaseUrl: true,
  },
  {
    id: 'custom',
    label: '其他兼容服务',
    description: '填写自己的地址和模型 ID',
    slot: 'custom',
    baseUrl: '',
    models: [],
    supportsBaseUrl: true,
  },
];

export const CUSTOM_MODEL_VALUE = '__custom_model__';

export const providerPreset = (id: ModelProviderId) =>
  MODEL_PROVIDER_PRESETS.find((preset) => preset.id === id) ?? MODEL_PROVIDER_PRESETS[0];

export const normalizeBaseUrl = (value: string) => value.trim().replace(/\/$/, '').toLowerCase();

export const editableRowFor = (rows: ModelRow[], preset: ModelProviderPreset) => {
  const candidates = rows.filter((row) => row.slot === preset.slot);
  if (preset.providerName) return candidates.find((row) => row.name?.toLowerCase() === preset.providerName) ?? null;
  if (preset.slot !== 'openai' || !preset.baseUrl) return candidates[0] ?? null;
  return candidates.find((row) => normalizeBaseUrl(row.baseUrl) === normalizeBaseUrl(preset.baseUrl)) ?? null;
};

export const inferProviderPreset = (rows: ModelRow[]): ModelProviderId => {
  const eligible = (candidate: ModelRow) => candidate.slot === 'openai' || candidate.slot === 'anthropic' || candidate.slot === 'custom';
  // The API returns all configured providers. Prefer the configured primary
  // row so adding Aliyun does not make a reload silently fall back to an old
  // DeepSeek/OpenAI row that happens to be listed first.
  const row = rows.find((candidate) => candidate.role === '主' && eligible(candidate)) ?? rows.find(eligible);
  if (!row) return 'deepseek';
  if (row.slot === 'anthropic') return 'anthropic';
  if (row.slot === 'custom') {
    const matched = MODEL_PROVIDER_PRESETS.find((preset) => preset.providerName === row.name?.toLowerCase());
    return matched?.id ?? 'custom';
  }
  const matched = MODEL_PROVIDER_PRESETS.find(
    (preset) => preset.slot === 'openai' && normalizeBaseUrl(row.baseUrl) === normalizeBaseUrl(preset.baseUrl),
  );
  if (matched) return matched.id;
  if (row.model.startsWith('deepseek')) return 'deepseek';
  return 'openai';
};

export const isPresetModel = (preset: ModelProviderPreset, value: string) => preset.models.includes(value);
