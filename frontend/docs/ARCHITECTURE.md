# Frontend architecture

## Runtime model

Hypha exports graph data into the `{{HYPHA_DATA}}` placeholder in `index.html`. `src/app.tsx` parses that JSON, owns filters and selection state, and passes normalized nodes and edges to the graph and inspector.

```text
Hypha CLI data
  → index.html placeholder
  → app.tsx state and filtering
  → graph.tsx rendering + layout.ts positions
  → inspector.tsx semantic detail view
  → Vite single-file build
  → skills/hypha-governance/templates/view.html
```

## Source ownership

- `src/app.tsx`: data contract, top-level state, search, filters, view modes, and keyboard behavior.
- `src/graph.tsx`: React Flow nodes, handles, edges, focus emphasis, and graph interaction.
- `src/layout.ts`: deterministic task, knowledge, and mixed colony layouts. Keep it independent of React and the DOM.
- `src/inspector.tsx`: task/knowledge-specific relationship summaries and navigation.
- `src/styles.css`: application shell and graph visual system.
- `src/inspector.css`: inspector-only presentation.
- `src/layout.test.ts`: deterministic layout checks.
- `e2e/view.spec.ts`: offline export and user-interaction regression coverage.
- `build_template.py`: copies the single-file build into the distributable skill.

## Change boundaries

1. Preserve the `GraphNode`, `GraphEdge`, and `{{HYPHA_DATA}}` contracts unless the CLI exporter and Python tests change in the same patch.
2. Keep layout deterministic. Do not introduce random positions without a stable seed; screenshots and spatial memory depend on repeatability.
3. React Flow is the rendering layer. Do not reintroduce Canvas hit testing, camera state, or a layout web worker unless measured graph size demonstrates a need.
4. The generated template is an artifact. Change source files, run `pnpm build:template`, then verify the generated skill template.
5. The offline HTML must not fetch fonts, scripts, images, or styles at runtime.

## Required checks

Run these after frontend changes:

```bash
cd frontend
pnpm typecheck
pnpm lint
pnpm test
pnpm build:template
pnpm test:e2e
```

For layout or visual changes, also inspect the 1920 × 1080 E2E screenshot. Verify a mixed graph and a selected-node state, not only the empty or single-node view.
