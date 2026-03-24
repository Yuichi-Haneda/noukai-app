import streamlit as st
import pandas as pd
import requests
import sqlite3
import json
import urllib.parse
from datetime import datetime

# --- 基本設定 ---
st.set_page_config(page_title="懇親会調整 Pro Max+", page_icon="🤝", layout="wide")

# 定数管理
DB_FILE = "multi_event_v8.db" 
OWNER_PASS = "owner2026" 
API_KEY = st.secrets.get("HOTPEPPER_API_KEY", "")
BUDGET_MAP = {"指定なし": "", "2001〜3000円": "B002", "3001〜4000円": "B003", "4001〜5000円": "B008", "5001〜7000円": "B004"}

# --- データベース共通関数 ---
def run_query(query, params=(), is_select=False):
    with sqlite3.connect(DB_FILE) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(query, params)
        if is_select:
            return cursor.fetchall()
        conn.commit()

def init_db():
    run_query('CREATE TABLE IF NOT EXISTS events (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT, password TEXT)')
    run_query('CREATE TABLE IF NOT EXISTS dates (id INTEGER PRIMARY KEY AUTOINCREMENT, event_id INTEGER, dt_text TEXT)')
    run_query('CREATE TABLE IF NOT EXISTS responses (id INTEGER PRIMARY KEY AUTOINCREMENT, event_id INTEGER, name TEXT, ans TEXT, dislikes TEXT)')

init_db()

def get_responses_df(ev_id):
    with sqlite3.connect(DB_FILE) as conn:
        df_raw = pd.read_sql("SELECT name, ans, dislikes FROM responses WHERE event_id=?", conn, params=(ev_id,))
    if df_raw.empty: return pd.DataFrame()
    rows = []
    for _, r in df_raw.iterrows():
        try:
            d_row = json.loads(r["ans"])
            d_row["名前"] = r["name"]
            d_row["苦手・アレルギー"] = r["dislikes"]
            rows.append(d_row)
        except: continue
    df = pd.DataFrame(rows)
    cols = ["名前", "苦手・アレルギー"] + [c for c in df.columns if c not in ["名前", "苦手・アレルギー"]]
    return df[cols]

# --- UI制御 ---
st.sidebar.title("🤝 懇親会調整くん")
mode = st.sidebar.radio("モード切替", ["参加者画面", "管理者画面", "サイトオーナー画面"])
q_ev_id = st.query_params.get("event_id")

# --- 1. サイトオーナー画面 ---
if mode == "サイトオーナー画面":
    st.title("👑 全イベント管理")
    if st.text_input("オーナーパスワード", type="password") == OWNER_PASS:
        with sqlite3.connect(DB_FILE) as conn:
            evs = pd.read_sql("SELECT * FROM events", conn)
        for _, row in evs.iterrows():
            c1, c2 = st.columns([4, 1])
            c1.write(f"ID: {row['id']} | **{row['title']}**")
            if c2.button("削除", key=f"own_del_{row['id']}"):
                run_query("DELETE FROM events WHERE id=?", (row['id'],))
                run_query("DELETE FROM dates WHERE event_id=?", (row['id'],))
                run_query("DELETE FROM responses WHERE event_id=?", (row['id'],))
                st.rerun()

