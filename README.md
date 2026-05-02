# Experiment Website

This web app runs the flow:

1. Participant enters a name.
2. Name is saved to Neon in the `name` field.
3. A notice appears: "Your entry has been saved into the folder ...", and user clicks Confirm.
4. Participant completes 30 statement steps (statements are on paper, not shown on screen).
5. Each statement submit stores a random folder value into `statement_1` ... `statement_30`.
6. After each submit, the same save notice appears and user confirms to continue.


## One-Line Run (Windows Recommended)

```powershell
.\run.ps1
```

Open:

`http://127.0.0.1:5000`


## Deploy Publicly (Render)

Public URL:

`[https://memory-folder-study.onrender.com](https://memory-folder-study.onrender.com)`

## Neon Table

The app auto-creates this table on startup:

- `experiment_entries`
  - `id`
  - `name`
  - `statement_1` ... `statement_30`

Total fields requested are covered: `name` + 30 statement fields.
