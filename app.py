import streamlit as st
import pandas as pd
import requests
import sqlite3
import json
import os
from datetime import datetime

# --- 基本設定 ---
st.set_page_config(page_title="懇親会調整くん", page_icon="🤝", layout="wide")
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
    t1, t2 = st.tabs(["🗓 日程設定・回答確認", "🍺 会場選び・案内作成"])

    with t1:
        st.subheader("1. 候補日時の追加")
        col1, col2 = st.columns(2)
        d = col1.date_input("日付")
        t = col2.time_input("時間", value=datetime.strptime("18:30", "%H:%M").time())
        if st.button("この日時をリストに追加"):
            dt_str = f"{d.strftime('%m/%d')}({['月','火','水','木','金','土','日'][d.weekday()]}) {t.strftime('%H:%M')}～"
            new_list = saved_dates + [dt_str] if dt_str not in saved_dates else saved_dates
            with sqlite3.connect(DB_FILE) as conn:
                conn.cursor().execute("DELETE FROM events")
                conn.cursor().execute("INSERT INTO events (dates) VALUES (?)", (",".join(new_list),))
            st.success(f"追加: {dt_str}")
            st.rerun()
        
        if st.button("全リセット", type="primary"):
            if os.path.exists(DB_FILE): os.remove(DB_FILE)
            st.rerun()
            
        st.divider()
        st.subheader("📊 回答状況")
        st.dataframe(resp_table, use_container_width=True)

    with t2:
        if not saved_dates:
            st.warning("先に日程を設定してください")
        else:
            st.subheader("2. 開催日と会場の決定")
            c_a, c_b = st.columns(2)
            # 決定した日程を選択（ここで選んだものが案内文に入ります）
            selected_date = c_a.selectbox("最終決定日を選択", saved_dates)
            area = c_b.text_input("検索エリア", value="所沢")
            
            if st.button("会場を検索する", use_container_width=True):
                url = "http://webservice.recruit.co.jp/hotpepper/gourmet/v1/"
                params = {"key": API_KEY, "keyword": area, "count": 5, "format": "json"}
                res = requests.get(url, params=params)
                st.session_state.shops = res.json().get('results', {}).get('shop', [])

            if "shops" in st.session_state:
                for s in st.session_state.shops:
                    with st.container(border=True):
                        col_img, col_txt = st.columns([1, 2])
                        with col_img: st.image(s['photo']['pc']['l'])
                        with col_txt:
                            st.subheader(s['name'])
                            st.write(f"💰 予算: {s['budget']['name']} / 📍 {s['mobile_access']}")
                            st.write(f"🔗 [詳細を表示]({s['urls']['pc']})")
                            
                            # このボタンを押すと、上の selected_date と組み合わせて案内文を作る
                            if st.button(f"このお店（{s['name']}）で決定！", key=s['id']):
                                st.session_state.final_msg = f"""【懇親会開催のお知らせ】

皆様お疲れ様です。
日程調整へのご協力ありがとうございました。
検討の結果、以下の内容で決定いたしました！

■日時：{selected_date}
■場所：{s['name']}
■住所：{s['address']}
■地図：{s['urls']['pc']}
■予算：{s['budget']['name']}

当日のご参加をお待ちしております！"""
                                st.success(f"「{s['name']}」に決定しました。下に案内文が表示されます。")
                                st.rerun()

            if "final_msg" in st.session_state:
                st.divider()
                st.subheader("📝 そのまま送れる案内文")
                st.text_area("コピーしてSlackやTeamsに貼り付け", value=st.session_state.final_msg, height=280)

# --- 参加者画面 ---
else:
    st.title("🤝 懇親会 日程アンケート")
    sd, _ = load_data()
    if not sd:
        st.info("幹事が日程を調整中です。公開までお待ちください。")
    else:
        with st.form("user_form"):
            n = st.text_input("お名前（フルネーム）")
            ans = {d: st.radio(d, ["○ (参加)", "△ (未定)", "× (不可)"], horizontal=True) for d in sd}
            if st.form_submit_button("回答を送信"):
                if n:
                    with sqlite3.connect(DB_FILE) as conn:
                        conn.cursor().execute("INSERT INTO responses (name, answers) VALUES (?, ?)", (n, json.dumps(ans, ensure_ascii=False)))
                    st.success("回答を送信しました。ご協力ありがとうございます！")
                else:
                    st.error("お名前を入力してください")
