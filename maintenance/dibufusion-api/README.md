# DibuFusion API maintenance

The [installation payload](../../skills/dibufusion-api/SKILL.md) contains the CLI and its required operation catalog. Run offline regressions from the repository root:

```bash
./.venv/bin/python -m unittest discover -s maintenance/dibufusion-api/tests -v
```

[Verification evidence](verification.md) records historical API observations and unresolved cases. Tests use mocks and do not contact the live console. Installed copies are synchronized separately by the user.
