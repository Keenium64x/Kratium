# Conventions

- Python formatting uses tabs and double quotes per Ruff config.
- Frappe DocTypes follow standard generated folder structure under each domain module.
- Existing backend files mix Frappe APIs with plain Python service functions; avoid introducing unrelated framework patterns.
- User-facing planned system code should preserve top-down VS Code region structure when creating or restructuring orchestration/planning code.
- For the input/orchestration layer, preserve a visible distinction between structural sections, scaffold functions, and completed implementation.