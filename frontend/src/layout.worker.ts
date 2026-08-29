import { dagLayout, knowledgeLayout } from "./layout";
self.onmessage = ({ data }: MessageEvent<{ mode: "tasks" | "knowledge"; nodes: { id: string }[]; edges: { from: string; to: string; kind: string }[] }>) => postMessage([...((data.mode === "tasks" ? dagLayout : knowledgeLayout)(data.nodes, data.edges))]);
