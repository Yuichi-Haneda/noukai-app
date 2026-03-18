import streamlit as st
import pandas as pd
import requests
import sqlite3
import json
from datetime import datetime

# --- 設定 ---
st.set_page_config(page_title="納会調整くん Pro DB版", layout="wide")
API_KEY = st.secrets.get("HOTPEPPER_API_KEY", "")
ADMIN_USER = "admin"
ADMIN_PASS = "noukai2026"
DB_FILE = "noukai_data.db"

# --- DB操作関数 (SQLite) ---
def init_db():
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute('CREATE TABLE IF NOT EXISTS events (id INTEGER PRIMARY KEY, dates TEXT)')
        c.execute('CREATE TABLE IF NOT EXISTS responses (id INTEGER PRIMARY KEY, name TEXT, answers TEXT)')
        conn.commit()

def save_event_config(dates):
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("DELETE FROM events")
        c.execute("INSERT INTO events (dates) VALUES (?)", (",".join(dates),))
        c.execute("DELETE FROM responses")
        conn.commit()

def save_response(name, answers_dict):
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("INSERT INTO responses (name, answers) VALUES (?, ?)", (name, json.dumps(answers_dict, ensure_ascii=False)))
        conn.commit()

def load_data():
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

# --- アプリ本体 ---
mode = st.sidebar.radio("表示切替", ["参加者画面", "管理者画面"])

if mode == "管理者画面":
    st.title("🔐 管理者パネル")
    if 'logged_in' not in st.session_state: st.session_state.logged_in = False
    if not st.session_state.logged_in:
        with st.form("login"):
            u, p = st.text_input("ID"), st.text_input("PASS", type="password")
            if st.form_submit_button("ログイン") and u == ADMIN_USER and p == ADMIN_PASS:
                st.session_state.logged_in = True
                st.rerun()
        st.stop()

    saved_dates, resp_table = load_data()
    tab1, tab2 = st.tabs(["🗓 日程設定・回答確認", "🍺 お店選び・案内作成"])

    with tab1:
        st.subheader("1. 候補日時の追加")
        col1, col2 = st.columns(2)
        d = col1.date_input("日付")
        t = col2.time_input("時間", value=datetime.strptime("18:30", "%H:%M").time())
        if st.button("この日時を候補に追加"):
            dt_str = f"{d.strftime('%m/%d')}({['月','火','水','木','金','土','日'][d.weekday()]}) {t.strftime('%H:%M')}～"
            save_event_config(saved_dates + [dt_str] if dt_str not in saved_dates else saved_dates)
            st.rerun()
        if st.button("全データをリセット", type="primary"):
            if os.path.exists(DB_FILE): os.remove(DB_FILE)
            st.rerun()
        st.divider()
        st.subheader("📊 回答状況")
        st.dataframe(resp_table, use_container_width=True)

    with tab2:
        if not saved_dates: st.warning("日程を先に設定してください")
        else:
            col_a, col_b = st.columns([1, 1])
            selected_date = col_a.selectbox("決定日", saved_dates)
            area = col_b.text_input("エリア (例: 小手指, 所沢)", value="所沢")
            
            if st.button("おすすめのお店を検索", use_container_width=True):
                url = "http://webservice.recruit.co.jp/hotpepper/gourmet/v1/"
                res = requests.get(url, params={"key":API_KEY, "keyword":f"{area} 宴会 個室", "count":5, "format":"json", "order":4})
                st.session_state.shops = res.json().get('results', {}).get('shop', [])

            if "shops" in st.session_state:
                for s in st.session_state.shops:
                    # お店情報のカード表示
                    with st.container(border=True):
                        c1, c2 = st.columns([1, 2])
                        with c1:
                            st.image(s['photo']['pc']['l'], use_container_width=True)
                        with c2:
                            st.subheader(s['name'])
                            st.caption(f"📣 {s['catch']}")
                            
                            # 詳細情報をアイコン付きで並べる
                            info_col1, info_col2 = st.columns(2)
                            info_col1.write(f"📍 **アクセス:** {s['mobile_access']}")
                            info_col1.write(f"💰 **予算:** {s['budget']['name']}")
                            info_col2.write(f"👥 **キャパ:** {s['capacity']}名")
                            info_col2.write(f"🚭 **禁煙喫煙:** {s['non_smoking']}")
                            
                            st.write(f"📝 **設備:** 個室:{s['private_room']} / 掘りごたつ:{s['horigotatsu']}")
                            st.write(f"🔗 [ホットペッパー詳細ページ]({s['urls']['pc']})")
                            
                            if st.button(f"このお店（{s['name']}）で確定する", key=s['id']):
                                st.session_state.final_msg = f"【納会開催のお知らせ】\n\n日時の調整が完了しました！\n\n■日時：{selected_date}\n■場所：{s['name']}\n■住所：{s['address']}\n■地図：{s['urls']['pc']}\n■予算：{s['budget']['name']}\n\nご参加お待ちしております！"
                                st.success(f"「{s['name']}」に決定しました！")
                
            if "final_msg" in st.session_state:
                st.divider()
                st.subheader("📝 そのまま送れる案内文")
                st.text_area("Slackやメールにコピー", value=st.session_state.final_msg, height=250)

else:
    st.title("🗓 納会日程アンケート")
    saved_dates, _ = load_data()
    if not saved_dates:
        st.info("幹事が日程を調整中です。公開まで少々お待ちください。")
    else:
        with st.form("user_form"):
            name = st.text_input("お名前")
            st.write("参加可能な日時にチェックを入れてください。")
            ans = {d: st.radio(d, ["○ (参加)", "△ (未定)", "× (不可)"], horizontal=True) for d in saved_dates}
            if st.form_submit_button("回答を送信") and name:
                save_response(name, ans)
                st.success("回答を保存しました。ご協力ありがとうございます！")
