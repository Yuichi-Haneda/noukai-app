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
DB_FILE = "multi_event_v4.db"

# サイトオーナー用パスワード（全イベント管理用）
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

# --- UI制御 ---
st.sidebar.title("🤝 懇親会調整ツール")
mode = st.sidebar.radio("モード切替", ["参加者画面", "管理者画面", "サイトオーナー画面"])

# URLパラメータ取得
params = st.query_params
query_ev_id = params.get("event_id")

# --- サイトオーナー画面 ---
if mode == "サイトオーナー画面":
    st.title("👑 全イベント管理（サイトオーナー）")
    pw = st.text_input("オーナーパスワード", type="password")
    if pw == OWNER_PASS:
        evs = get_events()
        for _, row in evs.iterrows():
            col_a, col_b = st.columns([4, 1])
            col_a.write(f"ID: {row['id']} | **{row['title']}**")
            if col_b.button("完全削除", key=f"owner_del_{row['id']}"):
                with sqlite3.connect(DB_FILE) as conn:
                    c = conn.cursor()
                    c.execute("DELETE FROM events WHERE id=?", (row['id'],))
                    c.execute("DELETE FROM dates WHERE event_id=?", (row['id'],))
                    c.execute("DELETE FROM responses WHERE event_id=?", (row['id'],))
                st.rerun()
    elif pw: st.error("パスワードが違います")

# --- 管理者画面 ---
elif mode == "管理者画面":
    st.title("⚙️ イベント管理者パネル")
    
    with st.expander("➕ 新規イベント作成"):
        with st.form("create_ev"):
            new_title = st.text_input("イベント名")
            new_pass = st.text_input("管理用パスワード", type="password")
            if st.form_submit_button("作成"):
                if new_title and new_pass:
                    with sqlite3.connect(DB_FILE) as conn:
                        conn.cursor().execute("INSERT INTO events (title, password) VALUES (?, ?)", (new_title, new_pass))
                    st.success("作成しました。")
                    st.rerun()

    event_list = get_events()
    if event_list.empty: st.stop()

    sel_title = st.selectbox("管理するイベントを選択", event_list["title"])
    target_ev = event_list[event_list["title"] == sel_title].iloc[0]
    ev_id = target_ev["id"]

    # ログイン認証
    auth_key = f"auth_{ev_id}"
    if auth_key not in st.session_state: st.session_state[auth_key] = False
    if not st.session_state[auth_key]:
        if st.text_input("パスワード", type="password", key=f"pw_{ev_id}") == target_ev["password"]:
            if st.button("ログイン"):
                st.session_state[auth_key] = True
                st.rerun()
        st.stop()

    t1, t2, t3, t4 = st.tabs(["🗓 日程設定", "📊 回答確認", "🍺 会場検索", "🗑 イベント削除"])

    with t1:
        st.subheader("日時の追加")
        c1, c2 = st.columns(2)
        d = c1.date_input("日付")
        t = c2.time_input("時間", value=datetime.strptime("18:30", "%H:%M").time())
        if st.button("追加"):
            dt_str = f"{d.strftime('%m/%d')}({['月','火','水','木','金','土','日'][d.weekday()]}) {t.strftime('%H:%M')}～"
            with sqlite3.connect(DB_FILE) as conn:
                conn.cursor().execute("INSERT INTO dates (event_id, dt_text) VALUES (?, ?)", (int(ev_id), dt_str))
            st.rerun()

    with t2:
        df_res = get_responses(ev_id)
        if not df_res.empty:
            st.dataframe(df_res, use_container_width=True)
            st.download_button("CSV保存", df_res.to_csv(index=False).encode('utf-8-sig'), f"{sel_title}.csv")

    with t3:
        st.subheader("リッチ会場検索")
        with sqlite3.connect(DB_FILE) as conn:
            saved_dates = pd.read_sql(f"SELECT dt_text FROM dates WHERE event_id={ev_id}", conn)["dt_text"].tolist()
        
        c_d, c_a, c_b = st.columns([2, 2, 1])
        sel_date = c_d.selectbox("決定日", saved_dates)
        area = c_a.text_input("検索エリア（駅名・住所など）", value="") # デフォルト空白
        bud = c_b.selectbox("予算", list(BUDGET_MAP.keys()))
        
        if st.button("この条件で検索"):
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
                        st.write(f"📢 **{s['catch']}**")
                        st.write(f"🍴 {s['genre']['name']} / 💰 {s['budget']['name']}")
                        
                        # リッチ情報の追加
                        st.caption(f"🚬 禁煙・喫煙: {s['non_smoking']} / 💳 カード: {s['card']} / 🅿️ 駐車場: {s['parking']}")
                        
                        g_url = f"https://www.google.com/maps/search/?api=1&query={urllib.parse.quote(s['name'] + ' ' + s['address'])}"
                        st.write(f"🗺️ [Googleマップ]({g_url}) / 🔗 [ホットペッパー]({s['urls']['pc']})")
                        
                        if st.button(f"「{s['name']}」で決定！", key=f"sel_{s['id']}"):
                            st.session_state.final_msg = f"【懇親会のお知らせ】\n\n日時：{sel_date}\n会場：{s['name']}\n場所：{s['address']}\n地図：{g_url}\n詳細：{s['urls']['pc']}\n\nご参加お待ちしております！"
                            st.rerun()

            if "final_msg" in st.session_state:
                st.text_area("案内文（コピー用）", value=st.session_state.final_msg, height=200)

    with t4:
        st.subheader("イベントの削除")
        st.warning("この操作は取り消せません。このイベントに関する全ての日程・回答データが消去されます。")
        if st.button("このイベントを今すぐ削除する", type="primary"):
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
    current_ev_id = None
    if query_ev_id:
        try:
            current_ev_id = int(query_ev_id[0])
            target_row = evs[evs["id"] == current_ev_id]
            if not target_row.empty: st.info(f"イベント：**{target_row.iloc[0]['title']}**")
            else: current_ev_id = None
        except: current_ev_id = None

    if not current_ev_id:
        if evs.empty: st.stop()
        sel_ev_title = st.selectbox("回答するイベントを選択", evs["title"])
        current_ev_id = evs[evs["title"] == sel_ev_title].iloc[0]["id"]

    with sqlite3.connect(DB_FILE) as conn:
        d_list = pd.read_sql(f"SELECT dt_text FROM dates WHERE event_id={current_ev_id}", conn)["dt_text"].tolist()

    if d_list:
        with st.form("ans"):
            n = st.text_input("お名前")
            dis = st.text_input("苦手なもの（任意）")
            ans = {d: st.radio(d, ["○", "△", "×"], horizontal=True) for d in d_list}
            if st.form_submit_button("回答を送信"):
                if n:
                    with sqlite3.connect(DB_FILE) as conn:
                        conn.cursor().execute("INSERT INTO responses (event_id, name, ans, dislikes) VALUES (?, ?, ?, ?)", 
                                             (int(current_ev_id), n, json.dumps(ans, ensure_ascii=False), dis))
                    st.success("送信完了！")
                    st.rerun()
        st.dataframe(get_responses(current_ev_id), use_container_width=True, hide_index=True)
