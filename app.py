import streamlit as st
import pandas as pd
import requests
import sqlite3
import json
import os
import urllib.parse
from datetime import datetime

# --- 基本設定 ---
st.set_page_config(page_title="懇親会調整 Pro Max+", page_icon="🤝", layout="wide")
API_KEY = st.secrets.get("HOTPEPPER_API_KEY", "")
DB_FILE = "multi_event_v5.db" # 新規DBで構造を安定させます
OWNER_PASS = "owner2026" 

BUDGET_MAP = {"指定なし": "", "2001〜3000円": "B002", "3001〜4000円": "B003", "4001〜5000円": "B008", "5001〜7000円": "B004"}

# --- DB初期化 ---
def init_db():
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute('CREATE TABLE IF NOT EXISTS events (id INTEGER PRIMARY KEY, title TEXT, password TEXT)')
        c.execute('CREATE TABLE IF NOT EXISTS dates (id INTEGER PRIMARY KEY, event_id INTEGER, dt_text TEXT)')
        c.execute('CREATE TABLE IF NOT EXISTS responses (id INTEGER PRIMARY KEY, event_id INTEGER, name TEXT, ans TEXT, dislikes TEXT)')
        conn.commit()

init_db()

# --- データ操作関数 ---
def get_events():
    with sqlite3.connect(DB_FILE) as conn:
        return pd.read_sql("SELECT * FROM events", conn)

def get_responses(ev_id):
    with sqlite3.connect(DB_FILE) as conn:
        resps = pd.read_sql(f"SELECT name, ans, dislikes FROM responses WHERE event_id={ev_id}", conn)
    if resps.empty: return pd.DataFrame()
    rows = []
    for _, r in resps.iterrows():
        try:
            d_row = json.loads(r["ans"])
            d_row["名前"] = r["name"]
            d_row["苦手・アレルギー"] = r["dislikes"]
            rows.append(d_row)
        except: continue
    df = pd.DataFrame(rows)
    cols = ["名前", "苦手・アレルギー"] + [c for c in df.columns if c not in ["名前", "苦手・アレルギー"]]
    return df[cols]

# --- メインロジック ---
st.sidebar.title("🤝 懇親会調整くん")
mode = st.sidebar.radio("モード切替", ["参加者画面", "管理者画面", "サイトオーナー画面"])

# URLパラメータ取得
query_params = st.query_params
q_ev_id = query_params.get("event_id")

# --- サイトオーナー画面 ---
if mode == "サイトオーナー画面":
    st.title("👑 全イベント管理")
    if st.text_input("オーナーパスワード", type="password") == OWNER_PASS:
        evs = get_events()
        for _, row in evs.iterrows():
            c1, c2 = st.columns([4, 1])
            c1.write(f"ID: {row['id']} | **{row['title']}**")
            if c2.button("削除", key=f"own_del_{row['id']}"):
                with sqlite3.connect(DB_FILE) as conn:
                    c = conn.cursor()
                    c.execute("DELETE FROM events WHERE id=?", (row['id'],))
                    c.execute("DELETE FROM dates WHERE event_id=?", (row['id'],))
                    c.execute("DELETE FROM responses WHERE event_id=?", (row['id'],))
                st.rerun()

