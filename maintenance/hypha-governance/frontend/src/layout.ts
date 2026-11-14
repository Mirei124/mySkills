export type Point = { x: number; y: number };
export type LayoutNode = { id: string; type?: "task" | "knowledge" };
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

export function colonyLayout(nodes: LayoutNode[], edges: LayoutEdge[], selected?: string): Map<string, Point> {
  const tasks = nodes.filter((node) => node.type !== "knowledge");
  const knowledge = nodes.filter((node) => node.type === "knowledge");
  const positions = dagLayout(tasks, edges);
  const taskPoints = [...positions.values()];
  const centerY = taskPoints.length ? (Math.min(...taskPoints.map((point) => point.y)) + Math.max(...taskPoints.map((point) => point.y))) / 2 : 300;
  for (const point of taskPoints) point.y += 310 - centerY;

  knowledge.forEach((node, index) => {
    const targets = edges.filter((edge) => edge.kind === "affects" && edge.from === node.id).map((edge) => positions.get(edge.to)).filter(Boolean) as Point[];
    const anchor = targets.length ? { x: targets.reduce((sum, point) => sum + point.x, 0) / targets.length, y: targets.reduce((sum, point) => sum + point.y, 0) / targets.length } : { x: 180 + (index % 5) * 230, y: 310 };
    const above = index % 2 === 0;
    positions.set(node.id, { x: anchor.x + ((index % 3) - 1) * 95, y: anchor.y + (above ? -205 : 205) });
  });

  // A short deterministic collision pass keeps the colony organic without a perpetual force simulation.
  for (let pass = 0; pass < 36; pass += 1) for (let i = 0; i < nodes.length; i += 1) for (let j = i + 1; j < nodes.length; j += 1) {
    const a = positions.get(nodes[i].id), b = positions.get(nodes[j].id); if (!a || !b) continue;
    const minX = nodes[i].type === "knowledge" && nodes[j].type === "knowledge" ? 205 : 245;
    const minY = nodes[i].type === "knowledge" && nodes[j].type === "knowledge" ? 105 : 145;
    const dx = b.x - a.x, dy = b.y - a.y;
    if (Math.abs(dx) >= minX || Math.abs(dy) >= minY) continue;
    const pushX = (minX - Math.abs(dx)) * .07 * (dx < 0 ? -1 : 1);
    const pushY = (minY - Math.abs(dy)) * .07 * (dy < 0 ? -1 : 1);
    a.x -= pushX; b.x += pushX; a.y -= pushY; b.y += pushY;
  }

  if (selected && positions.has(selected)) {
    const origin = positions.get(selected)!;
    const offset = { x: 520 - origin.x, y: 340 - origin.y };
    for (const point of positions.values()) { point.x += offset.x; point.y += offset.y; }
    const direct = edges.filter((edge) => edge.from === selected || edge.to === selected);
    const groups = { incoming: [] as string[], outgoing: [] as string[], knowledge: [] as string[] };
    direct.forEach((edge) => {
      const other = edge.from === selected ? edge.to : edge.from;
      const item = nodes.find((node) => node.id === other);
      if (item?.type === "knowledge" || edge.kind === "wiki" || edge.kind === "affects") groups.knowledge.push(other);
      else if (edge.to === selected) groups.incoming.push(other);
      else groups.outgoing.push(other);
    });
    [...new Set(groups.incoming)].forEach((id, index, all) => positions.set(id, { x: 215, y: 340 + (index - (all.length - 1) / 2) * 165 }));
    [...new Set(groups.outgoing)].forEach((id, index, all) => positions.set(id, { x: 825, y: 340 + (index - (all.length - 1) / 2) * 165 }));
    [...new Set(groups.knowledge)].forEach((id, index, all) => positions.set(id, { x: 425 + index * 220 - (all.length - 1) * 110, y: index % 2 ? 555 : 110 }));
  }
  return positions;
}
