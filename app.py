import streamlit as st
import pandas as pd
import requests
import sqlite3
import json
import os
from datetime import datetime

# --- 基本設定 ---
st.set_page_config(page_title="懇親会調整くん", page_icon="🤝", layout="wide")

# Secretsの取得チェック
API_KEY = st.secrets.get("HOTPEPPER_API_KEY", "")
ADMIN_USER = "admin"
ADMIN_PASS = "noukai2026"
DB_FILE = "konshinkai_data.db"

# --- DB操作 ---
def init_db():
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute('CREATE TABLE IF NOT EXISTS events (id INTEGER PRIMARY KEY, dates TEXT)')
        c.execute('CREATE TABLE IF NOT EXISTS responses (id INTEGER PRIMARY KEY, name TEXT, answers TEXT)')
        conn.commit()

def load_data():
    if not os.path.exists(DB_FILE): return [], pd.DataFrame(columns=["名前"])
    with sqlite3.connect(DB_FILE) as conn:
        event_df = pd.read_sql("SELECT * FROM events", conn)
        resp_df = pd.read_sql("SELECT * FROM responses", conn)
    dates = event_df["dates"].iloc[0].split(",") if not event_df.empty else []
    rows = []
    for _, row in resp_df.iterrows():
        ans = json.loads(row["answers"])
        ans["名前"] = row["name"]
        rows.append(ans)
    df = pd.DataFrame(rows) if rows else pd.DataFrame(columns=["名前"] + dates)
    return dates, df

init_db()

# --- サイドバー ---
mode = st.sidebar.radio("モード切替", ["参加者画面", "管理者画面"])

if mode == "管理者画面":
    st.title("⚙️ 管理者パネル")
    if 'logged_in' not in st.session_state: st.session_state.logged_in = False
    if not st.session_state.logged_in:
        with st.form("login"):
            u, p = st.text_input("ID"), st.text_input("PASS", type="password")
            if st.form_submit_button("ログイン") and u == ADMIN_USER and p == ADMIN_PASS:
                st.session_state.logged_in = True
                st.rerun()
        st.stop()

    saved_dates, resp_table = load_data()
    t1, t2 = st.tabs(["日程設定", "会場選び"])

    with t1:
        st.subheader("候補日設定")
        c1, c2 = st.columns(2)
        d = c1.date_input("日付")
        t = c2.time_input("時間")
        if st.button("追加"):
            dt_str = f"{d.strftime('%m/%d')}({['月','火','水','木','金','土','日'][d.weekday()]}) {t.strftime('%H:%M')}～"
            with sqlite3.connect(DB_FILE) as conn:
                conn.cursor().execute("DELETE FROM events")
                conn.cursor().execute("INSERT INTO events (dates) VALUES (?)", (",".join(saved_dates + [dt_str]),))
            st.rerun()
        if st.button("全リセット"):
            if os.path.exists(DB_FILE): os.remove(DB_FILE)
            st.rerun()
        st.dataframe(resp_table)

    with t2:
        st.subheader("会場検索")
        area = st.text_input("検索エリア", value="所沢")
        
        if st.button("会場を検索する"):
            if not API_KEY:
                st.error("❌ APIキーが設定されていません。StreamlitのSecretsを確認してください。")
            else:
                url = "http://webservice.recruit.co.jp/hotpepper/gourmet/v1/"
                # 検索条件を少し緩めてヒットしやすくします
                params = {
                    "key": API_KEY,
                    "keyword": area, 
                    "count": 5,
                    "format": "json"
                }
                
                try:
                    res = requests.get(url, params=params)
                    data = res.json()
                    
                    # デバッグ情報の表示（エラー時のみ役立つ）
                    if "error" in data.get("results", {}):
                        st.error(f"APIエラーが発生しました: {data['results']['error'][0]['message']}")
                    
                    st.session_state.shops = data.get('results', {}).get('shop', [])
                    
                    if not st.session_state.shops:
                        st.warning(f"「{area}」で見つかりませんでした。キーワードを変えてみてください。")
                
                except Exception as e:
                    st.error(f"通信エラーが発生しました: {e}")

        if "shops" in st.session_state:
            for s in st.session_state.shops:
                with st.container(border=True):
                    col_img, col_txt = st.columns([1, 2])
                    with col_img: st.image(s['photo']['pc']['l'])
                    with col_txt:
                        st.subheader(s['name'])
                        st.write(f"💰 {s['budget']['name']} / 📍 {s['mobile_access']}")
                        st.write(f"🔗 [詳細]({s['urls']['pc']})")
                        if st.button(f"{s['name']}に決定", key=s['id']):
                            st.session_state.final_msg = f"【懇親会のお知らせ】\n日時：未定\n場所：{s['name']}\n地図：{s['urls']['pc']}"
            
        if "final_msg" in st.session_state:
            st.text_area("案内文", value=st.session_state.final_msg, height=150)

else:
    st.title("🤝 懇親会アンケート")
    sd, _ = load_data()
    if not sd: st.info("準備中")
    else:
        with st.form("f"):
            n = st.text_input("名前")
            ans = {d: st.radio(d, ["○","△","×"], horizontal=True) for d in sd}
            if st.form_submit_button("送信") and n:
                with sqlite3.connect(DB_FILE) as conn:
                    conn.cursor().execute("INSERT INTO responses (name, answers) VALUES (?, ?)", (n, json.dumps(ans)))
                st.success("保存完了")
