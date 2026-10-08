import { useEffect, useRef, useState } from 'react';
import { PageHeader } from './components/shared';
import { apiUrl } from './api';

type Navigate = (path: string) => void;
type Message = { role: 'user' | 'assistant'; content: string; blocked?: boolean };

function sessionId(): string {
  const key = 'creatoros:chat-session';
  const old = window.localStorage.getItem(key);
  if (old) return old;
  const next = `creatoros-${Date.now()}-${Math.random().toString(36).slice(2)}`;
  window.localStorage.setItem(key, next);
  return next;
}

export function ChatPage({ navigate }: { navigate: Navigate }) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState('');
  const abort = useRef<AbortController | null>(null);

  useEffect(() => () => abort.current?.abort(), []);

  const send = async () => {
    const text = input.trim();
    if (!text || busy) return;
    setInput(''); setNotice(''); setBusy(true);
    setMessages(prev => [...prev, { role: 'user', content: text }, { role: 'assistant', content: '' }]);
    const controller = new AbortController(); abort.current = controller;
    try {
      const response = await fetch(apiUrl('/api/chat/stream'), { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ message: text, sessionId: sessionId(), turnId: `${Date.now()}` }), signal: controller.signal });
      if (!response.ok) {
        const body = await response.json().catch(() => ({}));
        throw new Error(String(body.detail || `请求失败（${response.status}）`));
      }
      const reader = response.body?.getReader();
      if (!reader) throw new Error('服务没有返回流');
      const decoder = new TextDecoder(); let buffer = ''; let done = false;
      while (!done) {
        const chunk = await reader.read(); done = chunk.done;
        buffer += decoder.decode(chunk.value || new Uint8Array(), { stream: !done });
        const lines = buffer.split(/\r?\n/); buffer = lines.pop() || '';
        let event = ''; let data = '';
        for (const line of lines) {
          if (!line) {
            if (event === 'token' || event === 'message') {
              let value = data; try { value = JSON.parse(data) as string; } catch { /* raw SSE */ }
              setMessages(prev => { const next = [...prev]; const last = next.length - 1; next[last] = { ...next[last], content: next[last].content + value }; return next; });
            }
            if (event === 'error') throw new Error(data);
            event = ''; data = ''; continue;
          }
          if (line.startsWith('event:')) event = line.slice(6).trim();
          if (line.startsWith('data:')) data += line.slice(5).trim();
        }
      }
    } catch (error) {
      if ((error as Error).name !== 'AbortError') {
        const message = (error as Error).message || '对话暂不可用';
        setMessages(prev => { const next = [...prev]; const last = next.length - 1; next[last] = { role: 'assistant', blocked: true, content: `暂时无法继续：${message}\n\n请先到“模型设置”完成配置并测试。` }; return next; });
        setNotice('本轮没有生成内容，状态已保留为阻断。');
      }
    } finally { abort.current = null; setBusy(false); }
  };

  return <>
    <PageHeader title="对话" description="用知序工作台发起研究、改写和任务协作。消息、阻断状态和恢复动作都保留在当前会话。">
      <button className="secondary" onClick={() => navigate('workspace')}>转到一键工作流</button>
    </PageHeader>
    {notice && <div className="message error" role="status">{notice}</div>}
    <section className="panel creator-chat">
      <div className="creator-chat-head"><div><span className="kicker">CREATOROS CHAT</span><h2>先问一个具体问题</h2></div><span className="state">本地会话</span></div>
      <div className="creator-chat-log" aria-live="polite">{messages.length === 0 ? <div className="empty"><h2>还没有消息</h2><p>可以从来源核验、选题角度、平台改写或质量检查开始。</p></div> : messages.map((message, index) => <article className={`creator-chat-message ${message.role} ${message.blocked ? 'blocked' : ''}`} key={index}><span>{message.role === 'user' ? '你' : '知序'}</span><p>{message.content || (busy && index === messages.length - 1 ? '正在连接模型服务…' : '')}</p></article>)}</div>
      <div className="creator-chat-compose"><textarea rows={3} value={input} onChange={e => setInput(e.target.value)} onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); void send(); } }} placeholder="输入研究问题、改写要求或平台限制…" disabled={busy} /><div className="action-row"><small className="hint">Enter 发送 · Shift+Enter 换行 · 不会伪造模型结果</small>{busy ? <button className="secondary" onClick={() => abort.current?.abort()}>停止</button> : <button className="primary" disabled={!input.trim()} onClick={() => void send()}>发送</button>}</div></div>
    </section>
  </>;
}
