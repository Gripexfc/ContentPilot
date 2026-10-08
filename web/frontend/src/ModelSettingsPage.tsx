import { useEffect, useMemo, useRef, useState, type KeyboardEvent } from 'react';
import {
  ApiError,
  discoverModels,
  getModelChannels,
  getModelGatewayStatus,
  saveModelConfig,
  selftestModel,
  type ModelGatewayStatus,
  type ModelRow,
  type ModelSelftestResult,
} from './api';
import { Message, PageHeader } from './components/shared';
import { StudioIcon } from './components/StudioIcon';
import {
  CUSTOM_MODEL_VALUE,
  editableRowFor,
  inferProviderPreset,
  MODEL_PROVIDER_PRESETS,
  normalizeBaseUrl,
  providerPreset,
  type ModelProviderId,
  type ModelProviderPreset,
} from './lib/modelSettings';

const displayBaseUrl = (row: ModelRow | null) => {
  const value = row?.baseUrl?.trim() ?? '';
  return value && !['官方', '（未配置）'].includes(value) ? value : '';
};

type ModelAction = 'read' | 'save' | 'test';

const modelErrorText = (error: unknown, action: ModelAction) => {
  const message = error instanceof Error ? error.message : '';
  const status = error instanceof ApiError ? error.status : 0;
  const networkFailure = /failed to fetch|networkerror|load failed/i.test(message);
  if (networkFailure) {
    if (action === 'read') return '暂时读不到本地配置。请确认 CreatorOS 服务仍在运行，然后点击“重新读取”。';
    if (action === 'save') return '暂时无法保存配置，本地服务没有响应。请确认 CreatorOS 服务仍在运行后重试。';
    return '模型测试没有完成，本地服务没有响应。请确认 CreatorOS 服务仍在运行后重试。';
  }
  if (status >= 500 || /internal server error/i.test(message)) {
    if (action === 'save') return '本地服务保存配置时出错了。请重启 CreatorOS 后再试。';
    if (action === 'test') return '本地服务检查配置时出错了。请重启 CreatorOS 后再试。';
    return '本地服务读取配置时出错了。请重启 CreatorOS 后再试。';
  }
  return message || '操作没有完成，请稍后再试。';
};

const modelTestDetail = (detail: string) => {
  const value = detail.toLowerCase();
  if (/(arrearage|overdue|欠费|账户状态)/.test(value)) return '模型账户欠费或状态异常，请到服务商控制台处理欠费并开启可用额度后重试。';
  if (/(401|403)/.test(value)) return 'API Key 无效或没有权限，请检查是否过期、复制不完整，或已被撤销。';
  if (/(402|billing|insufficient balance|insufficient credit|余额不足|额度)/.test(value)) return '模型账户余额或额度不足，请到服务商控制台充值，或更换可用 API Key。';
  if (/404/.test(value)) return '服务地址可以访问，但接口地址不对，请检查服务地址。';
  if (/400/.test(value)) return '模型请求未被服务商接受，可能是模型尚未开启或模型 ID 不正确；请到服务商控制台启用模型后重试。';
  if (/429/.test(value)) return '请求过于频繁或额度不足，请稍后重试。';
  if (/(500|502|503|504)/.test(value)) return '服务商暂时不可用，请稍后重试。';
  if (/(timeout|timed out|urlopen error|network|connection|name or service)/.test(value)) return '无法连接服务商，请检查网络和服务地址。';
  return '服务未返回成功，请检查服务地址和 API Key。';
};

type ModelDropdownOption = { value: string; label: string; description?: string };

