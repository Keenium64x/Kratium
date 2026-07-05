# Core

- Frappe bench app at `/home/keenan/Kratium/apps/kratium`; bench root is `/home/keenan/Kratium`.
- Main backend package: `kratium/`.
- Distinct domains visible in source: `input_system.py`, `execution_system/`, `planning_system/`, `time_system/`, `knowledge_system/`, notifications/firebase/reminders.
- Frontend lives in `frontend/`; built assets copy into `kratium/public/frontend` and `kratium/www/frontend.html`.
- Read `mem:tech_stack` for framework/tool versions and `mem:conventions` for code style before broad edits.
- Read `mem:input_system/core` before changing the AI/input orchestration layer.