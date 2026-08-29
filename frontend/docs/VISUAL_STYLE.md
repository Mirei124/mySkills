# Visual system and guardrails

## Reference

The primary visual reference is [Mycelium Task Map reference](reference/mycelium-task-map-reference.png). It establishes the intended mood and hierarchy; current product behavior and real Hypha data take precedence over literal copying.

## Design direction

The interface should feel like a calm field-research workspace: warm paper, moss, soil, translucent specimen panels, and living mycelial connections. It should not drift toward a generic dark dashboard, neon graph explorer, or flat white admin table.

Core qualities:

- Warm ivory and mineral backgrounds rather than pure white.
- Moss green as the primary action and task color.
- Muted violet for knowledge and terracotta for `affects` relationships.
- Serif display type for identity and entity titles; restrained sans-serif for controls and metadata.
- Frosted panels with visible scenery behind them, fine borders, inner highlights, and soft depth.
- Organic asymmetry in node placement and silhouettes, while labels remain readable.
- Slow, low-saturation motion that suggests growth or transport rather than urgency.

## Layout hierarchy

- Keep a compact rectangular top bar separated from the rounded main board by visible breathing room.
- The graph is the primary surface. The inspector is a stable right-hand column, not a modal overlay on desktop.
- In the mixed view, tasks form the structural backbone and knowledge sits near the tasks it informs.
- Selecting a node should clarify its neighborhood: emphasize direct relations, de-emphasize unrelated content, and keep the selected node visually central.
- Avoid collisions between nodes, labels, legend, controls, and inspector.

## Graph language

- Task nodes and knowledge nodes must remain distinguishable by shape, color, and content—not color alone.
- Preserve four-sided connection handles so edges leave nodes in a spatially natural direction.
- Use layered edges: a subtle glow beneath a semantic base stroke, plus a slow moving overlay only for related paths.
- `parent` edges are quiet; `depends`, `affects`, and `wiki` retain distinct semantic colors.
- Do not show every `contains` label in a dense overview. Contextual labels are preferable to repeated visual noise.
- The selected-node outline should make one slow circuit. Do not add a separate “Selected” badge.

## Motion and accessibility

- Motion must remain calm. Current relationship flow is approximately 1.4 seconds per dash cycle and the selected outline approximately 4.2 seconds per circuit.
- Keep `prefers-reduced-motion` behavior for every decorative animation.
- Maintain keyboard focus rings, Escape-to-clear behavior, readable contrast, and non-color status cues.
- Visible product copy is English.

## Before merging a visual change

- Compare the result with the reference image at desktop size.
- Check the mixed, tasks-only, and knowledge-only views.
- Check an unselected graph and at least one selected task and knowledge node.
- Exercise Status, Progress, Type, Reset, Focus, search, relation navigation, zoom, and pan.
- Confirm frost remains visible over a non-flat background.
- Confirm animations are noticeable but not distracting and reduced-motion disables them.
- Run the checks in `ARCHITECTURE.md` and rebuild the distributable template.

When intentionally departing from these rules, record the reason in the change description so the visual language evolves deliberately rather than through accidental drift.
