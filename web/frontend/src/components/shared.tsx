import { useEffect } from 'react';
import type { ReactNode } from 'react';

export const statusNames: Record<string, string> = {
  idea: '待研究', researching: '研究中', briefed: '写作计划阶段', drafting: '起草中', adapted: '待审阅', reviewing: '审阅中', archived: '已归档',
  proposed: '待确认', confirmed: '已确认', rejected: '已拒绝', revoked: '已撤销', draft: '待确认', generated: '模板草稿', edited: '已编辑',
  writing: '编辑中', ready: '待提交', submitted: '已提交',
  not_configured: '未配置', configured: '已配置', connecting: '连接中', connected: '已连接', read_succeeded: '读取完成', submit_succeeded: '已提交', publish_succeeded: '已发布', failed: '失败', unsupported: '不支持', expired: '已过期',
};
export const stateName = (value: string) => statusNames[value] ?? value;
const connectorStatusNames: Record<string, string> = {
  not_configured: '还没配置', configured: '配置已保存', connecting: '正在检查登录状态',
  connected: '已登录，等待读取账号', read_succeeded: '账号数据已读取', submit_succeeded: '本地演示已提交',
  publish_succeeded: '已发布（等待真实回执）', failed: '处理失败', unsupported: '暂不支持', expired: '登录已过期',
};
export const connectorStateName = (value: string) => connectorStatusNames[value] ?? stateName(value);
export const dateLabel = (value: string) => new Date(/(?:Z|[+-]\d\d:\d\d)$/.test(value) ? value : `${value}Z`).toLocaleString('zh-CN');
export const errorText = (error: unknown) => error instanceof Error ? error.message : '操作失败，请重试';
export const lines = (value: string) => value.split('\n').map(s => s.trim()).filter(Boolean);
export const stringList = (value: unknown): string[] => Array.isArray(value) ? value.filter((item): item is string => typeof item === 'string') : [];
export function PageHeader({ title, description, children }: { title: string; description: string; children?: ReactNode }) {
  return <header className="page-header"><div><h1>{title}</h1><p>{description}</p></div>{children}</header>;
}
export function Message({ children, error = false }: { children: ReactNode; error?: boolean }) {
  return <div className={`message ${error ? 'error' : ''}`} role={error ? 'alert' : 'status'}>{children}</div>;
}
export function Empty({ title, children }: { title: string; children: ReactNode }) {
  return <div className="empty"><h2>{title}</h2>{children}</div>;
}
export function useDirty(dirty: boolean, onDirty: (value: boolean) => void) {
  useEffect(() => { onDirty(dirty); return () => onDirty(false); }, [dirty, onDirty]);
  useEffect(() => {
    if (!dirty) return;
    const warn = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = ''; };
    window.addEventListener('beforeunload', warn);
    return () => window.removeEventListener('beforeunload', warn);
  }, [dirty]);
}
