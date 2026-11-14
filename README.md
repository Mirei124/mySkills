# Skills index

Reusable agent skills and their maintenance resources.

| Skill | Purpose | Maintenance |
|---|---|---|
| [hypha-governance](skills/hypha-governance/SKILL.md) | Local task, knowledge and saved-context management with an offline graph view. Python 3.10+. | [Guide, tests and frontend](maintenance/hypha-governance/README.md) |
| [dibufusion-api](skills/dibufusion-api/SKILL.md) | Direct API access to the internal DibuFusion console. Python 3; authorized console access required. | [Tests and verification](maintenance/dibufusion-api/README.md) |
| [wayfire-computer-use](skills/wayfire-computer-use/SKILL.md) | Visual control of Wayfire applications through Portal/PipeWire and virtual input. Linux; Rust build required initially. | [Build and regressions](maintenance/wayfire-computer-use/README.md) |
| [research-hypothesis-loop](skills/deprecated/research-hypothesis-loop/SKILL.md) | Deprecated research hypothesis workflow, retained for explicit use. | [Evaluations](maintenance/research-hypothesis-loop/README.md) |

## Installation

Install the entire selected skill directory, preserving its supporting files. Skill managers such as `npx skills` should use the corresponding directory under `skills/`. Deprecated skills remain under `skills/deprecated/`.

For a manual installation, copy a skill into your agent's skill directory, for example:

```bash
mkdir -p ~/.agents/skills
cp -a skills/wayfire-computer-use ~/.agents/skills/
```

Wayfire includes its Rust source and lockfile. On the target Linux machine, install the [build dependencies](skills/wayfire-computer-use/references/usage.md#dependencies), then run:

```bash
cd ~/.agents/skills/wayfire-computer-use
./build.sh
./target/release/wayfire-computer-use doctor
```

The compiled executable and `target/` are not committed. Rust/C tooling is needed for compilation; normal runtime uses the binary and system libraries, with no Python dependency. Rebuild explicitly after source updates. Hypha and DibuFusion run their bundled Python scripts; Hypha's generated HTML requires no Node.js at runtime.

## Repository maintenance

Start at [maintenance/README.md](maintenance/README.md) for tests, frontend builds, evaluations, historical plans and verification evidence. [AGENTS.md](AGENTS.md) defines repository conventions, including skill-prefixed commit subjects.

`skills/` contains installation payloads and source required for target-machine builds. `maintenance/<skill-name>/` contains development-only resources. Repository-wide Git hooks, guidance and task records stay at the root. Installed skill copies are updated separately; reorganizing this repository does not synchronize them automatically.