function ModelDropdown({ id, value, options, disabled, onChange }: {
  id: string;
  value: string;
  options: ModelDropdownOption[];
  disabled?: boolean;
  onChange: (value: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState(0);
  const rootRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const optionRefs = useRef<Array<HTMLButtonElement | null>>([]);
  const selectedIndex = Math.max(0, options.findIndex(option => option.value === value));
  const selected = options[selectedIndex];
  const menuId = `${id}-menu`;

  useEffect(() => {
    if (!open) return undefined;
    const isInside = (target: EventTarget | null) => target instanceof Node && Boolean(rootRef.current?.contains(target));
    const closeWhenOutside = (event: PointerEvent) => {
      if (!isInside(event.target)) setOpen(false);
    };
    // Keep the menu open while its own list is being scrolled. The capture
    // listener also sees descendant scroll events, so without this guard a
    // wheel/touch scroll closes the menu on the first frame.
    const closeWhenScrolled = (event: Event) => {
      if (isInside(event.target)) return;
      setOpen(false);
    };
    document.addEventListener('pointerdown', closeWhenOutside);
    window.addEventListener('scroll', closeWhenScrolled, true);
    return () => {
      document.removeEventListener('pointerdown', closeWhenOutside);
      window.removeEventListener('scroll', closeWhenScrolled, true);
    };
  }, [open]);

  useEffect(() => {
    if (open) setActiveIndex(selectedIndex);
  }, [open, selectedIndex]);

  useEffect(() => {
    if (!open) return;
    const activeOption = optionRefs.current[activeIndex];
    activeOption?.scrollIntoView?.({ block: 'nearest' });
  }, [activeIndex, open]);

  const choose = (option: ModelDropdownOption, index: number) => {
    onChange(option.value);
    setActiveIndex(index);
    setOpen(false);
    requestAnimationFrame(() => triggerRef.current?.focus());
  };
  const openMenu = () => {
    if (disabled || !options.length) return;
    setActiveIndex(selectedIndex);
    setOpen(true);
  };
  const move = (direction: 1 | -1) => {
    setActiveIndex(index => (index + direction + options.length) % options.length);
  };
  const handleKeyDown = (event: KeyboardEvent<HTMLButtonElement>) => {
    if (event.key === 'Escape') {
      if (open) { event.preventDefault(); setOpen(false); }
      return;
    }
    if (event.key === 'Tab') {
      if (open) setOpen(false);
      return;
    }
    if (event.key === 'ArrowDown') {
      event.preventDefault();
      if (!open) openMenu(); else move(1);
      return;
    }
    if (event.key === 'ArrowUp') {
      event.preventDefault();
      if (!open) openMenu(); else move(-1);
      return;
    }
    if (event.key === 'Home' && open) { event.preventDefault(); setActiveIndex(0); return; }
    if (event.key === 'End' && open) { event.preventDefault(); setActiveIndex(options.length - 1); return; }
    if ((event.key === 'Enter' || event.key === ' ') && open) {
      event.preventDefault();
      choose(options[activeIndex], activeIndex);
    }
  };

  return <div className={`model-select ${open ? 'is-open' : ''}`} ref={rootRef}>
    <button
      ref={triggerRef}
      id={id}
      type="button"
      className="model-select-trigger"
      role="combobox"
      aria-haspopup="listbox"
      aria-expanded={open}
      aria-controls={menuId}
      aria-activedescendant={open ? `${id}-option-${activeIndex}` : undefined}
      disabled={disabled}
      onClick={() => open ? setOpen(false) : openMenu()}
      onKeyDown={handleKeyDown}
    >
      <span className="model-select-value">
        <strong>{selected?.label || '请选择'}</strong>
        {selected?.description && <small>{selected.description}</small>}
      </span>
      <StudioIcon name="chevron-down" size={16} />
    </button>
    {open && <div id={menuId} className="model-select-menu" role="listbox" aria-labelledby={id}>
      {options.map((option, index) => <button
        id={`${id}-option-${index}`}
        key={`${option.value}-${index}`}
        ref={node => { optionRefs.current[index] = node; }}
        type="button"
        role="option"
        aria-selected={option.value === value}
        className={index === activeIndex ? 'is-active' : ''}
        onMouseDown={event => event.preventDefault()}
        onMouseEnter={() => setActiveIndex(index)}
        onClick={() => choose(option, index)}
      >
        <span><strong>{option.label}</strong>{option.description && <small>{option.description}</small>}</span>
        {option.value === value && <StudioIcon name="check" size={16} />}
      </button>)}
    </div>}
  </div>;
}

export function ModelSettingsPage() {
  const [rows, setRows] = useState<ModelRow[]>([]);
  const [providerId, setProviderId] = useState<ModelProviderId>('deepseek');
  const [model, setModel] = useState('');
  const [baseUrl, setBaseUrl] = useState('');
  const [key, setKey] = useState('');
  const [name, setName] = useState('');
  const [primary, setPrimary] = useState(true);
  const [loading, setLoading] = useState(true);
  const [hydrated, setHydrated] = useState(false);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [notice, setNotice] = useState('');
  const [error, setError] = useState('');
  const [testResults, setTestResults] = useState<ModelSelftestResult[]>([]);
  const [gateway, setGateway] = useState<ModelGatewayStatus | null>(null);
  const [discoveredModels, setDiscoveredModels] = useState<string[]>([]);
  const [discoveringModels, setDiscoveringModels] = useState(false);
  const [discoveryDetail, setDiscoveryDetail] = useState('');
  const discoveryRequestRef = useRef(0);

  const preset = useMemo(() => providerPreset(providerId), [providerId]);
  const current = useMemo(() => editableRowFor(rows, preset), [rows, preset]);
  const availableModels = useMemo(
    () => Array.from(new Set([...discoveredModels, ...preset.models].map(item => item.trim()).filter(Boolean))),
    [discoveredModels, preset.models],
  );
  const modelIsKnown = availableModels.includes(model);
  const endpointChanged = Boolean(
    current?.keyMasked && preset.supportsBaseUrl && normalizeBaseUrl(baseUrl) !== normalizeBaseUrl(displayBaseUrl(current)),
  );
  const needsKey = !key.trim() && (!current?.keyMasked || endpointChanged);

  const hydrate = (nextPreset: ModelProviderPreset, row: ModelRow | null) => {
    setProviderId(nextPreset.id);
    setModel(row?.model || nextPreset.models[0] || '');
    setBaseUrl(nextPreset.supportsBaseUrl ? displayBaseUrl(row) || nextPreset.baseUrl : '');
    setName(nextPreset.slot === 'custom' ? row?.name || nextPreset.providerName || '' : '');
    setPrimary(row ? row.role === '主' : true);
    setKey('');
  };

  const discoverFor = async (
    nextPreset: ModelProviderPreset,
    row: ModelRow | null,
    overrides: { baseUrl?: string; key?: string; model?: string; name?: string } = {},
  ) => {
    const requestId = ++discoveryRequestRef.current;
    const requestedBase = (overrides.baseUrl ?? (nextPreset.supportsBaseUrl ? displayBaseUrl(row) || nextPreset.baseUrl : '')).trim();
    const requestedKey = overrides.key ?? '';
    const requestedModel = overrides.model ?? row?.model ?? '';
    const requestedName = overrides.name ?? row?.name ?? nextPreset.providerName ?? '';
    const storedBase = displayBaseUrl(row);
    setDiscoveryDetail('');
    setDiscoveringModels(true);
    if (!requestedBase) {
      if (requestId === discoveryRequestRef.current) {
        setDiscoveredModels([]);
        setDiscoveryDetail('暂未读取到模型列表，可手填模型 ID。');
        setDiscoveringModels(false);
      }
      return;
    }
    // Do not let a saved key follow a newly entered endpoint. The backend also
    // enforces this binding, but avoiding the request here keeps the UI honest.
    if (!requestedKey && row?.keyMasked && normalizeBaseUrl(requestedBase) !== normalizeBaseUrl(storedBase)) {
      if (requestId === discoveryRequestRef.current) {
        setDiscoveredModels([]);
        setDiscoveryDetail('服务地址已变化，请先填写新的 API Key 才能读取模型。');
        setDiscoveringModels(false);
      }
      return;
    }
    try {
      const response = await discoverModels({
        slot: nextPreset.slot,
        name: nextPreset.slot === 'custom' ? requestedName : undefined,
        model: requestedModel,
        baseUrl: requestedBase,
        key: requestedKey,
      });
      if (requestId !== discoveryRequestRef.current) return;
      const remoteModels = Array.from(new Set((response.models || []).map(item => item.trim()).filter(Boolean)));
      setDiscoveredModels(remoteModels);
      setDiscoveryDetail(response.available && remoteModels.length
        ? `已读取 ${remoteModels.length} 个可用模型。`
        : response.detail || '暂未读取到模型列表，可手填模型 ID。');
    } catch {
      if (requestId !== discoveryRequestRef.current) return;
      setDiscoveredModels([]);
      setDiscoveryDetail('暂未读取到模型列表，可手填模型 ID。');
    } finally {
      if (requestId === discoveryRequestRef.current) setDiscoveringModels(false);
    }
  };

  const load = async () => {
    setLoading(true);
    setError('');
    discoveryRequestRef.current += 1;
    setDiscoveredModels([]);
    setDiscoveryDetail('');
    setDiscoveringModels(false);
    const [modelsResult, gatewayResult] = await Promise.allSettled([getModelChannels(), getModelGatewayStatus()]);
    if (modelsResult.status === 'fulfilled') {
      const nextRows = modelsResult.value.channels.chat.rows || [];
      const nextProvider = providerPreset(inferProviderPreset(nextRows));
      const nextRow = editableRowFor(nextRows, nextProvider);
      setRows(nextRows);
      hydrate(nextProvider, nextRow);
      void discoverFor(nextProvider, nextRow);
      setHydrated(true);
    } else {
      const nextProvider = providerPreset('deepseek');
      setRows([]);
      hydrate(nextProvider, null);
      setHydrated(true);
      setError(`${modelErrorText(modelsResult.reason, 'read')} 页面仍可继续填写新的配置。`);
    }
    if (gatewayResult.status === 'fulfilled') setGateway(gatewayResult.value);
    setLoading(false);
  };

  useEffect(() => {
    void load();
  }, []);

  const selectProvider = (value: ModelProviderId) => {
    const nextPreset = providerPreset(value);
    const nextRow = editableRowFor(rows, nextPreset);
    setDiscoveredModels([]);
    hydrate(nextPreset, nextRow);
    void discoverFor(nextPreset, nextRow);
    setNotice('');
    setError('');
    setTestResults([]);
  };

  const save = async (): Promise<boolean> => {
    if (!model.trim()) {
      setError('请选择或填写一个模型。');
      return false;
    }
    if (preset.slot === 'custom' && !preset.providerName && (!name.trim() || !baseUrl.trim())) {
      setError('自定义服务需要填写服务商标识和地址。');
      return false;
    }
    if (preset.supportsBaseUrl && !baseUrl.trim()) {
      setError('请补充服务地址，或从服务商下拉中重新选择。');
      return false;
    }
    if (needsKey) {
      setError(endpointChanged ? '服务地址已变化，请重新填写 API Key。' : '首次配置需要填写 API Key。');
      return false;
    }

    setSaving(true);
    setError('');
    setNotice('');
    setTestResults([]);
    try {
      const response = await saveModelConfig([{
        slot: preset.slot,
        name: preset.slot === 'custom' ? (preset.providerName || name.trim().toLowerCase()) : undefined,
        model: model.trim(),
        baseUrl: preset.supportsBaseUrl ? baseUrl.trim() : '',
        key: key.trim(),
        primary,
      }]);
      const nextRows = response.channels.chat.rows || [];
      const nextRow = editableRowFor(nextRows, preset);
      setRows(nextRows);
      setKey('');
      void discoverFor(preset, nextRow, { baseUrl: baseUrl.trim(), key: key.trim(), model: model.trim(), name });
      const nextGateway = await getModelGatewayStatus().catch(() => gateway);
      setGateway(nextGateway);
      const gatewayHint = nextGateway?.gatewayOnline
        ? '模型服务已运行，但还没完成验证；请点击“保存并测试”。'
        : '配置已保存，模型服务还没启动；启动后点击“保存并测试”。';
      setNotice(`${preset.label} 配置已保存。${gatewayHint}${response.note ? ` ${response.note}` : ''}`);
      return true;
    } catch (e) {
      setError(`保存失败：${modelErrorText(e, 'save')}`);
      return false;
    } finally {
      setSaving(false);
    }
  };

  const test = async () => {
    setTesting(true);
    setError('');
    setNotice('');
    setTestResults([]);
    try {
      const response = await selftestModel();
      setTestResults(response.results || []);
      setGateway(await getModelGatewayStatus().catch(() => gateway));
      if (!response.results.length) {
        setNotice('配置已保存，但暂时没有可检查的模型。请确认 API Key 后再试。');
      } else if (response.results.every(result => result.ok)) {
          setNotice('模型测试通过：服务地址、API Key、模型权限和账户额度均已完成一次最小生成验证。');
      } else {
        // save() 之后 rows 可能要等下一次渲染才更新，因此这里同时把本次表单
        // 地址视为主模型地址，避免刚保存的主模型被误判成备份。
        const primaryBases = new Set(primaryBaseUrls);
        if (primary && preset.supportsBaseUrl && baseUrl.trim()) primaryBases.add(normalizeBaseUrl(baseUrl));
        const primaryResults = response.results.filter(result => primaryBases.has(normalizeBaseUrl(result.baseUrl)));
        const primaryPassed = primaryResults.some(result => result.ok);
        const backupFailed = response.results
          .filter(result => !primaryBases.has(normalizeBaseUrl(result.baseUrl)))
          .some(result => !result.ok);
        if (primaryPassed && backupFailed) {
          setNotice('主模型测试通过，另有备份模型失败。配置已保存，当前生成会使用主模型。');
        } else if (primaryPassed) {
          setNotice('主模型测试通过。配置已保存，可以开始创作。');
        } else if (response.results.some(result => result.ok)) {
          setNotice('主模型测试未通过，但有备份模型通过；请查看下方结果并处理主模型配置。');
        } else {
          setNotice('模型测试失败，请查看下方结果。配置仍已保存。');
        }
      }
    } catch (e) {
      setError(`模型测试失败：${modelErrorText(e, 'test')}`);
    } finally {
      setTesting(false);
    }
  };

  const saveAndTest = async () => {
    const saved = await save();
    if (saved) await test();
  };

  // 自测可能同时检查历史备份和当前主模型。备份失败不能覆盖主模型已通过的结论，
  // 否则用户会看到“模型还不能生成”，但实际创作请求已经可以使用主模型。
  const primaryBaseUrls = new Set(
    rows.filter(row => row.role === '主').map(row => normalizeBaseUrl(displayBaseUrl(row))).filter(Boolean),
  );
  const isPrimaryResult = (result: ModelSelftestResult) => primaryBaseUrls.has(normalizeBaseUrl(result.baseUrl));
  const primaryResults = testResults.filter(isPrimaryResult);
  const backupResults = testResults.filter(result => !isPrimaryResult(result));
  const primaryPassed = primaryResults.some(result => result.ok);
  const primaryFailed = primaryResults.length > 0 && primaryResults.every(result => !result.ok);
  const backupFailed = backupResults.some(result => !result.ok);
  // 兼容旧配置无法从 rows 找到主模型的情况：只有所有结果都失败时才判定整体失败。
  const testFailed = primaryResults.length ? primaryFailed : testResults.length > 0 && testResults.every(result => !result.ok);
  const partialBackupFailure = primaryPassed && backupFailed;
  const gatewayLabel = loading
    ? '正在读取'
    : primaryPassed && partialBackupFailure
      ? '主模型可用，备用模型异常'
      : primaryPassed
        ? '模型已验证'
        : testFailed
          ? '模型验证失败'
          : gateway?.gatewayOnline
            ? '模型服务已运行，尚未验证'
            : gateway?.configured
              ? '配置已保存，模型服务未启动'
              : '还没配置模型服务';
  const gatewayTitle = primaryPassed
    ? '模型已验证，可以开始创作'
    : testFailed
      ? '模型暂时不可用'
      : gateway?.gatewayOnline
        ? '模型服务已运行，尚未验证'
        : gateway?.configured
          ? '配置已保存，模型服务还没启动'
          : '先配置并测试模型';
  const gatewayDescription = primaryPassed
    ? partialBackupFailure
      ? `主模型已经通过一次最小生成测试，可以开始创作；${backupResults.filter(result => !result.ok).length} 个备用模型检查失败，可稍后处理。`
      : '主模型已经通过一次最小生成测试，可以开始创作。你可以回到研究参考内容或开始创作。'
    : testFailed
      ? '模型服务在线，但主模型测试没有通过；请按下方结果处理服务地址、API Key、模型编号或账户额度。'
      : gateway?.gatewayOnline
        ? '模型服务已经运行，但还没有验证能否生成内容。点击“保存并测试”，检查 API Key、模型权限和账户额度。'
        : gateway?.configured
          ? '配置已经保存，但模型服务还没启动；启动后点击“保存并测试”。'
          : '先选择模型服务商、模型并填写 API Key，再点击“保存并测试”。';
  const modelOptions = model && !modelIsKnown ? [model, ...availableModels] : availableModels;

  return (
    <>
      <PageHeader title="模型设置" description="选择模型服务商和模型，填写 API Key（访问密钥）后即可测试模型服务。" />
      {notice && <Message>{notice}</Message>}
      {error && <Message error>{error}</Message>}

      <div className="model-settings-layout">
        <section className="model-config-panel" aria-labelledby="model-config-title" aria-busy={loading}>
          <div className="model-config-heading">
            <div>
              <h2 id="model-config-title">配置模型服务</h2>
              <p>选择模型服务商和模型，通常只需要补充 API Key（访问密钥）。</p>
            </div>
            <span className={`model-status ${gateway?.gatewayOnline ? 'online' : ''}`}><i aria-hidden="true" />{gatewayLabel}</span>
          </div>

          <div className="model-fields">
            <div className="model-field">
                <div className="model-field-label"><label htmlFor="model-provider">模型服务商</label><small>{preset.description}</small></div>
              <ModelDropdown
                id="model-provider"
                value={providerId}
                options={MODEL_PROVIDER_PRESETS.map(item => ({ value: item.id, label: item.label, description: item.description }))}
                onChange={value => selectProvider(value as ModelProviderId)}
                disabled={loading || saving}
              />
            </div>

            <div className="model-field">
              <div className="model-field-label"><label htmlFor="model-choice">模型</label><small>不确定时先用默认选项</small></div>
              <ModelDropdown
                id="model-choice"
                value={modelIsKnown ? model : CUSTOM_MODEL_VALUE}
                options={[
                  ...modelOptions.map(item => ({ value: item, label: item })),
                  { value: CUSTOM_MODEL_VALUE, label: model && !modelIsKnown ? `当前配置 · ${model}` : '其他模型 ID…', description: model && !modelIsKnown ? '编辑下方的模型 ID' : '粘贴服务商提供的模型 ID' },
                ]}
                onChange={value => setModel(value === CUSTOM_MODEL_VALUE ? '' : value)}
                disabled={loading || saving}
              />
              {(discoveringModels || discoveryDetail) && <small className="model-catalog-status" aria-live="polite">{discoveringModels ? '正在读取服务商可用模型…' : discoveryDetail}</small>}
              {!modelIsKnown && <input id="model-custom" className="model-custom-input" value={model} onChange={(event) => setModel(event.target.value)} placeholder="粘贴服务商提供的模型名称或编号" autoComplete="off" />}
            </div>

            <div className="model-field model-key-field">
              <div className="model-field-label"><label htmlFor="model-key">API Key（访问密钥）</label><small>{current?.keyMasked ? `已保存 ${current.keyMasked}，留空即可沿用` : '服务商提供，只在本机保存，不会显示明文'}</small></div>
              <input id="model-key" className="model-key-input" type="password" value={key} onChange={(event) => setKey(event.target.value)} onBlur={() => void discoverFor(preset, current, { baseUrl, key, model, name })} placeholder={current?.keyMasked ? '已配置，留空表示沿用' : '粘贴 API Key'} autoComplete="new-password" />
            </div>
          </div>

          <details className="model-advanced">
            <summary>高级设置 <span>通常不用改</span></summary>
            <div className="model-advanced-grid">
              {preset.slot === 'custom' && !preset.providerName && <label>服务商标识<input value={name} onChange={(event) => setName(event.target.value)} placeholder="例如 my-provider" autoComplete="off" /></label>}
              {preset.supportsBaseUrl && <label>服务地址<input value={baseUrl} onChange={(event) => setBaseUrl(event.target.value)} onBlur={() => void discoverFor(preset, current, { baseUrl, key, model, name })} placeholder="https://api.example.com/v1" autoComplete="url" /></label>}
              <label className="model-primary-toggle"><input type="checkbox" checked={primary} onChange={(event) => setPrimary(event.target.checked)} />设为内容生成主模型</label>
            </div>
            <p>只有使用自建或代理服务时才需要修改这里。更换服务地址后必须重新填写 API Key。</p>
          </details>

          <div className="model-action-row">
            <button className="primary" disabled={loading || saving || testing || !hydrated} onClick={() => void saveAndTest()}>{saving ? '保存中…' : testing ? '检查中…' : '保存并测试'}</button>
            <button className="secondary" disabled={loading || saving || testing || !hydrated} onClick={() => void save()}>只保存</button>
            <button className="quiet-button" disabled={loading || saving || testing} onClick={() => void load()}>重新读取</button>
          </div>
          {!!testResults.length && <div className="model-test-results" aria-live="polite">{testResults.map((result) => {
            const primaryResult = isPrimaryResult(result);
            return <div key={result.baseUrl}><strong className={result.ok ? 'model-test-ok' : 'model-test-fail'}>{result.ok ? '最小生成测试通过' : '最小生成测试失败'}</strong><span>{primaryResult ? '主模型' : '备用模型'} · {result.baseUrl}</span><small>{result.ok ? `已完成一次最小生成请求 · ${result.ms}ms` : modelTestDetail(result.detail || '')}</small></div>;
          })}</div>}
        </section>

        <aside className="model-side-panel">
          <div className="model-side-status"><span className="model-side-mark" aria-hidden="true" /><strong>{gatewayTitle}</strong><p>{gatewayDescription}</p></div>
          <div className="model-side-list"><h3>你只需要准备</h3><ul><li>一个模型服务商账号</li><li>一个 API Key（访问密钥）</li><li>一个可用的模型</li></ul></div>
          <details className="model-help"><summary>遇到问题？</summary><p>“保存并测试”会发起一次最小生成请求，验证服务地址、模型、权限和账户额度；请求可能产生极少量费用。通过后再回到内容工作区生成完整内容。</p></details>
        </aside>
      </div>
    </>
  );
}
