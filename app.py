import streamlit as st
import pandas as pd
import requests
import sqlite3
import json
import urllib.parse
from datetime import datetime

# --- 1. デザインエンジニアリング (Custom CSS) ---
st.set_page_config(page_title="懇親会調整 DX Pro", page_icon="🤝", layout="wide")

st.markdown("""
    <style>
    .main { background-color: #f9f9fb; }
    .stButton>button { border-radius: 8px; font-weight: 600; transition: all 0.2s; border: none; }
    .stButton>button:hover { transform: translateY(-1px); box-shadow: 0 4px 12px rgba(0,0,0,0.1); }
    .st-emotion-cache-1r6slb0 { border-radius: 12px; border: 1px solid #e6e9ef; background-color: white; padding: 20px; }
    h1, h2, h3 { color: #1e293b; font-family: 'Inter', sans-serif; }
    .recommend-badge { background-color: #fef3c7; color: #92400e; padding: 4px 12px; border-radius: 20px; font-size: 0.8rem; font-weight: bold; }
    </style>
    """, unsafe_allow_html=True)

# --- 2. データベース・コア・アーキテクチャ ---
DB_FILE = "konshinkai_v9_pro.db"
API_KEY = st.secrets.get("HOTPEPPER_API_KEY", "")

def run_query(query, params=(), is_select=False):
    with sqlite3.connect(DB_FILE) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(query, params)
        if is_select: return cursor.fetchall()
        conn.commit()

# テーブル初期化
run_query('CREATE TABLE IF NOT EXISTS events (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT, password TEXT)')
run_query('CREATE TABLE IF NOT EXISTS dates (id INTEGER PRIMARY KEY AUTOINCREMENT, event_id INTEGER, dt_text TEXT)')
run_query('CREATE TABLE IF NOT EXISTS responses (id INTEGER PRIMARY KEY AUTOINCREMENT, event_id INTEGER, name TEXT, ans TEXT, dislikes TEXT)')

# --- 3. ロジックレイヤー (おすすめ計算) ---
def get_processed_responses(ev_id):
    with sqlite3.connect(DB_FILE) as conn:
        df = pd.read_sql("SELECT name, ans, dislikes FROM responses WHERE event_id=?", conn, params=(ev_id,))
    if df.empty: return pd.DataFrame(), None
    
    rows = []
    for _, r in df.iterrows():
        try:
            d_row = json.loads(r["ans"])
            d_row["名前"] = r["name"]
            d_row["苦手・アレルギー"] = r["dislikes"]
            rows.append(d_row)
        except: continue
    
    res_df = pd.DataFrame(rows)
    # おすすめ度の計算 (○=2, △=1, ×=-10)
    score_map = {"○": 2, "△": 1, "×": -10}
    scores = {}
    date_cols = [c for c in res_df.columns if c not in ["名前", "苦手・アレルギー"]]
    for col in date_cols:
        scores[col] = res_df[col].map(score_map).sum()
    
    best_date = max(scores, key=scores.get) if scores else None
    return res_df, best_date

# --- 4. メインUIコンポーネント ---
st.sidebar.title("🤝 調整 DX Pro")
mode = st.sidebar.radio("役割を選択", ["参加者として回答", "管理者（幹事）", "システムオーナー"])
q_ev_id = st.query_params.get("event_id")

