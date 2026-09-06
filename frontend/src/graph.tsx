import { useEffect, useMemo } from "react";
import {
  Background,
  BaseEdge,
  Controls,
  EdgeLabelRenderer,
  Handle,
  MarkerType,
  Position,
  ReactFlow,
  getBezierPath,
  useEdgesState,
  useNodesState,
  type EdgeProps,
  type NodeProps,
  type Edge as FlowEdge,
  type Node as FlowNode,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { colonyLayout, dagLayout, knowledgeLayout } from "./layout";
import type { GraphEdge, GraphNode, Kind, Mode } from "./app";

type HyphaNodeData = { item: GraphNode; related: boolean };
type HyphaFlowNode = FlowNode<HyphaNodeData, "task" | "knowledge">;
type HyphaEdgeData = { kind: Kind; related: boolean; dimmed: boolean };
type HyphaFlowEdge = FlowEdge<HyphaEdgeData, "mycelium">;

const statusLabel: Record<string, string> = { todo: "To do", in_progress: "In progress", done: "Done", blocked: "Blocked", active: "Active" };

function NodeHandles() {
  return <>{([Position.Left, Position.Right, Position.Top, Position.Bottom] as Position[]).flatMap((position) => { const side = position.toLowerCase(); return [<Handle key={`${side}-target`} id={`${side}-target`} type="target" position={position} />, <Handle key={`${side}-source`} id={`${side}-source`} type="source" position={position} />]; })}</>;
}

function TaskNode({ data, selected }: NodeProps<HyphaFlowNode>) {
  const node = data.item;
  const progress = Math.max(0, Math.min(100, node.progress ?? 0));
  return <article className={`graph-node task-node status-${node.status || "todo"} ${selected ? "selected" : ""} ${!data.related ? "unrelated" : ""}`}>
    <NodeHandles />
    <div className="node-id">T · {node.id}</div>
    <h3>{node.title}</h3>
    <div className="node-status"><span />{statusLabel[node.status || "todo"] || node.status}</div>
    <div className="node-footer"><span>{node.progress == null ? "Unknown progress" : `${progress}%`}</span><span className="node-progress"><i style={{ width: `${progress}%` }} /></span></div>
  </article>;
}

function KnowledgeNode({ data, selected }: NodeProps<HyphaFlowNode>) {
  const node = data.item;
  return <article className={`graph-node knowledge-node ${selected ? "selected" : ""} ${!data.related ? "unrelated" : ""}`}>
    <NodeHandles />
    <span className="knowledge-orbit" aria-hidden="true">✦</span>
    <div><div className="node-id">K · {node.id.replace(/^know\//, "")}</div><h3>{node.title}</h3><p>{node.claim_kind || "Knowledge"}</p></div>
  </article>;
}

function MyceliumEdge(props: EdgeProps<HyphaFlowEdge>) {
  const [path, labelX, labelY] = getBezierPath(props);
  const kind = props.data?.kind || "parent";
  const label = kind === "depends" ? "depends on" : kind === "affects" ? "informs" : kind === "wiki" ? "links" : "contains";
  const related = Boolean(props.data?.related);
  const showLabel = kind !== "parent" || related;
  return <><BaseEdge path={path} markerEnd={props.markerEnd} className={`edge-glow edge-glow-${kind} ${props.data?.dimmed ? "dimmed" : ""}`} /><BaseEdge path={path} markerEnd={props.markerEnd} className={`mycelium-edge edge-${kind} ${related ? "edge-related" : ""} ${props.data?.dimmed ? "dimmed" : ""}`} />{related && <BaseEdge path={path} className={`edge-flow edge-flow-${kind}`} />}{showLabel && <EdgeLabelRenderer><span className={`edge-label edge-label-${kind} ${related ? "related" : ""} ${props.data?.dimmed ? "dimmed" : ""}`} style={{ transform: `translate(-50%, -50%) translate(${labelX}px,${labelY}px)` }}>{label}</span></EdgeLabelRenderer>}</>;
}

const nodeTypes = { task: TaskNode, knowledge: KnowledgeNode };
const edgeTypes = { mycelium: MyceliumEdge };
const visibleKind = (mode: Mode, kind: Kind) => mode === "all" || (mode === "tasks" && ["parent", "depends"].includes(kind)) || (mode === "knowledge" && kind === "wiki");

function graphLayout(items: GraphNode[], edges: GraphEdge[], mode: Mode, selected?: string) {
  if (mode === "tasks") return dagLayout(items, edges);
  if (mode === "knowledge") return knowledgeLayout(items, edges);
  return colonyLayout(items, edges, selected);
}

function toFlowNodes(items: GraphNode[], edges: GraphEdge[], mode: Mode, selected?: string, focused?: Set<string>): HyphaFlowNode[] {
  const shown = items.filter((node) => (mode === "all" || node.type === (mode === "tasks" ? "task" : "knowledge")) && (!focused || focused.has(node.id)));
  const positions = graphLayout(shown, edges, mode, selected);
  const related = selected ? new Set([selected, ...edges.filter((edge) => edge.from === selected || edge.to === selected).flatMap((edge) => [edge.from, edge.to])]) : new Set(shown.map((node) => node.id));
  return shown.map((item) => {
    const point = positions.get(item.id) || { x: 0, y: 0 };
    return { id: item.id, type: item.type, position: { x: point.x, y: point.y }, data: { item, related: related.has(item.id) }, selectable: true, draggable: true };
  });
}

function toFlowEdges(items: GraphNode[], edges: GraphEdge[], mode: Mode, selected?: string, focused?: Set<string>): HyphaFlowEdge[] {
  const shown = items.filter((node) => (mode === "all" || node.type === (mode === "tasks" ? "task" : "knowledge")) && (!focused || focused.has(node.id)));
  const ids = new Set(shown.map((node) => node.id));
  const positions = graphLayout(shown, edges, mode, selected);
  const seenWiki = new Set<string>();
  return edges.filter((edge) => {
    if (!visibleKind(mode, edge.kind) || !ids.has(edge.from) || !ids.has(edge.to)) return false;
    if (edge.kind !== "wiki") return true;
    const key = [edge.from, edge.to].sort().join("↔");
    if (seenWiki.has(key)) return false;
    seenWiki.add(key);
    return true;
  }).map((edge, index) => {
    let source = edge.from; let target = edge.to;
    if (edge.kind === "wiki" && (positions.get(source)?.x ?? 0) > (positions.get(target)?.x ?? 0)) [source, target] = [target, source];
    const from = positions.get(source), to = positions.get(target); const dx = (to?.x || 0) - (from?.x || 0), dy = (to?.y || 0) - (from?.y || 0); const horizontal = Math.abs(dx) >= Math.abs(dy); const sourceSide = horizontal ? (dx >= 0 ? "right" : "left") : (dy >= 0 ? "bottom" : "top"); const targetSide = horizontal ? (dx >= 0 ? "left" : "right") : (dy >= 0 ? "top" : "bottom"); const related = Boolean(selected && (edge.from === selected || edge.to === selected));
    return { id: `${edge.kind}-${source}-${target}-${index}`, source, target, sourceHandle: `${sourceSide}-source`, targetHandle: `${targetSide}-target`, type: "mycelium", data: { kind: edge.kind, related, dimmed: Boolean(selected && !related) }, markerEnd: ["depends", "affects"].includes(edge.kind) ? { type: MarkerType.ArrowClosed, width: 14, height: 14 } : undefined };
  });
}

export function Graph({ nodes: sourceNodes, edges: sourceEdges, mode, selected, focused, onSelect }: { nodes: GraphNode[]; edges: GraphEdge[]; mode: Mode; selected?: string; focused?: Set<string>; onSelect: (node?: GraphNode) => void }) {
  const focusKey = focused ? [...focused].sort().join("|") : "";
  const initialNodes = useMemo(() => toFlowNodes(sourceNodes, sourceEdges, mode, selected, focused), [sourceNodes, sourceEdges, mode, selected, focused]);
  const initialEdges = useMemo(() => toFlowEdges(sourceNodes, sourceEdges, mode, selected, focused), [sourceNodes, sourceEdges, mode, selected, focused]);
  const [flowNodes, setFlowNodes, onNodesChange] = useNodesState<HyphaFlowNode>(initialNodes);
  const [flowEdges, setFlowEdges, onEdgesChange] = useEdgesState<HyphaFlowEdge>(initialEdges);
  useEffect(() => setFlowNodes(initialNodes), [initialNodes, setFlowNodes]);
  useEffect(() => setFlowEdges(initialEdges), [initialEdges, setFlowEdges]);

  return <ReactFlow<HyphaFlowNode, HyphaFlowEdge>
    key={`${mode}:${focusKey}`}
    nodes={flowNodes.map((node) => ({ ...node, selected: node.id === selected }))}
    edges={flowEdges}
    nodeTypes={nodeTypes}
    edgeTypes={edgeTypes}
    onNodesChange={onNodesChange}
    onEdgesChange={onEdgesChange}
    onNodeClick={(_, node) => onSelect(node.data.item)}
    onPaneClick={() => onSelect(undefined)}
    minZoom={0.25}
    maxZoom={2}
    fitView
    fitViewOptions={{ padding: 0.2, maxZoom: 1 }}
    nodesConnectable={false}
    edgesReconnectable={false}
    proOptions={{ hideAttribution: true }}
    aria-label="Interactive Hypha relationship graph"
  >
    <Background color="#aaa792" gap={34} size={0.8} />
    <Controls showInteractive={false} position="bottom-right" />
  </ReactFlow>;
}
