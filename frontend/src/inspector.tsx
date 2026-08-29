import type { ReactNode } from "react";
import "./inspector.css";

export type InspectorNode = { id: string; title: string; type: "task" | "knowledge"; status?: string; claim_kind?: string; progress?: number; path?: string; summary?: string; markdown?: string; metadata?: Record<string, unknown> };
export type InspectorEdge = { from: string; to: string; kind: string };

function RelationList({ title, ids, nodes, onSelectNode }: { title: string; ids: string[]; nodes: InspectorNode[]; onSelectNode: (id: string) => void }) {
  const unique = [...new Set(ids)];
  if (!unique.length) return null;
  return <section className="relation-section"><div className="section-heading"><h3>{title}</h3><span>{unique.length}</span></div><div className="relation-list">{unique.map((id) => { const item = nodes.find((node) => node.id === id); return <button key={id} onClick={() => onSelectNode(id)}><span className={`relation-dot ${item?.type || "task"}`} /><span><small>{id}</small>{item?.title || id}</span><b>↗</b></button>; })}</div></section>;
}

export function Inspector({ node, nodes, edges, onFocus, onSelectNode }: { node?: InspectorNode; nodes: InspectorNode[]; edges: InspectorEdge[]; onFocus: () => void; onSelectNode: (id: string) => void }): ReactNode {
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
    <div className="inspector-title"><span className={`type-chip ${node.type}`}>{node.type === "task" ? "Task" : node.claim_kind || "Knowledge"}</span><h2>{node.title}</h2><p>{summary || "No summary available."}</p></div>
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
    <section className="metadata-section"><h3>Metadata</h3><dl><dt>Path</dt><dd>{node.path || "—"}</dd>{extraMetadata.map(([key, value]) => <><dt key={`${key}-term`}>{key.replaceAll("_", " ")}</dt><dd key={key}>{Array.isArray(value) ? value.join(", ") : String(value)}</dd></>)}</dl></section>
    <div className="inspector-actions"><button onClick={onFocus}>Focus neighborhood</button><button onClick={() => navigator.clipboard?.writeText(node.id)}>Copy ID</button></div>
    <section className="markdown-section"><h3>Markdown content</h3><pre className="markdown">{node.markdown || "(No content)"}</pre></section>
  </>;
}
