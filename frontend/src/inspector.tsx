import type { ReactNode } from "react";
import "./inspector.css";

export type InspectorNode = { id: string; title: string; type: "task" | "knowledge"; status?: string; claim_kind?: string; progress?: number | null; created_at?: string; updated_at?: string; path?: string; summary?: string; markdown?: string; metadata?: Record<string, unknown> };
export type InspectorEdge = { from: string; to: string; kind: string };

function NodeTime({ value }: { value?: string }): ReactNode {
  if (!value) return <>—</>;
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return <>{value}</>;
  return <time dateTime={value} title={value}>{new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(parsed)}</time>;
}

function RelationList({ title, ids, nodes, onSelectNode }: { title: string; ids: string[]; nodes: InspectorNode[]; onSelectNode: (id: string) => void }) {
  const unique = [...new Set(ids)];
  if (!unique.length) return null;
  return <section className="relation-section"><div className="section-heading"><h3>{title}</h3><span>{unique.length}</span></div><div className="relation-list">{unique.map((id) => { const item = nodes.find((node) => node.id === id); return <button key={id} onClick={() => onSelectNode(id)}><span className={`relation-dot ${item?.type || "task"}`} /><span><small>{id}</small>{item?.title || id}</span><b>↗</b></button>; })}</div></section>;
}

export function Inspector({ node, nodes, edges, onFocus, onSelectNode, canGoBack, canGoForward, onBack, onForward }: { node?: InspectorNode; nodes: InspectorNode[]; edges: InspectorEdge[]; onFocus: () => void; onSelectNode: (id: string) => void; canGoBack: boolean; canGoForward: boolean; onBack: () => void; onForward: () => void }): ReactNode {
  if (!node) return <div className="inspector-empty"><span aria-hidden="true">✦</span><h2>Node details</h2><p>Select a node to inspect its relationships. Press Esc to clear or / to search.</p></div>;
  const incoming = (kind: string) => edges.filter((edge) => edge.kind === kind && edge.to === node.id).map((edge) => edge.from);
  const outgoing = (kind: string) => edges.filter((edge) => edge.kind === kind && edge.from === node.id).map((edge) => edge.to);
  const wiki = edges.filter((edge) => edge.kind === "wiki" && (edge.from === node.id || edge.to === node.id)).map((edge) => edge.from === node.id ? edge.to : edge.from);
  const metadata = node.metadata || {};
  const hiddenKeys = new Set(["parent", "depends_on", "affects", "when", "triggers"]);
  const extraMetadata = Object.entries(metadata).filter(([key]) => !hiddenKeys.has(key));
  const progress = Math.max(0, Math.min(100, node.progress ?? 0));
  const summary = node.summary?.replace(/^#.*$/m, "").trim();

  return <>
    <div className="inspector-title"><div className="inspector-titlebar"><span className={`type-chip ${node.type}`}>{node.type === "task" ? "Task" : node.claim_kind || "Knowledge"}</span><div className="node-history" aria-label="Node navigation"><button aria-label="Previous node" title="Previous node" disabled={!canGoBack} onClick={onBack}>←</button><button aria-label="Next node" title="Next node" disabled={!canGoForward} onClick={onForward}>→</button></div></div><h2>{node.title}</h2><p>{summary || "No summary available."}</p></div>
    <section className="overview-card"><div><span>Status</span><strong>{(node.status || node.claim_kind || "Unknown").replaceAll("_", " ")}</strong></div>{node.type === "task" && <div className="inspector-progress"><span>Progress</span><strong>{node.progress == null ? "—" : `${progress}%`}</strong><i><b style={{ width: `${progress}%` }} /></i></div>}<div><span>ID</span><strong>{node.id}</strong></div></section>
    {node.type === "task" ? <>
      <RelationList title="Upstream dependencies" ids={[...incoming("depends"), ...incoming("parent")]} nodes={nodes} onSelectNode={onSelectNode} />
      <RelationList title="Downstream tasks" ids={[...outgoing("depends"), ...outgoing("parent")]} nodes={nodes} onSelectNode={onSelectNode} />
      <RelationList title="Related knowledge" ids={incoming("affects")} nodes={nodes} onSelectNode={onSelectNode} />
    </> : <>
      <RelationList title="Affected tasks" ids={outgoing("affects")} nodes={nodes} onSelectNode={onSelectNode} />
      <RelationList title="Linked knowledge" ids={wiki} nodes={nodes} onSelectNode={onSelectNode} />
      {(metadata.when || metadata.triggers) && <section className="routing-card"><h3>Routing context</h3>{Boolean(metadata.when) && <p><span>When</span>{String(metadata.when)}</p>}{Boolean(metadata.triggers) && <p><span>Triggers</span>{Array.isArray(metadata.triggers) ? metadata.triggers.join(" · ") : String(metadata.triggers)}</p>}</section>}
    </>}
    <section className="metadata-section"><h3>Metadata</h3><dl><dt>Created</dt><dd><NodeTime value={node.created_at} /></dd><dt>Updated</dt><dd><NodeTime value={node.updated_at} /></dd><dt>Path</dt><dd>{node.path || "—"}</dd>{extraMetadata.map(([key, value]) => <><dt key={`${key}-term`}>{key.replaceAll("_", " ")}</dt><dd key={key}>{typeof value === "object" ? JSON.stringify(value) : String(value)}</dd></>)}</dl></section>
    <div className="inspector-actions"><button onClick={onFocus}>Focus neighborhood</button><button onClick={() => navigator.clipboard?.writeText(node.id)}>Copy ID</button></div>
    <section className="markdown-section"><h3>Markdown content</h3><pre className="markdown">{node.markdown || "(No content)"}</pre></section>
  </>;
}
