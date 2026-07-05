# Tech Stack

- Backend: Frappe app, Python `>=3.10` managed by bench.
- AI/input layer dependencies in `pyproject.toml`: `pydantic-ai-slim>=1.99,<2`, `httpx`, `ddgs`, `beautifulsoup4`, `logfire[system-metrics]`.
- Frontend: Vue 3 + Vite + Frappe UI under `frontend/`.
- Frontend package manager: Yarn.
- Frontend testing/linting: Vitest and Biome.
- Python lint/format config: Ruff in `pyproject.toml`; quote style double, tab indentation, line length 110.