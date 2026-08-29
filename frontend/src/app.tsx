import { useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import "./styles.css";
import { Graph } from "./graph";
import { Inspector } from "./inspector";

export type Mode = "all" | "tasks" | "knowledge";
export type Kind = "parent" | "depends" | "wiki" | "affects";
export type GraphNode = { id: string; type: "task" | "knowledge"; title: string; status?: string; claim_kind?: string; progress?: number; path?: string; summary?: string; markdown?: string; metadata?: Record<string, unknown> };
export type GraphEdge = { from: string; to: string; kind: Kind };
type Data = { schemaVersion?: number; initialMode?: Mode; tasks?: Record<string, Omit<GraphNode, "id" | "type">>; knowledge?: Record<string, Omit<GraphNode, "id" | "type">>; edges?: GraphEdge[]; diagnostics?: { redlinks: string[] } };

const data = JSON.parse(document.querySelector("#hypha-data")?.textContent || "{}") as Data;
const nodes: GraphNode[] = [
  ...Object.entries(data.tasks || {}).map(([id, value]) => ({ id, type: "task" as const, ...value })),
  ...Object.entries(data.knowledge || {}).map(([id, value]) => ({ id, type: "knowledge" as const, ...value })),
];
const edges = data.edges || [];

function App() {
  const [mode, setMode] = useState<Mode>(data.initialMode || "all");
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState<GraphNode>();
  const [selectionHistory, setSelectionHistory] = useState<{ ids: string[]; index: number }>({ ids: [], index: -1 });
  const [focused, setFocused] = useState<Set<string>>();
  const [statusFilter, setStatusFilter] = useState("all");
  const [progressFilter, setProgressFilter] = useState("all");
  const [typeFilter, setTypeFilter] = useState("all");
  const matches = useMemo(() => nodes.filter((node) => `${node.id} ${node.title} ${node.status || node.claim_kind || ""}`.toLowerCase().includes(query.toLowerCase())), [query]);
  const filteredNodes = useMemo(() => nodes.filter((node) => {
    if (typeFilter !== "all" && node.type !== typeFilter) return false;
    if (statusFilter !== "all" && node.status !== statusFilter && node.claim_kind !== statusFilter) return false;
    const progress = node.progress ?? 0;
    if (progressFilter === "not-started" && progress !== 0) return false;
    if (progressFilter === "in-progress" && (progress <= 0 || progress >= 100)) return false;
    if (progressFilter === "complete" && progress !== 100) return false;
    return true;
  }), [progressFilter, statusFilter, typeFilter]);
  const statuses = useMemo(() => [...new Set(nodes.map((node) => node.status || node.claim_kind).filter(Boolean) as string[])].sort(), []);
  const neighbors = selected ? new Set([selected.id, ...edges.filter((edge) => edge.from === selected.id || edge.to === selected.id).flatMap((edge) => [edge.from, edge.to])]) : new Set<string>();
  const filtersActive = statusFilter !== "all" || progressFilter !== "all" || typeFilter !== "all" || Boolean(focused);
  const selectNode = (node?: GraphNode) => {
    setSelected(node);
    if (focused) setFocused(undefined);
    if (!node) return;
    setSelectionHistory((current) => {
      const visited = current.ids.slice(0, current.index + 1);
      if (visited.at(-1) === node.id) return current;
      const ids = [...visited, node.id];
      return { ids, index: ids.length - 1 };
    });
  };
  const navigateHistory = (offset: -1 | 1) => {
    const index = selectionHistory.index + offset;
    const node = nodes.find((item) => item.id === selectionHistory.ids[index]);
    if (!node) return;
    setSelectionHistory((current) => ({ ...current, index }));
    setSelected(node);
    setFocused(undefined);
  };
  const resetFilters = () => { setStatusFilter("all"); setProgressFilter("all"); setTypeFilter("all"); setFocused(undefined); };

  useEffect(() => {
    const listener = (event: KeyboardEvent) => {
      if (event.key === "Escape") { setSelected(undefined); setFocused(undefined); }
      if (event.key === "/") { event.preventDefault(); document.querySelector<HTMLInputElement>("#search")?.focus(); }
    };
    addEventListener("keydown", listener);
    return () => removeEventListener("keydown", listener);
  }, []);

  return <main>
    <header className="topbar">
      <div className="brand"><span className="brand-mark" aria-hidden="true">⌘</span><div><h1>Hypha Task Map</h1><p>Local Knowledge Network</p></div></div>
      <div className="search-wrap"><span aria-hidden="true">⌕</span><input id="search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search tasks, knowledge, notes…" /><kbd>⌘ K</kbd>{query && <div className="results">{matches.slice(0, 6).map((node) => <button key={node.id} onClick={() => { selectNode(node); setQuery(""); }}>{node.id} · {node.title}</button>)}</div>}</div>
      <div className="filters" aria-label="Filters"><label><span className="sr-only">Status</span><select aria-label="Status" value={statusFilter} onChange={(event) => { setStatusFilter(event.target.value); setFocused(undefined); }}><option value="all">Status · All</option>{statuses.map((status) => <option key={status} value={status}>{status.replaceAll("_", " ")}</option>)}</select></label><label><span className="sr-only">Progress</span><select aria-label="Progress" value={progressFilter} onChange={(event) => { setProgressFilter(event.target.value); setFocused(undefined); }}><option value="all">Progress · All</option><option value="not-started">Not started</option><option value="in-progress">1–99%</option><option value="complete">Complete</option></select></label><label><span className="sr-only">Type</span><select aria-label="Type" value={typeFilter} onChange={(event) => { setTypeFilter(event.target.value); setFocused(undefined); }}><option value="all">Type · All</option><option value="task">Tasks</option><option value="knowledge">Knowledge</option></select></label><button className="reset-filters" disabled={!filtersActive} onClick={resetFilters} aria-label="Reset filters" title="Reset filters and focus">↺ Reset</button></div>
      <nav aria-label="Graph views">{(["all", "tasks", "knowledge"] as Mode[]).map((item) => <button key={item} aria-pressed={mode === item} className={mode === item ? "active" : ""} onClick={() => { setMode(item); setFocused(undefined); }}>{item === "all" ? "⌘ Mycelium" : item === "tasks" ? "Tasks" : "Knowledge"}</button>)}<button aria-pressed={Boolean(focused)} className={focused ? "active" : ""} disabled={!selected} title={selected ? "Show the selected node and its direct relations" : "Select a node to focus"} onClick={() => setFocused((value) => value ? undefined : neighbors)}>◎ Focus</button></nav>
    </header>
    <section className="board"><div className="canvas"><Graph nodes={filteredNodes} edges={edges} mode={mode} selected={selected?.id} focused={focused} onSelect={selectNode} /><div className="legend" aria-label="Legend"><strong>Legend</strong><span><i className="task-key" />Task</span><span><i className="knowledge-key" />Knowledge</span><span><i className="depends-key" />Dependency</span><span><i className="affects-key" />Affects</span><span className="redlinks">Redlinks {data.diagnostics?.redlinks.length || 0}</span></div></div><aside aria-live="polite"><Inspector node={selected} nodes={nodes} edges={edges} onFocus={() => setFocused(neighbors)} onSelectNode={(id) => selectNode(nodes.find((node) => node.id === id))} canGoBack={selectionHistory.index > 0} canGoForward={selectionHistory.index >= 0 && selectionHistory.index < selectionHistory.ids.length - 1} onBack={() => navigateHistory(-1)} onForward={() => navigateHistory(1)} /><p className="read-only">Read-only view · update state through Hypha CLI</p></aside></section>
    <div className="sr-only" aria-live="polite">{selected ? `Selected ${selected.title}` : "No node selected"}</div><ul className="sr-only" aria-label="Node list">{nodes.map((node) => <li key={node.id}><button onClick={() => selectNode(node)}>{node.id} {node.title}</button></li>)}</ul>
  </main>;
}

createRoot(document.querySelector("#root")!).render(<App />);
