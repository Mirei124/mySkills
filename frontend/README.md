# Hypha frontend

This directory contains the source for Hypha's offline task and knowledge graph. The development application uses React, TypeScript, Vite, and React Flow. The shipped skill contains only a generated, self-contained HTML file, so the Python CLI has no Node.js runtime dependency.

## Development

```bash
pnpm install
pnpm typecheck
pnpm lint
pnpm test
pnpm build:template
pnpm test:e2e
```

`pnpm build:template` builds `dist/index.html`, validates the `{{HYPHA_DATA}}` placeholder, and copies the result to `skills/hypha-governance/templates/view.html`.

Generated directories (`node_modules`, `dist`, `test-results`, and `playwright-report`) are disposable and ignored by Git. Do not edit generated HTML directly.

## Maintenance documentation

- [Architecture](docs/ARCHITECTURE.md) explains data flow, source ownership, and safe change boundaries.
- [Visual system](docs/VISUAL_STYLE.md) records the design language, interaction rules, review checklist, and reference image.

Read both documents before making substantial frontend changes. The visual reference is directional rather than a pixel-perfect specification; preserve its hierarchy and atmosphere while keeping the graph driven by real Hypha data.