# --- 管理者画面 ---
elif mode == "管理者画面":
    st.title("⚙️ イベント管理者パネル")
    
    # 1. イベント作成
    with st.expander("➕ 新しい懇親会イベントを作成する"):
        with st.form("create_new"):
            t = st.text_input("イベント名")
            p = st.text_input("管理パスワード設定", type="password")
            if st.form_submit_button("作成実行"):
                if t and p:
                    with sqlite3.connect(DB_FILE) as conn:
                        conn.cursor().execute("INSERT INTO events (title, password) VALUES (?, ?)", (t, p))
                    st.success("作成しました。下のリストから選んでログインしてください。")
                    st.rerun()

    # 2. イベント選択
    event_list = get_events()
    if event_list.empty:
        st.info("イベントがありません。作成してください。")
        st.stop()
    
    sel_title = st.selectbox("管理するイベントを選択", event_list["title"])
    target_ev = event_list[event_list["title"] == sel_title].iloc[0]
    ev_id = target_ev["id"]

    # 3. 個別ログイン認証
    auth_key = f"logged_in_ev_{ev_id}"
    if auth_key not in st.session_state: st.session_state[auth_key] = False

    if not st.session_state[auth_key]:
        with st.form(f"login_{ev_id}"):
            st.write(f"🔓 **{sel_title}** の管理パスワードを入力")
            input_pw = st.text_input("パスワード", type="password")
            if st.form_submit_button("管理者ログイン"):
                if input_pw == target_ev["password"]:
                    st.session_state[auth_key] = True
                    st.rerun()
                else: st.error("パスワードが正しくありません")
        st.stop()

    # 4. ログイン後のURL発行とメイン機能
    st.success(f"✅ 「{sel_title}」管理モードでログイン中")
    
    # 🔗 URL発行機能
    # 現在のURLを取得してパラメータを付与 (デプロイ環境で自動動作)
    base_url = "https://your-app-url.streamlit.app" # 実際の名前に書き換えてください
    target_url = f"{base_url}/?event_id={ev_id}"
    st.info(f"📢 **参加者に送る専用URL:**\n`{target_url}`")
    
    t1, t2, t3, t4 = st.tabs(["📅 日程・時間設定", "📊 回答状況", "🍴 会場決定", "❌ イベント終了・削除"])

    with t1:
        st.subheader("候補日時の追加")
        c1, c2 = st.columns(2)
        d = c1.date_input("日付")
        tm = c2.time_input("開始時間", value=datetime.strptime("18:30", "%H:%M").time())
        if st.button("この日時を追加"):
            dt_str = f"{d.strftime('%m/%d')}({['月','火','水','木','金','土','日'][d.weekday()]}) {tm.strftime('%H:%M')}～"
            with sqlite3.connect(DB_FILE) as conn:
                conn.cursor().execute("INSERT INTO dates (event_id, dt_text) VALUES (?, ?)", (int(ev_id), dt_str))
            st.rerun()

    with t2:
        df_res = get_responses(ev_id)
        if not df_res.empty:
            st.dataframe(df_res, use_container_width=True)
            st.download_button("集計CSVダウンロード", df_res.to_csv(index=False).encode('utf-8-sig'), f"{sel_title}.csv")

    with t3:
        st.subheader("お店の検索")
        with sqlite3.connect(DB_FILE) as conn:
            dates = pd.read_sql(f"SELECT dt_text FROM dates WHERE event_id={ev_id}", conn)["dt_text"].tolist()
        
        if not dates: st.warning("日程を登録してください")
        else:
            c_d, c_a, c_b = st.columns([2, 2, 1])
            sel_date = c_d.selectbox("決定日", dates)
            area = c_a.text_input("エリア（駅名など）", "")
            bud = c_b.selectbox("予算", list(BUDGET_MAP.keys()))
            
            if st.button("検索"):
                if not area: st.warning("エリアを入力してください")
                else:
                    params = {"key": API_KEY, "keyword": area, "budget": BUDGET_MAP[bud], "count": 10, "format": "json"}
                    res = requests.get("http://webservice.recruit.co.jp/hotpepper/gourmet/v1/", params=params)
                    st.session_state.shop_results = res.json().get('results', {}).get('shop', [])

            if "shop_results" in st.session_state:
                for s in st.session_state.shop_results:
                    with st.container(border=True):
                        col_img, col_txt = st.columns([1, 2])
                        with col_img: st.image(s['photo']['pc']['l'])
                        with col_txt:
                            st.subheader(s['name'])
                            st.write(f"💰 {s['budget']['name']} / 🚬 {s['non_smoking']}")
                            g_url = f"https://www.google.com/maps/search/?api=1&query={urllib.parse.quote(s['name'] + ' ' + s['address'])}"
                            if st.button(f"「{s['name']}」に決定", key=s['id']):
                                st.session_state.final_msg = f"【懇親会のお知らせ】\n\n日時：{sel_date}\n会場：{s['name']}\n地図：{g_url}"
                                st.rerun()

    with t4:
        if st.button("このイベントの全データを削除する", type="primary"):
            with sqlite3.connect(DB_FILE) as conn:
                c = conn.cursor()
                c.execute("DELETE FROM events WHERE id=?", (int(ev_id),))
                c.execute("DELETE FROM dates WHERE event_id=?", (int(ev_id),))
                c.execute("DELETE FROM responses WHERE event_id=?", (int(ev_id),))
            st.session_state[auth_key] = False
            st.rerun()

# --- 参加者画面 ---
else:
    st.title("🤝 懇親会アンケート")
    evs = get_events()
    
    # URLパラメータからの自動選択
    current_ev_id = None
    if q_ev_id:
        try:
            current_ev_id = int(q_ev_id)
            target = evs[evs["id"] == current_ev_id]
            if not target.empty:
                st.info(f"イベント：**{target.iloc[0]['title']}**")
            else: current_ev_id = None
        except: current_ev_id = None

    if not current_ev_id:
        if evs.empty: st.info("現在募集中のイベントはありません。")
        else:
            sel_ev_title = st.selectbox("回答するイベントを選択してください", evs["title"])
            current_ev_id = evs[evs["title"] == sel_ev_title].iloc[0]["id"]

    if current_ev_id:
        with sqlite3.connect(DB_FILE) as conn:
            d_list = pd.read_sql(f"SELECT dt_text FROM dates WHERE event_id={current_ev_id}", conn)["dt_text"].tolist()
        
        if d_list:
            with st.form("ans"):
                n = st.text_input("お名前")
                dis = st.text_input("苦手なもの")
                ans = {d: st.radio(d, ["○", "△", "×"], horizontal=True) for d in d_list}
                if st.form_submit_button("回答を送信"):
                    if n:
                        with sqlite3.connect(DB_FILE) as conn:
                            conn.cursor().execute("INSERT INTO responses (event_id, name, ans, dislikes) VALUES (?, ?, ?, ?)", 
                                                 (int(current_ev_id), n, json.dumps(ans, ensure_ascii=False), dis))
                        st.success("送信完了しました！")
                        st.rerun()
            st.dataframe(get_responses(current_ev_id), use_container_width=True, hide_index=True)
