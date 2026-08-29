import type { ReactNode } from "react";

export type InspectorNode = { id: string; title: string; type: "task" | "knowledge"; status?: string; claim_kind?: string; progress?: number; path?: string; summary?: string; metadata?: Record<string, unknown> };
export type InspectorEdge = { from: string; to: string; kind: string };
export function Inspector({ node, edges, onFocus }: { node?: InspectorNode; edges: InspectorEdge[]; onFocus: () => void }): ReactNode {
  if (!node) return <><h2>节点详情</h2><p>点击节点查看关系；Esc 清除选择，/ 搜索。</p></>;
  const links = edges.filter(edge => edge.from === node.id || edge.to === node.id).map(edge => `${edge.kind}: ${edge.from === node.id ? edge.to : edge.from}`);
  const metadata = Object.entries(node.metadata || {}).map(([key, value]) => `${key}: ${Array.isArray(value) ? value.join(", ") : String(value)}`);
  return <><h2>{node.title}</h2><dl><dt>ID</dt><dd>{node.id}</dd><dt>类型</dt><dd>{node.type === "task" ? "任务" : "知识"}</dd><dt>状态</dt><dd>{node.status || node.claim_kind || "—"}</dd><dt>进度</dt><dd>{node.progress ?? "—"}</dd><dt>路径</dt><dd>{node.path || "—"}</dd><dt>摘要</dt><dd>{node.summary || "—"}</dd><dt>入/出边</dt><dd>{links.join(" · ") || "无直接关系"}</dd><dt>元数据</dt><dd>{metadata.join(" · ") || "—"}</dd></dl><button onClick={onFocus}>聚焦邻域</button><button onClick={() => navigator.clipboard?.writeText(node.id)}>复制 ID</button></>;
}
