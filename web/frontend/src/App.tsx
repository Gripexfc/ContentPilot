import { useEffect, useMemo, useRef, useState, type KeyboardEvent } from 'react';
import { QuickCreatePage } from './QuickCreatePage';
import { HotspotsPage } from './HotspotsPage';
import { StudioLibraryPage } from './StudioLibraryPage';
import { StudioProfilePage } from './StudioProfilePage';
import { ContentWorkspace } from './Workspace';
import { BreakdownPage } from './BreakdownPage';
import { ModelSettingsPage } from './ModelSettingsPage';
import { AnalyticsPage } from './AnalyticsPage';
import { PublishCenterPage } from './PublishCenter';
import { DraftCenterPage } from './DraftCenter';
import { OutputsPage } from './OutputsPage';
import { ChatPage } from './ChatPage';
import { SkillsPage } from './SkillsPage';
import { OverviewPage, SettingsPage as AccountsPage } from './Pages';
import { getStatus } from './api';
import { StudioIcon } from './components/StudioIcon';

const routes = [
  ['hotspots', '热点话题', 'compass', '从热点开始'],
  ['breakdown', '研究参考内容', 'spark', '把参考内容变成自己的方法'],
  ['create', '内容工作区', 'pen', '从主题开始'],
  ['library', '内容库', 'file', '继续打磨作品'],
  ['profile', '我的写作偏好', 'settings', '让内容更像你'],
  ['analytics', '账号分析', 'chart', '查看账号表现'],
  ['settings', '模型设置', 'sliders', '配置并测试模型服务'],
  ['accounts', '账号与连接', 'settings', '连接平台账号'],
  ['publish', '发布前检查', 'check', '检查后再交付'],
  ['overview', '工作台总览', 'file', '查看整体进度'],
  ['drafts', '公众号草稿', 'file', '继续编辑公众号草稿'],
  ['outputs', '输出文件', 'file', '查看工作流输出'],
  ['chat', '对话助手', 'spark', '询问和改写'],
  ['skills', '能力说明', 'spark', '查看可用能力'],
] as const;
type RouteKey = (typeof routes)[number][0];
const primaryKeys: readonly RouteKey[] = ['hotspots', 'create', 'library', 'profile', 'publish'];
const utilityKeys: readonly RouteKey[] = ['breakdown', 'analytics', 'settings', 'accounts'];

type ThemeMode = 'dark' | 'light' | 'system';
type ThemeOption = { value: ThemeMode; label: string };
const themeOptions: ThemeOption[] = [
  { value: 'system', label: '跟随系统' },
  { value: 'dark', label: '夜间' },
  { value: 'light', label: '日间' },
];

