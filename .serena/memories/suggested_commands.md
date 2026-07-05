# Suggested Commands

- From bench root `/home/keenan/Kratium`: run Frappe commands with `bench --site kratium.localhost ...`.
- Frontend dev from app root: `yarn dev` or `cd frontend && yarn dev`.
- Frontend build from app root: `yarn build` or `cd frontend && yarn build`.
- Frontend tests from `frontend/`: `yarn test:run`.
- Frontend lint/write fixes from `frontend/`: `yarn lint`.
- Python compile sanity for touched backend files: `python -m py_compile <file>` inside bench env when available.