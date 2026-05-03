import math
import os
import random
import time
from threading import Thread

import psycopg
from dotenv import load_dotenv
from flask import Flask, Response, redirect, render_template_string, request, session, url_for

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "replace-with-a-secret-key")

FOLDERS = ["事實", "數據", "資訊", "名稱", "項目", "重點"]
TOTAL_STATEMENTS = 30

# Seconds before the “continue to next phase” button becomes active (e.g. 600 for 10 minutes).
NEXT_PHASE_WAIT_SECONDS = 10

# Phase 2: question index 1..30 maps to answer_1..answer_30 regardless of display order.
PHASE2_QUESTIONS = [
    None,  # unused; index 1 = question 1
    "關於「薩達姆·海珊」的資訊，存在哪一個資料夾？",
    "關於「格陵蘭島」的資訊，存在哪一個資料夾？",
    "關於「亞洲海嘯」的資訊，存在哪一個資料夾？",
    "關於「母牛產奶量」的資訊，存在哪一個資料夾？",
    "關於「藍鳥視覺」的資訊，存在哪一個資料夾？",
    "關於「麥可·傑克森」的資訊，存在哪一個資料夾？",
    "關於「美加邊界國家」的資訊，存在哪一個資料夾？",
    "關於「倫敦地鐵爆炸案」的資訊，存在哪一個資料夾？",
    "關於「美國總統人數」的資訊，存在哪一個資料夾？",
    "關於「凍甲」的資訊，存在哪一個資料夾？",
    "關於「彼得·詹寧斯」的資訊，存在哪一個資料夾？",
    "關於「教宗本篤十六世」的資訊，存在哪一個資料夾？",
    "關於「賓州與科羅拉多州高度」的資訊，存在哪一個資料夾？",
    "關於「沒有沙漠的大陸」的資訊，存在哪一個資料夾？",
    "關於「拉森 B 冰棚」的資訊，存在哪一個資料夾？",
    "關於「哥倫比亞號太空梭」的資訊，存在哪一個資料夾？",
    "關於「南極洲電話區碼」的資訊，存在哪一個資料夾？",
    "關於「25 美分硬幣溝槽」的資訊，存在哪一個資料夾？",
    "關於「冷藏橡皮筋」的資訊，存在哪一個資料夾？",
    "關於「薯條起源地」的資訊，存在哪一個資料夾？",
    "關於「艾爾·卡彭的名片」的資訊，存在哪一個資料夾？",
    "關於「約翰·藍儂的視力」的資訊，存在哪一個資料夾？",
    "關於「大西洋鹹度」的資訊，存在哪一個資料夾？",
    "關於「印有聖經的國旗」的資訊，存在哪一個資料夾？",
    "關於「Live 8 演唱會」的資訊，存在哪一個資料夾？",
    "關於「北約轟炸南斯拉夫」的資訊，存在哪一個資料夾？",
    "關於「大麥克上的芝麻」的資訊，存在哪一個資料夾？",
    "關於「中文字元數量」的資訊，存在哪一個資料夾？",
    "關於「鴕鳥的眼睛」的資訊，存在哪一個資料夾？",
    "關於「睡覺消耗的卡路里」的資訊，存在哪一個資料夾？",
]


def _stage_redirect():
    stage = session.get("stage")
    if stage in {"notice_name", "notice_statement"}:
        return redirect(url_for("saved_notice"))
    if stage == "statement":
        expected = session.get("expected_statement", 1)
        return redirect(url_for("statement_step", statement_number=expected))
    if stage == "waiting_phase2":
        return redirect(url_for("wait_phase2"))
    if stage == "phase2":
        expected = session.get("expected_phase2", 1)
        return redirect(url_for("phase2_step", step=expected))
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
    answer_columns = ",\n".join([f"answer_{i} TEXT" for i in range(1, TOTAL_STATEMENTS + 1)])
    create_sql = f"""
    CREATE TABLE IF NOT EXISTS experiment_entries (
        id BIGSERIAL PRIMARY KEY,
        name TEXT NOT NULL,
        {statement_columns},
        {answer_columns}
    );
    """
    with _get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(create_sql)
            for i in range(1, TOTAL_STATEMENTS + 1):
                cur.execute(f"ALTER TABLE experiment_entries ADD COLUMN IF NOT EXISTS answer_{i} TEXT;")
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


def _save_phase2_answer(row_id, question_index, answer_text):
    column_name = f"answer_{question_index}"
    update_sql = f"UPDATE experiment_entries SET {column_name} = %s WHERE id = %s;"
    with _get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(update_sql, (answer_text, row_id))
        conn.commit()


def _save_phase2_answer_async(row_id, question_index, answer_text):
    thread = Thread(
        target=_save_phase2_answer,
        args=(row_id, question_index, answer_text),
        daemon=True,
    )
    thread.start()


