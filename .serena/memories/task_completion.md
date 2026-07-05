# Task Completion

- Use the narrowest validation for touched code first.
- Backend Python: compile touched modules and use focused bench/site checks when Frappe state matters.
- Frappe schema/DocType changes: run `bench --site kratium.localhost migrate` from `/home/keenan/Kratium` when appropriate.
- Frontend source changes: run `cd frontend && yarn build`; add `yarn test:run` when behaviour/tests changed.
- Do not fix unrelated failures; report them separately.