# --- A. 管理者モード ---
if mode == "管理者（幹事）":
    st.title("⚙️ 幹事ダッシュボード")
    
    with st.expander("➕ 新しい懇親会イベントを立ち上げる"):
        with st.form("new_ev"):
            t = st.text_input("イベント名 (例: 第1回 Python勉強会打ち上げ)")
            p = st.text_input("管理用パスワード", type="password")
            if st.form_submit_button("イベント作成"):
                if t and p:
                    run_query("INSERT INTO events (title, password) VALUES (?, ?)", (t, p))
                    st.success("作成完了！下のリストから選んでください。")
                    st.rerun()

    ev_list = pd.read_sql("SELECT * FROM events", sqlite3.connect(DB_FILE))
    if ev_list.empty: st.stop()
    
    sel_title = st.selectbox("管理するイベントを選択", ev_list["title"])
    target_ev = ev_list[ev_list["title"] == sel_title].iloc[0]
    ev_id = int(target_ev["id"])

    # ログイン
    if f"auth_{ev_id}" not in st.session_state: st.session_state[f"auth_{ev_id}"] = False
    if not st.session_state[f"auth_{ev_id}"]:
        with st.form(f"auth_form_{ev_id}"):
            pw = st.text_input("パスワードを入力", type="password")
            if st.form_submit_button("ログイン"):
                if pw == target_ev["password"]:
                    st.session_state[f"auth_{ev_id}"] = True
                    st.rerun()
                else: st.error("不一致")
        st.stop()

    # --- ログイン後: 幹事用機能 ---
    st.markdown(f"## 📍 {sel_title}")
    
    # 共有URLセクション
    share_url = f"https://your-app.streamlit.app/?event_id={ev_id}"
    st.text_input("📣 参加者配布用URL", value=share_url, help="このURLをSlack等に貼ってください")
    
    tab1, tab2, tab3 = st.tabs(["📊 回答状況・分析", "📅 日程設定", "🍴 店選定・告知"])

    with tab1:
        res_df, best_date = get_processed_responses(ev_id)
        if res_df.empty:
            st.info("まだ回答が届いていません。URLを共有して回答を待ちましょう。")
        else:
            if best_date:
                st.markdown(f"💡 **AIレコメンド:** 現在、最も調整がつきやすいのは <span class='recommend-badge'>{best_date}</span> です。", unsafe_allow_html=True)
            
            st.dataframe(res_df, use_container_width=True, hide_index=True)
            
            dis_list = [x for x in res_df["苦手・アレルギー"].tolist() if x]
            if dis_list:
                with st.chat_message("assistant"):
                    st.write(f"⚠️ **配慮が必要な食材:** {', '.join(dis_list)}")

    with tab2:
        st.subheader("候補日の管理")
        with st.form("add_date"):
            c1, c2 = st.columns(2)
            d = c1.date_input("日付")
            t_val = c2.time_input("開始時間", value=datetime.strptime("18:30", "%H:%M").time())
            if st.form_submit_button("候補日に追加"):
                dt_str = f"{d.strftime('%m/%d')}({['月','火','水','木','金','土','日'][d.weekday()]}) {t_val.strftime('%H:%M')}～"
                run_query("INSERT INTO dates (event_id, dt_text) VALUES (?, ?)", (ev_id, dt_str))
                st.rerun()
        
        # 既存日程の削除機能
        dates = run_query("SELECT * FROM dates WHERE event_id=?", (ev_id,), True)
        for d in dates:
            col_a, col_b = st.columns([4, 1])
            col_a.write(d['dt_text'])
            if col_b.button("削除", key=f"del_date_{d['id']}"):
                run_query("DELETE FROM dates WHERE id=?", (d['id'],))
                st.rerun()

    with tab3:
        st.subheader("お店の決定")
        date_rows = run_query("SELECT dt_text FROM dates WHERE event_id=?", (ev_id,), True)
        all_dates = [r['dt_text'] for r in date_rows]
        
        if not all_dates:
            st.warning("先に日程を設定してください。")
        else:
            with st.container(border=True):
                c1, c2, c3 = st.columns([2, 2, 1])
                sel_date = c1.selectbox("開催日に決定する日", all_dates, index=all_dates.index(best_date) if best_date in all_dates else 0)
                area = c2.text_input("駅名・エリア", placeholder="例: 所沢")
                bud = c3.selectbox("予算", ["指定なし", "3001〜4000円", "4001〜5000円"])
                if st.button("🔍 条件に合う店を探す", use_container_width=True):
                    bud_code = {"3001〜4000円":"B003", "4001〜5000円":"B008"}.get(bud, "")
                    res = requests.get("http://webservice.recruit.co.jp/hotpepper/gourmet/v1/", 
                                     params={"key": API_KEY, "keyword": area, "budget": bud_code, "count": 10, "format": "json"})
                    st.session_state[f"shops_{ev_id}"] = res.json().get('results', {}).get('shop', [])

            if f"shops_{ev_id}" in st.session_state:
                for s in st.session_state[f"shops_{ev_id}"]:
                    with st.container(border=True):
                        l, r = st.columns([1, 2])
                        l.image(s['photo']['pc']['l'], use_container_width=True)
                        r.subheader(s['name'])
                        r.write(f"🍴 {s['genre']['name']} | 💰 {s['budget']['name']}")
                        r.caption(s['catch'])
                        g_map = f"https://www.google.com/maps/search/?api=1&query={urllib.parse.quote(s['name'] + ' ' + s['address'])}"
                        if r.button(f"✅ {s['name']} を予約・告知する", key=f"btn_{s['id']}", type="primary"):
                            st.session_state[f"final_{ev_id}"] = f"""【懇親会のお知らせ】\n\n日時：{sel_date}\n会場：{s['name']}\n場所：{s['address']}\n地図：{g_map}\n詳細：{s['urls']['pc']}\n\nよろしくお願いします！"""
                            st.rerun()

            if f"final_{ev_id}" in st.session_state:
                st.divider()
                st.success("🎉 Slack/Teamsに以下の文章を貼り付けてください")
                st.text_area("告知用メッセージ", value=st.session_state[f"final_{ev_id}"], height=200)