BASE_HTML = """
<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>網路對記憶儲存策略的影響</title>
  <style>
    body { font-family: Arial, sans-serif; max-width: 900px; margin: 40px auto; line-height: 1.5; padding: 0 16px; }
    .card { border: 1px solid #ddd; border-radius: 10px; padding: 20px; margin-top: 16px; }
    input[type=text], textarea { width: 100%; padding: 10px; margin-top: 8px; margin-bottom: 12px; }
    button { padding: 10px 16px; border: 0; border-radius: 8px; background: #0b66ff; color: white; cursor: pointer; }
    button:disabled { background: #aaa; color: #eee; cursor: not-allowed; }
  </style>
</head>
<body>
  <h1>網路對記憶儲存策略的影響</h1>
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
            session["phase2_unlock_at"] = time.time() + NEXT_PHASE_WAIT_SECONDS
            session["stage"] = "waiting_phase2"
            return redirect(url_for("wait_phase2"))
        session["expected_statement"] = next_idx
        session["stage"] = "statement"
        return redirect(url_for("statement_step", statement_number=next_idx))

    content = f"""
    <h2>已儲存</h2>
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
    if stage in {"notice_name", "notice_statement", "finished", "waiting_phase2", "phase2"}:
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
    <h2>第{statement_number}點  (共{TOTAL_STATEMENTS}點)</h2>
    <p>請輸入紙上顯示的句子，然後點擊提交。</p>
    <form method="post">
      <label>請輸入句子</label>
      <textarea name="typed_statement" rows="4" required></textarea>
      <button type="submit">提交</button>
    </form>
    """
    return render_template_string(BASE_HTML, content=content)


@app.route("/wait-phase2", methods=["GET", "POST"])
def wait_phase2():
    participant_row_id = session.get("participant_row_id")
    stage = session.get("stage")
    if not participant_row_id:
        return redirect(url_for("home"))
    if stage != "waiting_phase2":
        return _stage_redirect()

    if request.method == "POST":
        if time.time() < session.get("phase2_unlock_at", 0):
            return redirect(url_for("wait_phase2"))
        order = list(range(1, TOTAL_STATEMENTS + 1))
        random.shuffle(order)
        session["phase2_order"] = order
        session["expected_phase2"] = 1
        session["stage"] = "phase2"
        return redirect(url_for("phase2_step", step=1))

    unlock_at = session.get("phase2_unlock_at", 0)
    remaining = max(0, int(math.ceil(unlock_at - time.time())))
    content = f"""
    <h2>請等待測試人員的下一步指示</h2>
    <p>剩餘時間：<span id="timer">{remaining}</span> 秒</p>
    <form method="post" id="continue-form" style="text-align:center;">
      <button type="submit" id="continue-btn" {'disabled' if remaining > 0 else ''}>繼續下一階段</button>
    </form>
    <script>
      (function () {{
        var left = {remaining};
        var btn = document.getElementById('continue-btn');
        var label = document.getElementById('timer');
        if (left <= 0) {{
          btn.disabled = false;
          label.textContent = 0;
          return;
        }}
        btn.disabled = true;
        function tick() {{
          left -= 1;
          if (left < 0) left = 0;
          label.textContent = left;
          if (left <= 0) {{
            btn.disabled = false;
            return;
          }}
          setTimeout(tick, 1000);
        }}
        setTimeout(tick, 1000);
      }})();
    </script>
    """
    return render_template_string(BASE_HTML, content=content)


@app.route("/phase2/<int:step>", methods=["GET", "POST"])
def phase2_step(step):
    participant_row_id = session.get("participant_row_id")
    stage = session.get("stage")
    expected_step = session.get("expected_phase2", 1)
    order = session.get("phase2_order")
    if not participant_row_id or not order:
        return redirect(url_for("home"))
    if stage != "phase2":
        return _stage_redirect()
    if step != expected_step:
        return redirect(url_for("phase2_step", step=expected_step))

    question_id = order[step - 1]
    question_text = PHASE2_QUESTIONS[question_id]

    if request.method == "POST":
        answer_text = request.form.get("answer", "").strip()
        if not answer_text:
            return redirect(url_for("phase2_step", step=step))

        _save_phase2_answer_async(participant_row_id, question_id, answer_text)

        next_step = step + 1
        if next_step > TOTAL_STATEMENTS:
            session["stage"] = "finished"
            return redirect(url_for("finish"))
        session["expected_phase2"] = next_step
        return redirect(url_for("phase2_step", step=next_step))

    content = f"""
    <h2>問題 {step} / {TOTAL_STATEMENTS}</h2>
    <p>{question_text}</p>
    <form method="post">
      <label>請輸入答案（資料夾名稱）</label>
      <input type="text" name="answer" autocomplete="off" required>
      <button type="submit">提交</button>
    </form>
    """
    return render_template_string(BASE_HTML, content=content)


@app.route("/finish")
def finish():
    if not session.get("participant_row_id"):
        return redirect(url_for("home"))
    stage = session.get("stage")
    if stage != "finished":
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