function ThemeDropdown({ value, onChange }: { value: ThemeMode; onChange: (value: ThemeMode) => void }) {
  const [open, setOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState(0);
  const rootRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const selectedIndex = Math.max(0, themeOptions.findIndex(option => option.value === value));
  const selected = themeOptions[selectedIndex];
  const menuId = 'theme-select-menu';

  useEffect(() => {
    if (!open) return undefined;
    const closeWhenOutside = (event: PointerEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false);
    };
    const closeWhenScrolled = (event: Event) => {
      // The listener uses capture so page scrolling can dismiss the menu, but
      // must not treat the menu's own scroll as an outside scroll. Otherwise
      // a scrollable in-page menu closes on its first wheel/touch movement.
      const target = event.target;
      if (target instanceof Node && rootRef.current?.contains(target)) return;
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

  const choose = (option: ThemeOption, index: number) => {
    onChange(option.value);
    setActiveIndex(index);
    setOpen(false);
    requestAnimationFrame(() => triggerRef.current?.focus());
  };
  const openMenu = () => {
    setActiveIndex(selectedIndex);
    setOpen(true);
  };
  const move = (direction: 1 | -1) => {
    setActiveIndex(index => (index + direction + themeOptions.length) % themeOptions.length);
  };
  const handleKeyDown = (event: KeyboardEvent<HTMLButtonElement>) => {
    if (event.key === 'Escape') {
      if (open) { event.preventDefault(); setOpen(false); }
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
    if (event.key === 'End' && open) { event.preventDefault(); setActiveIndex(themeOptions.length - 1); return; }
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault();
      if (!open) { openMenu(); return; }
      choose(themeOptions[activeIndex], activeIndex);
    }
  };

  return <div className={`theme-select ${open ? 'is-open' : ''}`} ref={rootRef}>
    <button
      ref={triggerRef}
      id="theme-select-trigger"
      type="button"
      className="theme-select-trigger"
      role="combobox"
      aria-label="切换外观"
      aria-haspopup="listbox"
      aria-expanded={open}
      aria-controls={menuId}
      aria-activedescendant={open ? `theme-option-${activeIndex}` : undefined}
      onClick={() => open ? setOpen(false) : openMenu()}
      onKeyDown={handleKeyDown}
    >
      <span>{selected.label}</span>
      <StudioIcon name="chevron-down" size={13} />
    </button>
    {open && <div id={menuId} className="theme-select-menu" role="listbox" aria-labelledby="theme-select-trigger">
      {themeOptions.map((option, index) => <button
        id={`theme-option-${index}`}
        key={option.value}
        type="button"
        role="option"
        aria-selected={option.value === value}
        className={index === activeIndex ? 'is-active' : ''}
        onMouseDown={event => event.preventDefault()}
        onMouseEnter={() => setActiveIndex(index)}
        onClick={() => choose(option, index)}
      >
        <span>{option.label}</span>
        {option.value === value && <StudioIcon name="check" size={14} />}
      </button>)}
    </div>}
  </div>;
}

export const routeFromHash = (hash: string) => {
  const [raw, id = ''] = hash.replace(/^#\/?/, '').split('/');
  const view = raw === 'workspace' ? (id ? 'workspace' : 'create') : routes.some(([key]) => key === raw) ? raw : 'hotspots';
  return { view, id };
};

export default function App() {
  const [route, setRoute] = useState(() => routeFromHash(window.location.hash));
  const [online, setOnline] = useState<boolean | null>(null);
  const [theme, setTheme] = useState<ThemeMode>(() => {
    try {
      const saved = window.localStorage.getItem('creatoros:theme');
      return saved === 'light' || saved === 'system' || saved === 'dark' ? saved : 'light';
    } catch { return 'light'; }
  });
  useEffect(() => {
    const media = window.matchMedia('(prefers-color-scheme: dark)');
    const applyTheme = () => { document.documentElement.dataset.theme = theme === 'system' ? (media.matches ? 'dark' : 'light') : theme; };
    applyTheme();
    try { window.localStorage.setItem('creatoros:theme', theme); } catch { /* Theme still works for this visit. */ }
    media.addEventListener('change', applyTheme);
    return () => media.removeEventListener('change', applyTheme);
  }, [theme]);
  useEffect(() => {
    const change = () => { setRoute(routeFromHash(window.location.hash)); window.scrollTo(0, 0); };
    window.addEventListener('hashchange', change);
    return () => window.removeEventListener('hashchange', change);
  }, []);
  const current = route.view === 'workspace' ? routes.find(([key]) => key === 'create')! : routes.find(([key]) => key === route.view) || routes[1];
  const routeByKey = useMemo(() => new Map(routes.map(routeItem => [routeItem[0], routeItem])), []);
  useEffect(() => { document.title = `知序 · ${current[1]}`; }, [current]);
  const check = (showPending = true) => { if (showPending) setOnline(null); void getStatus().then(() => setOnline(true)).catch(() => setOnline(false)); };
  useEffect(() => {
    check();
    // Keep the shell status honest when the local API is restarted or exits
    // while the browser tab remains open. A one-time check can otherwise keep
    // showing “本地已连接” after a failed generation request.
    const timer = window.setInterval(() => check(false), 15000);
    return () => window.clearInterval(timer);
  }, []);
  const navigate = (path: string) => { window.location.hash = `/${path}`; };
  const renderNav = (keys: readonly RouteKey[]) => keys.map(key => {
    const item = routeByKey.get(key);
    if (!item) return null;
    const [routeKey, label, icon, hint] = item;
    return <a className="studio-nav-item" key={routeKey} href={`#/${routeKey}`} aria-label={label} title={hint} aria-current={(route.view === routeKey || (route.view === 'workspace' && routeKey === 'create')) ? 'page' : undefined}>
      <span className="studio-nav-icon"><StudioIcon name={icon} /></span><span className="studio-nav-label">{label}</span>
      {routeKey === 'profile' && route.view === 'profile' && <span className="studio-nav-count">当前</span>}
    </a>;
  });

  return <div className="studio studio-refactor">
    <a className="studio-skip" href="#main">跳到内容</a>
    <aside className="studio-sidebar">
      <a className="studio-brand" href="#/hotspots" aria-label="知序内容工作台">
        <img className="studio-brand-mark" src="/brand/zixu-mark.svg?v=3" width="32" height="32" alt="" />
        <span className="studio-brand-copy"><strong>知序</strong><small>ZIXU STUDIO</small></span>
      </a>
      <div className="studio-workspace"><div><strong>林屿的工作区</strong><small>本地私有空间</small></div></div>
      <nav className="studio-nav studio-nav-primary" aria-label="工作台导航"><span className="studio-nav-heading">工作台</span>{renderNav(primaryKeys)}</nav>
      <nav className="studio-nav studio-nav-utility" aria-label="研究与设置导航"><span className="studio-nav-heading">研究与设置</span>{renderNav(utilityKeys)}</nav>
      <div className="studio-sidebar-bottom">
        <div className="sidebar-workflow" aria-label="创作流程"><span>发现线索</span><StudioIcon name="arrow" size={12} /><span>形成作品</span></div>
        <button className="studio-connection" onClick={() => check()} title="重新检查知序本地服务"><span className={online ? 'connection-dot online' : 'connection-dot'} />{online === null ? '正在连接知序本地服务' : online ? '知序本地服务已连接' : '重新连接知序本地服务'}</button>
      </div>
    </aside>
    <div className="studio-body">
      <header className="studio-topbar">
        <div className="studio-breadcrumb"><span>我的知序空间</span><StudioIcon name="chevron" size={13} /><strong>{current[1]}</strong></div>
        <div className="studio-utilities"><label className="studio-search-shell" aria-label="搜索工作区"><StudioIcon name="search" size={15} /><input placeholder="搜索内容或来源" /></label><span className="studio-local"><i className={online ? 'online' : ''} />{online === null ? '正在连接知序本地服务' : online ? '知序本地服务已连接' : '知序本地服务未连接'}</span><div className="theme-control"><span>外观</span><ThemeDropdown value={theme} onChange={setTheme} /></div></div>
      </header>
      <main id="main" tabIndex={-1} className="studio-main" key={route.view + route.id}>
        {online === false && <div className="message error" role="alert">知序本地服务暂时无法连接，内容保存和读取可能受影响。<button className="link" onClick={() => check()}>重新检查</button></div>}
        {route.view === 'hotspots' && <HotspotsPage navigate={navigate} />}
        {route.view === 'breakdown' && <BreakdownPage navigate={navigate} />}
        {route.view === 'create' && <QuickCreatePage navigate={navigate} />}
        {route.view === 'library' && <StudioLibraryPage navigate={navigate} />}
        {route.view === 'profile' && <StudioProfilePage navigate={navigate} />}
        {route.view === 'analytics' && <div className="analytics-page"><AnalyticsPage /></div>}
        {route.view === 'settings' && <ModelSettingsPage />}
        {route.view === 'accounts' && <AccountsPage />}
        {route.view === 'overview' && <OverviewPage navigate={navigate} />}
        {route.view === 'publish' && <PublishCenterPage initialTaskId={route.id || undefined} navigate={navigate} />}
        {route.view === 'drafts' && <DraftCenterPage initialDraftId={route.id || undefined} onDirty={() => {}} />}
        {route.view === 'outputs' && <OutputsPage />}
        {route.view === 'chat' && <ChatPage navigate={navigate} />}
        {route.view === 'skills' && <SkillsPage />}
        {route.view === 'workspace' && <ContentWorkspace taskId={route.id} navigate={navigate} onDirty={() => {}} />}
      </main>
    </div>
  </div>;
}
