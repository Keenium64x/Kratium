# Input System Next Pass Checklist

Use this before touching `kratium/input_system.py`.

## 1. Choose The Station

Pick exactly one station for the pass:

- Input Streams
- Orchestration Entry
- Clarification
- Collect Information
- Route Selection
- Implementation Design
- Execution Bus
- Outcome Review
- Utility Tools

## 2. Define The Station

```text
Station:
Purpose:
Input:
Output:
Reads shared state:
Writes shared state:
Next handoff:
User concepts to flag:
```

## 3. Inspect Only What Is Needed

Use Serena/symbol lookup for `kratium/input_system.py`:

- symbol overview if structure is unclear;
- exact function body if changing one function;
- references if changing a contract used elsewhere.

Do not reread the whole file.

## 4. Plan Code Before Editing

```text
Files:
Functions/classes:
Input/output contracts:
Validation:
Questions for user:
```

## 5. After Editing

- Update `docs/input_system/INPUT_SYSTEM_MAP.md` if responsibilities or plumbing changed.
- Update `docs/USER_CAPABILITY_INDEX.md` if new important concepts were introduced.
- Run the narrowest validation.
- Handoff with station map, plumbing explanation, files touched, validation, and next question.
