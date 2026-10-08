import { describe, expect, it } from 'vitest';
import { editableRowFor, inferProviderPreset, providerPreset } from './modelSettings';

describe('model provider presets', () => {
  it('treats Aliyun Bailian as a named compatible provider', () => {
    const preset = providerPreset('aliyun');
    const row = {
      slot: 'custom', order: 0, name: 'aliyun-bailian', model: 'qwen3.7-flash-2026-07-15',
      baseUrl: preset.baseUrl, keyMasked: '«已配置»', role: '主', result: '已配置',
    };
    expect(preset.providerName).toBe('aliyun-bailian');
    expect(editableRowFor([row], preset)?.model).toBe(row.model);
    const previous = { ...row, name: 'deepseek', slot: 'openai', role: '备' };
    expect(inferProviderPreset([previous, row])).toBe('aliyun');
  });
});
