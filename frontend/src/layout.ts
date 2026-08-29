export type Point = { x: number; y: number };
export type LayoutNode = { id: string };
export type LayoutEdge = { from: string; to: string; kind: string };

export function dagLayout(nodes: LayoutNode[], edges: LayoutEdge[]): Map<string, Point> {
  const depth = new Map(nodes.map(n => [n.id, 0]));
  for (let pass = 0; pass < nodes.length; pass += 1) for (const edge of edges) if (["parent", "depends"].includes(edge.kind)) depth.set(edge.to, Math.max(depth.get(edge.to) || 0, (depth.get(edge.from) || 0) + 1));
  const layers = new Map<number, string[]>(); for (const node of nodes) { const d = depth.get(node.id) || 0; layers.set(d, [...(layers.get(d) || []), node.id]); }
  return new Map([...layers].flatMap(([d, ids]) => ids.sort().map((id, i) => [id, { x: 150 + d * 250, y: 110 + i * 125 }] as [string, Point])));
}

export function knowledgeLayout(nodes: LayoutNode[], edges: LayoutEdge[]): Map<string, Point> {
  const p = new Map(nodes.map((n, i) => [n.id, { x: 140 + (i % 6) * 160, y: 120 + Math.floor(i / 6) * 140 }]));
  for (let step = 0; step < 48; step += 1) for (const edge of edges.filter(e => e.kind === "wiki")) { const a = p.get(edge.from), b = p.get(edge.to); if (!a || !b) continue; const dx = b.x - a.x, dy = b.y - a.y, l = Math.max(1, Math.hypot(dx, dy)), shift = (l - 180) * .02; a.x += dx / l * shift; a.y += dy / l * shift; b.x -= dx / l * shift; b.y -= dy / l * shift; }
  return p;
}
