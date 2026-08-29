# Hypha 前端

此目录保存 Hypha Canvas 的开发源码。发布时运行 `python3 frontend/build_template.py`，把 `src/view.html` 复制成 skill 内唯一的运行时模板 `skills/hypha-governance/templates/view.html`。CLI 本身不依赖 Node，因此生成的 `view.html` 仍可离线、单文件打开。

React/TypeScript/Vite、ESLint、Vitest 与 Playwright 将只在这里作为开发依赖落地；skill 中只交付构建后的 HTML 模板和 Python CLI。
