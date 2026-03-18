import streamlit as st
import pandas as pd
import requests
import sqlite3
import json
import os
from datetime import datetime

# --- 基本設定 ---
st.set_page_config(page_title="懇親会日程・会場調整くん", page_icon="🤝", layout="wide")
API_KEY = st.secrets.get("HOTPEPPER_API_KEY", "")
ADMIN_USER = "admin"
ADMIN_PASS = "noukai2026"
DB_FILE = "konshinkai_data.db"

# --- DB操作関数 ---
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

# --- メインロジック ---
st.sidebar.title("🤝 懇親会調整ツール")
mode = st.sidebar.radio("モードを切り替える", ["参加者アンケート画面", "管理者設定画面"])

if mode == "管理者設定画面":
    st.title("⚙️ 管理者専用パネル")
    if 'logged_in' not in st.session_state: st.session_state.logged_in = False
    if not st.session_state.logged_in:
        with st.form("login"):
            u, p = st.text_input("管理者ID"), st.text_input("パスワード", type="password")
            if st.form_submit_button("ログイン"):
                if u == ADMIN_USER and p == ADMIN_PASS:
                    st.session_state.logged_in = True
                    st.rerun()
                else: st.error("IDまたはパスワードが正しくありません")
        st.stop()

    saved_dates, resp_table = load_data()
    tab1, tab2 = st.tabs(["📅 日程の設定・回答確認", "🍴 会場選び・案内作成"])

    with tab1:
        st.subheader("1. 候補日時の登録")
        col1, col2 = st.columns(2)
        d = col1.date_input("候補日")
        t = col2.time_input("開始予定時間", value=datetime.strptime("18:30", "%H:%M").time())
        if st.button("この日時をリストに追加"):
            dt_str = f"{d.strftime('%m/%d')}({['月','火','水','木','金','土','日'][d.weekday()]}) {t.strftime('%H:%M')}～"
            save_event_config(saved_dates + [dt_str] if dt_str not in saved_dates else saved_dates)
            st.success(f"追加しました：{dt_str}")
            st.rerun()
        
        if st.button("全ての日程と回答をリセット", type="primary"):
            if os.path.exists(DB_FILE): os.remove(DB_FILE)
            st.rerun()
            
        st.divider()
        st.subheader("📊 参加希望の集計状況")
        st.dataframe(resp_table, use_container_width=True)

    with tab2:
        if not saved_dates: st.warning("先に日程を設定してください")
        else:
            st.subheader("2. 開催日時と会場の決定")
            c_a, c_b = st.columns([1, 1])
            selected_date = c_a.selectbox("最終決定した日時", saved_dates)
            area = c_b.text_input("会場検索エリア", value="所沢")
            
            if st.button("おすすめの会場を検索", use_container_width=True):
                url = "http://webservice.recruit.co.jp/hotpepper/gourmet/v1/"
                res = requests.get(url, params={"key":API_KEY, "keyword":f"{area} 懇親会 個室", "count":5, "format":"json", "order":4})
                st.session_state.shops = res.json().get('results', {}).get('shop', [])

            if "shops" in st.session_state:
                for s in st.session_state.shops:
                    with st.container(border=True):
                        c1, c2 = st.columns([1, 2])
                        with c1: st.image(s['photo']['pc']['l'], use_container_width=True)
                        with c2:
                            st.subheader(s['name'])
                            st.caption(f"✨ {s['catch']}")
                            i_col1, i_col2 = st.columns(2)
                            i_col1.write(f"💰 予算: {s['budget']['name']}")
                            i_col1.write(f"📍 アクセス: {s['mobile_access']}")
                            i_col2.write(f"👥 最大: {s['capacity']}名")
                            i_col2.write(f"🚬 禁煙喫煙: {s['non_smoking']}")
                            st.write(f"🔗 [お店の詳細(ホットペッパー)]({s['urls']['pc']})")
                            
                            if st.button(f"この会場に決定", key=f"sel_{s['id']}"):
                                st.session_state.final_msg = f"【親睦を深める懇親会のお知らせ】\n\n皆様お疲れ様です。検討の結果、以下の内容で決定いたしました！\n\n■日時：{selected_date}\n■場所：{s['name']}\n■住所：{s['address']}\n■地図：{s['urls']['pc']}\n■予算：{s['budget']['name']}\n\nぜひ奮ってご参加ください！"
                                st.success(f"「{s['name']}」で決定しました！下に案内文が表示されます。")
                
            if "final_msg" in st.session_state:
                st.divider()
                st.subheader("📢 送信用案内文")
                st.text_area("コピーして共有（Slack/Teams等）", value=st.session_state.final_msg, height=250)

else:
    st.title("🤝 懇親会 日程アンケート")
    saved_dates, _ = load_data()
    if not saved_dates:
        st.info("ただいま幹事が日程を調整中です。公開までもう少々お待ちください。")
    else:
        st.write("皆様のご都合の良い日時にチェックをお願いします。")
        with st.form("user_form"):
            name = st.text_input("お名前（フルネーム）")
            ans = {d: st.radio(d, ["○ (参加)", "△ (検討中)", "× (不参加)"], horizontal=True) for d in saved_dates}
            if st.form_submit_button("回答を送信"):
                if name:
                    save_response(name, ans)
                    st.success("回答を送信しました。ご協力ありがとうございます！")
                else: st.error("お名前を入力してください。")
