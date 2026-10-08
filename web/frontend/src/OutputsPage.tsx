import { useEffect, useState } from 'react';
import { Empty, Message, PageHeader, errorText } from './components/shared';
import { listOfficialOutputs, officialOutputUrl, type OfficialOutputNode } from './api';

function Tree({ nodes, depth = 0 }: { nodes: OfficialOutputNode[]; depth?: number }) {
  return <div className="output-tree">{nodes.map(node => <div className="output-node" key={node.path} style={{ marginLeft: depth * 16 }}>
    <div className="output-node-row"><span className={`output-icon ${node.type}`}>{node.type === 'dir' ? '▾' : '·'}</span><strong>{node.name}</strong><small>{node.type === 'dir' ? `${node.fileCount ?? node.children?.length ?? 0} 项` : `${node.kind ?? '文件'}${node.size ? ` · ${node.size} B` : ''}`}</small>{node.type === 'file' && <a className="link" href={officialOutputUrl(node.path)} target="_blank" rel="noreferrer">打开</a>}</div>{node.children?.length ? <Tree nodes={node.children} depth={depth + 1} /> : null}</div>)} </div>;
}

export function OutputsPage() {
  const [nodes, setNodes] = useState<OfficialOutputNode[]>([]);
  const [error, setError] = useState('');
  const refresh = () => void listOfficialOutputs().then(setNodes).catch(e => setError(errorText(e)));
  useEffect(refresh, []);
  return <>
    <PageHeader title="产物树" description="工作流产物按知序的运行目录展示，便于追踪来源、查看草稿和继续编辑。目录只读，发布仍需在发布中心显式操作。"><button className="secondary" onClick={refresh}>刷新</button></PageHeader>
    {error && <Message error>{error} <button className="link" onClick={refresh}>重试</button></Message>}
    <section className="panel outputs-panel">{nodes.length ? <Tree nodes={nodes} /> : <Empty title="还没有运行产物"><p>启动一次一键工作流后，素材核验、写作计划、平台改写和检查结果会按作业归档到这里。</p></Empty>}</section>
  </>;
}