# --- 2. 管理者画面 ---
elif mode == "管理者画面":
    st.title("⚙️ 管理者パネル")
    with st.expander("➕ 新規イベント作成"):
        with st.form("create_new"):
            t = st.text_input("イベント名")
            p = st.text_input("管理パスワード", type="password")
            if st.form_submit_button("作成"):
                if t and p:
                    run_query("INSERT INTO events (title, password) VALUES (?, ?)", (t, p))
                    st.success("作成しました。")
                    st.rerun()

    with sqlite3.connect(DB_FILE) as conn:
        ev_df = pd.read_sql("SELECT * FROM events", conn)
    if ev_df.empty: st.stop()
    
    sel_title = st.selectbox("管理するイベントを選択", ev_df["title"])
    target_ev = ev_df[ev_df["title"] == sel_title].iloc[0]
    ev_id = int(target_ev["id"])

    auth_key = f"auth_{ev_id}"
    if not st.session_state.get(auth_key):
        with st.form(f"login_{ev_id}"):
            input_pw = st.text_input(f"🔓 {sel_title} のパスワード", type="password")
            if st.form_submit_button("ログイン"):
                if input_pw == target_ev["password"]:
                    st.session_state[auth_key] = True
                    st.rerun()
                else: st.error("不一致")
        st.stop()

    st.info(f"🔗 **参加者用URL:** `https://your-app-url.streamlit.app/?event_id={ev_id}`")
    
    t1, t2, t3, t4 = st.tabs(["📅 日程設定", "📊 回答状況", "🍴 会場決定", "🗑 削除"])

    with t1:
        st.subheader("候補日時追加")
        c1, c2 = st.columns(2)
        d = c1.date_input("日付")
        tm = c2.time_input("時間", value=datetime.strptime("18:30", "%H:%M").time())
        if st.button("追加"):
            dt_str = f"{d.strftime('%m/%d')}({['月','火','水','木','金','土','日'][d.weekday()]}) {tm.strftime('%H:%M')}～"
            run_query("INSERT INTO dates (event_id, dt_text) VALUES (?, ?)", (ev_id, dt_str))
            st.rerun()

    with t2:
        df_res = get_responses_df(ev_id)
        if not df_res.empty:
            st.dataframe(df_res, use_container_width=True)
            dis_list = [x for x in df_res["苦手・アレルギー"].tolist() if x]
            if dis_list: st.warning(f"苦手なもの: {', '.join(dis_list)}")
            st.session_state[f"dis_{ev_id}"] = dis_list
        else: st.info("回答待ち")

    with t3:
        st.subheader("🍴 最適な会場を見つける")
        date_rows = run_query("SELECT dt_text FROM dates WHERE event_id=?", (ev_id,), True)
        dates = [r['dt_text'] for r in date_rows]
        
        if not dates:
            st.warning("先に日程を登録してください。")
        else:
            with st.container(border=True):
                c_d, c_a, c_b = st.columns([2, 2, 1])
                sel_date = c_d.selectbox("開催決定日", dates)
                area = c_a.text_input("エリア・駅名", placeholder="例：所沢")
                bud = c_b.selectbox("予算", list(BUDGET_MAP.keys()))
                search_btn = st.button("🔍 検索実行", use_container_width=True)

            if search_btn and area:
                params = {"key": API_KEY, "keyword": area, "budget": BUDGET_MAP[bud], "count": 10, "format": "json"}
                res = requests.get("http://webservice.recruit.co.jp/hotpepper/gourmet/v1/", params=params)
                st.session_state.shops = res.json().get('results', {}).get('shop', [])

            if "shops" in st.session_state:
                for s in st.session_state.shops:
                    with st.container(border=True):
                        col1, col2 = st.columns([1, 2])
                        with col1: st.image(s['photo']['pc']['l'], use_container_width=True)
                        with col2:
                            st.subheader(s['name'])
                            st.write(f"「{s['catch']}」")
                            st.caption(f"💰 {s['budget']['name']} | 🚬 {s['non_smoking']} | 🏠 {s['address']}")
                            g_map_url = f"https://www.google.com/maps/search/?api=1&query={urllib.parse.quote(s['name'] + ' ' + s['address'])}"
                            if st.button(f"✅ {s['name']}に決定", key=f"sel_{s['id']}", type="primary"):
                                st.session_state[f"msg_{ev_id}"] = f"【懇親会のお知らせ】\n\n日時：{sel_date}\n会場：{s['name']}\n地図：{g_map_url}\n詳細：{s['urls']['pc']}\n\nお待ちしております！"
                                st.rerun()

            if f"msg_{ev_id}" in st.session_state:
                st.divider()
                st.text_area("案内文（コピー用）", value=st.session_state[f"msg_{ev_id}"], height=200)

    with t4:
        if st.button("イベントを完全に削除", type="primary"):
            run_query("DELETE FROM events WHERE id=?", (ev_id,))
            st.rerun()

# --- 3. 参加者画面 ---
else:
    st.title("🤝 懇親会アンケート")
    with sqlite3.connect(DB_FILE) as conn:
        ev_df = pd.read_sql("SELECT * FROM events", conn)
    
    current_ev_id = None
    if q_ev_id:
        try:
            current_ev_id = int(q_ev_id)
            target = ev_df[ev_df["id"] == current_ev_id]
            if not target.empty: st.info(f"イベント：**{target.iloc[0]['title']}**")
            else: current_ev_id = None
        except: current_ev_id = None

    if not current_ev_id:
        if ev_df.empty: st.stop()
        sel_title = st.selectbox("イベントを選択", ev_df["title"])
        current_ev_id = int(ev_df[ev_df["title"] == sel_title].iloc[0]["id"])

    date_rows = run_query("SELECT dt_text FROM dates WHERE event_id=?", (current_ev_id,), True)
    date_list = [r['dt_text'] for r in date_rows]
    
    if date_list:
        with st.form("ans"):
            name = st.text_input("お名前")
            dis = st.text_input("苦手なもの")
            ans = {d: st.radio(d, ["○", "△", "×"], horizontal=True) for d in date_list}
            if st.form_submit_button("送信"):
                if name:
                    run_query("INSERT INTO responses (event_id, name, ans, dislikes) VALUES (?, ?, ?, ?)", (current_ev_id, name, json.dumps(ans, ensure_ascii=False), dis))
                    st.success("完了！")
                    st.rerun()
        st.dataframe(get_responses_df(current_ev_id), use_container_width=True, hide_index=True)
