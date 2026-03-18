import streamlit as st
import pandas as pd
import requests
import sqlite3
from datetime import datetime
import os

# --- 設定 ---
st.set_page_config(page_title="納会調整くん Pro DB版", layout="wide")
API_KEY = st.secrets.get("HOTPEPPER_API_KEY", "")
ADMIN_USER = "admin"
ADMIN_PASS = "noukai2026"

# --- データベース準備 ---
DB_FILE = "noukai_data.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    # イベント情報テーブル
    c.execute('''CREATE TABLE IF NOT EXISTS events 
                 (id INTEGER PRIMARY KEY, dates TEXT, fixed_date TEXT, shop_json TEXT)''')
    # 参加者回答テーブル
    c.execute('''CREATE TABLE IF NOT EXISTS responses 
                 (id INTEGER PRIMARY KEY, name TEXT, answers TEXT)''')
    conn.commit()
    conn.close()

def save_event_config(dates):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("DELETE FROM events") # 常に1つのイベントとして上書き
    c.execute("INSERT INTO events (dates) VALUES (?)", (",".join(dates),))
    c.execute("DELETE FROM responses") # 日程が変わったら回答もリセット
    conn.commit()
    conn.close()

def save_response(name, answers_dict):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    import json
    c.execute("INSERT INTO responses (name, answers) VALUES (?, ?)", (name, json.dumps(answers_dict)))
    conn.commit()
    conn.close()

def load_data():
    conn = sqlite3.connect(DB_FILE)
    # イベント読み込み
    event_df = pd.read_sql("SELECT * FROM events", conn)
    # 回答読み込み
    resp_df = pd.read_sql("SELECT * FROM responses", conn)
    conn.close()
    
    dates = event_df["dates"].iloc[0].split(",") if not event_df.empty else []
    
    # 回答表を整形
    import json
    rows = []
    for _, row in resp_df.iterrows():
        ans = json.loads(row["answers"])
        ans["名前"] = row["name"]
        rows.append(ans)
    
    df = pd.DataFrame(rows) if rows else pd.DataFrame(columns=["名前"] + dates)
    return dates, df

# 起動時にDB初期化
init_db()

# --- アプリ本体 ---
mode = st.sidebar.radio("表示切替", ["参加者画面", "管理者画面"])

if mode == "管理者画面":
    st.title("🔐 管理者パネル (DB保存版)")
    if 'logged_in' not in st.session_state: st.session_state.logged_in = False
    if not st.session_state.logged_in:
        with st.form("login"):
            u, p = st.text_input("ID"), st.text_input("PASS", type="password")
            if st.form_submit_button("ログイン") and u == ADMIN_USER and p == ADMIN_PASS:
                st.session_state.logged_in = True
                st.rerun()
        st.stop()

    # DBから最新情報をロード
    saved_dates, resp_table = load_data()

    tab1, tab2 = st.tabs(["日程設定・回答確認", "お店選び・案内作成"])

    with tab1:
        st.subheader("1. 候補日時の追加")
        c1, c2 = st.columns(2)
        d = c1.date_input("日付")
        t = c2.time_input("時間", value=datetime.strptime("18:30", "%H:%M").time())
        
        if st.button("この日時をDBに保存"):
            dt_str = f"{d.strftime('%m/%d')}({['月','火','水','木','金','土','日'][d.weekday()]}) {t.strftime('%H:%M')}～"
            new_dates = saved_dates + [dt_str] if dt_str not in saved_dates else saved_dates
            save_event_config(new_dates)
            st.success("データベースに保存しました")
            st.rerun()

        if st.button("全データをリセット", type="primary"):
            conn = sqlite3.connect(DB_FILE)
            conn.cursor().execute("DROP TABLE IF EXISTS events")
            conn.cursor().execute("DROP TABLE IF EXISTS responses")
            conn.commit()
            conn.close()
            st.rerun()

        st.divider()
        st.subheader("📊 現在の回答状況 (リアルタイムDB参照)")
        st.dataframe(resp_table, use_container_width=True)

    with tab2:
        # (お店検索・案内文ロジックは前回同様)
        if not saved_dates: st.warning("日程を先に設定してください")
        else:
            selected_date = st.selectbox("決定日", saved_dates)
            area = st.text_input("検索エリア", value="所沢")
            if st.button("お店検索"):
                url = "http://webservice.recruit.co.jp/hotpepper/gourmet/v1/"
                res = requests.get(url, params={"key":API_KEY, "keyword":f"{area} 宴会", "count":3, "format":"json", "order":4})
                st.session_state.shops = res.json().get('results', {}).get('shop', [])

            if "shops" in st.session_state:
                for s in st.session_state.shops:
                    with st.container(border=True):
                        st.subheader(s['name'])
                        st.write(f"🔗 [詳細を表示]({s['urls']['pc']})")
                        if st.button(f"{s['name']}に決定", key=s['id']):
                            st.session_state.final_msg = f"【納会のお知らせ】\n日時：{selected_date}\n場所：{s['name']}\nURL：{s['urls']['pc']}"
            
            if "final_msg" in st.session_state:
                st.text_area("案内文", value=st.session_state.final_msg, height=150)

else:
    st.title("🗓 納会日程アンケート")
    saved_dates, _ = load_data()
    if not saved_dates:
        st.info("現在調整中です。")
    else:
        with st.form("user_form"):
            name = st.text_input("お名前")
            ans = {d: st.radio(d, ["○", "△", "×"], horizontal=True) for d in saved_dates}
            if st.form_submit_button("回答を送信") and name:
                save_response(name, ans)
                st.success("回答をデータベースに記録しました！")
