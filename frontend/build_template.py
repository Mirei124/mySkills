"""Copy the self-contained view template into the distributable skill."""
from pathlib import Path

ROOT = Path(__file__).parents[1]
SOURCE = ROOT / "frontend" / "dist" / "index.html"
TARGET = ROOT / "skills" / "hypha-governance" / "templates" / "view.html"

def main() -> None:
    text = SOURCE.read_text(encoding="utf-8")
    if "{{HYPHA_DATA}}" not in text:
        raise SystemExit("template must contain {{HYPHA_DATA}}")
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    TARGET.write_text(text, encoding="utf-8")
    print(TARGET.relative_to(ROOT))

if __name__ == "__main__":
    main()