# --- B. 参加者モード ---
elif mode == "参加者として回答":
    st.title("🤝 アンケートに回答")
    ev_df = pd.read_sql("SELECT * FROM events", sqlite3.connect(DB_FILE))
    
    current_ev_id = None
    if q_ev_id:
        try:
            current_ev_id = int(q_ev_id)
            target = ev_df[ev_df["id"] == current_ev_id]
            if not target.empty:
                st.info(f"イベント: **{target.iloc[0]['title']}**")
            else: current_ev_id = None
        except: current_ev_id = None
    
    if not current_ev_id:
        if ev_df.empty: st.info("現在募集中のイベントはありません。"); st.stop()
        sel = st.selectbox("回答するイベントを選択", ev_df["title"])
        current_ev_id = int(ev_df[ev_df["title"] == sel].iloc[0]["id"])

    date_rows = run_query("SELECT dt_text FROM dates WHERE event_id=?", (current_ev_id,), True)
    d_list = [r['dt_text'] for r in date_rows]
    
    if not d_list:
        st.warning("幹事が日程を準備中です。しばらくお待ちください。")
    else:
        with st.form("ans_form"):
            name = st.text_input("あなたの氏名")
            dis = st.text_input("苦手な食材・アレルギー (あれば)")
            st.write("▼ 都合のつく日時にチェックを入れてください")
            ans_data = {}
            for d in d_list:
                ans_data[d] = st.radio(d, ["○", "△", "×"], horizontal=True)
            
            if st.form_submit_button("回答を送信する"):
                if not name: st.error("お名前を入力してください。")
                else:
                    run_query("INSERT INTO responses (event_id, name, ans, dislikes) VALUES (?, ?, ?, ?)", 
                             (current_ev_id, name, json.dumps(ans_data, ensure_ascii=False), dis))
                    st.success("回答を受け付けました。ありがとうございました！")
                    st.balloons()
                    st.rerun()
        
        st.subheader("現在の回答一覧")
        rdf, _ = get_processed_responses(current_ev_id)
        if not rdf.empty: st.dataframe(rdf, use_container_width=True, hide_index=True)

# --- C. システムオーナー ---
else:
    st.title("👑 システム全削除・メンテナンス")
    if st.text_input("オーナーパスワード", type="password") == OWNER_PASS:
        evs = pd.read_sql("SELECT * FROM events", sqlite3.connect(DB_FILE))
        for _, row in evs.iterrows():
            if st.button(f"🗑 {row['title']} の全データを削除", key=f"del_ev_{row['id']}"):
                run_query("DELETE FROM events WHERE id=?", (row['id'],))
                run_query("DELETE FROM dates WHERE event_id=?", (row['id'],))
                run_query("DELETE FROM responses WHERE event_id=?", (row['id'],))
                st.rerun()
