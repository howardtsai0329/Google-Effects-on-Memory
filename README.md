# Experiment Website (Flask + Neon)

This web app now runs the simplified flow:

1. Participant enters a name.
2. Name is saved to Neon in the `name` field.
3. A centered notice appears: "Your entry has been saved into the folder ...", and user clicks Confirm.
4. Participant completes 40 statement steps (statements are on paper, not shown on screen).
5. Each statement submit stores a random folder value into `statement_1` ... `statement_40`.
6. After each submit, the same save notice appears and user confirms to continue.

## Run

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
set DATABASE_URL="your_neon_connection_string"
py -3 app.py
```

Open:

`http://127.0.0.1:5000`

## One-Line Run (Windows Recommended)

No `make` needed:

```powershell
.\run.ps1
```

## One-Line Run (Make)

If you have `make` installed, run:

```powershell
make run
```

## Deploy Publicly (Render)

1. Push this folder to a GitHub repo.
2. Go to [Render](https://render.com/) -> New -> Blueprint.
3. Select your repo (it will detect `render.yaml`).
4. Add environment variable:
   - `DATABASE_URL` = your Neon connection string
5. Deploy.

Render will give you a public URL like:

`https://memory-folder-study.onrender.com`

## Neon Table

The app auto-creates this table on startup:

- `experiment_entries`
  - `id`
  - `name`
  - `statement_1` ... `statement_40`

Total fields requested are covered: `name` + 40 statement fields.
