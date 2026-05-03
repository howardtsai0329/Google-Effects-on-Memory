import os
import random
from threading import Thread

import psycopg
from dotenv import load_dotenv
from flask import Flask, Response, redirect, render_template_string, request, session, url_for

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "replace-with-a-secret-key")

FOLDERS = ["FACTS", "DATA", "INFO", "NAMES", "ITEMS", "POINTS"]
TOTAL_STATEMENTS = 30


def _stage_redirect():
    stage = session.get("stage")
    if stage in {"notice_name", "notice_statement"}:
        return redirect(url_for("saved_notice"))
    if stage == "statement":
        expected = session.get("expected_statement", 1)
        return redirect(url_for("statement_step", statement_number=expected))
    if stage == "finished":
        return redirect(url_for("finish"))
    return redirect(url_for("home"))


def _get_db_connection():
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        raise RuntimeError("DATABASE_URL is missing. Set your Neon connection string first.")
    return psycopg.connect(db_url)


def _ensure_table():
    statement_columns = ",\n".join([f"statement_{i} TEXT" for i in range(1, TOTAL_STATEMENTS + 1)])
    create_sql = f"""
    CREATE TABLE IF NOT EXISTS experiment_entries (
        id BIGSERIAL PRIMARY KEY,
        name TEXT NOT NULL,
        {statement_columns}
    );
    """
    with _get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(create_sql)
        conn.commit()


def _insert_participant(name):
    with _get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("INSERT INTO experiment_entries (name) VALUES (%s) RETURNING id;", (name,))
            row_id = cur.fetchone()[0]
        conn.commit()
    return row_id


def _save_statement_folder(row_id, statement_index, folder_name):
    column_name = f"statement_{statement_index}"
    update_sql = f"UPDATE experiment_entries SET {column_name} = %s WHERE id = %s;"
    with _get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(update_sql, (folder_name, row_id))
        conn.commit()


def _save_statement_folder_async(row_id, statement_index, folder_name):
    # Fire-and-forget DB write so the UI can progress immediately.
    thread = Thread(
        target=_save_statement_folder,
        args=(row_id, statement_index, folder_name),
        daemon=True,
    )
    thread.start()


BASE_HTML = """
<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>Google Effects on Memory</title>
  <style>
    body { font-family: Arial, sans-serif; max-width: 900px; margin: 40px auto; line-height: 1.5; padding: 0 16px; }
    .card { border: 1px solid #ddd; border-radius: 10px; padding: 20px; margin-top: 16px; }
    input[type=text], textarea { width: 100%; padding: 10px; margin-top: 8px; margin-bottom: 12px; }
    button { padding: 10px 16px; border: 0; border-radius: 8px; background: #0b66ff; color: white; cursor: pointer; }
  </style>
</head>
<body>
  <h1>Google Effects on Memory</h1>
  <div class="card">
    {{ content|safe }}
  </div>
</body>
</html>
"""


@app.route("/", methods=["GET", "POST"])
def home():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        if not name:
            return redirect(url_for("home"))

        participant_row_id = _insert_participant(name)
        session["participant_row_id"] = participant_row_id
        session["expected_statement"] = 1
        session["notice_folder"] = random.choice(FOLDERS)
        session["notice_for"] = "name"
        session["stage"] = "notice_name"
        return redirect(url_for("saved_notice"))

    content = """
    <h2>開始測試</h2>
    <p>請輸入您的名字</p>
    <form method="post">
      <label>名字</label>
      <input type="text" name="name" placeholder="小明" required>
      <button type="submit">開始測試</button>
    </form>
    """
    return render_template_string(BASE_HTML, content=content)


@app.route("/saved-notice", methods=["GET", "POST"])
def saved_notice():
    folder_name = session.get("notice_folder")
    notice_for = session.get("notice_for")
    stage = session.get("stage")
    if not folder_name or not notice_for:
        return _stage_redirect()
    if stage not in {"notice_name", "notice_statement"}:
        return _stage_redirect()

    if request.method == "POST":
        if stage == "notice_name":
            session["stage"] = "statement"
            expected = session.get("expected_statement", 1)
            return redirect(url_for("statement_step", statement_number=expected))

        current_idx = session.get("expected_statement", 1)
        next_idx = current_idx + 1
        if next_idx > TOTAL_STATEMENTS:
            session["stage"] = "finished"
            return redirect(url_for("finish"))
        session["expected_statement"] = next_idx
        session["stage"] = "statement"
        return redirect(url_for("statement_step", statement_number=next_idx))

    content = f"""
    <h2>Saved</h2>
    <p style="text-align:center; font-size: 1.2rem;">
      您的資料已經被儲存到 <strong>{folder_name}</strong> 資料夾中。
    </p>
    <form method="post" style="text-align:center;">
      <button type="submit">確認</button>
    </form>
    """
    return render_template_string(BASE_HTML, content=content)


@app.route("/statement/<int:statement_number>", methods=["GET", "POST"])
def statement_step(statement_number):
    participant_row_id = session.get("participant_row_id")
    stage = session.get("stage")
    expected_statement = session.get("expected_statement", 1)
    if not participant_row_id:
        return redirect(url_for("home"))
    if stage in {"notice_name", "notice_statement", "finished"}:
        return _stage_redirect()
    if stage != "statement":
        return _stage_redirect()
    if statement_number != expected_statement:
        return redirect(url_for("statement_step", statement_number=expected_statement))

    if request.method == "POST":
        typed_statement = request.form.get("typed_statement", "").strip()
        if not typed_statement:
            return redirect(url_for("statement_step", statement_number=statement_number))

        assigned_folder = random.choice(FOLDERS)
        _save_statement_folder_async(participant_row_id, statement_number, assigned_folder)

        session["notice_folder"] = assigned_folder
        session["notice_for"] = "statement"
        session["stage"] = "notice_statement"
        return redirect(url_for("saved_notice"))

    content = f"""
    <h2>Statement {statement_number} of {TOTAL_STATEMENTS}</h2>
    <p>請輸入紙上顯示的句子，然後點擊提交。</p>
    <form method="post">
      <label>請輸入句子</label>
      <textarea name="typed_statement" rows="4" required></textarea>
      <button type="submit">提交</button>
    </form>
    """
    return render_template_string(BASE_HTML, content=content)


@app.route("/finish")
def finish():
    if not session.get("participant_row_id"):
        return redirect(url_for("home"))
    if session.get("stage") != "finished":
        return _stage_redirect()

    content = """
    <h2>完成</h2>
    <p><a href="/">再進行一次測試</a></p>
    """
    return render_template_string(BASE_HTML, content=content)


@app.route("/favicon.ico")
def favicon():
    return Response(status=204)


if __name__ == "__main__":
    _ensure_table()
    app.run(debug=True)
