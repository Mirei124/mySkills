import { describe, expect, it } from "vitest";
import { dagLayout, knowledgeLayout } from "./layout";

describe("graph layouts", () => {
  it("places task dependencies in later DAG layers", () => {
    const points = dagLayout([{ id: "a" }, { id: "b" }], [{ from: "a", to: "b", kind: "depends" }]);
    expect(points.get("b")!.x).toBeGreaterThan(points.get("a")!.x);
  });
  it("creates stable finite knowledge positions", () => {
    const nodes = [{ id: "a" }, { id: "b" }]; const edges = [{ from: "a", to: "b", kind: "wiki" }];
    expect([...knowledgeLayout(nodes, edges)]).toEqual([...knowledgeLayout(nodes, edges)]);
  });
});
