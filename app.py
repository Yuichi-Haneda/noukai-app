import streamlit as st
import pandas as pd
import requests
import sqlite3
import json
import os
import urllib.parse
from datetime import datetime

# --- 設定 ---
st.set_page_config(page_title="懇親会調整 Pro Max+", page_icon="🤝", layout="wide")
API_KEY = st.secrets.get("HOTPEPPER_API_KEY", "")
DB_FILE = "multi_event_food_data.db"

# 予算コード変換表
BUDGET_MAP = {"指定なし": "", "2001〜3000円": "B002", "3001〜4000円": "B003", "4001〜5000円": "B008", "5001〜7000円": "B004"}

# --- DB初期化 ---
def init_db():
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        # responsesテーブルに dislikes カラムを追加
        c.execute('CREATE TABLE IF NOT EXISTS events (id INTEGER PRIMARY KEY, title TEXT, password TEXT)')
        c.execute('CREATE TABLE IF NOT EXISTS dates (id INTEGER PRIMARY KEY, event_id INTEGER, dt_text TEXT)')
        c.execute('CREATE TABLE IF NOT EXISTS responses (id INTEGER PRIMARY KEY, event_id INTEGER, name TEXT, ans TEXT, dislikes TEXT)')
        conn.commit()

init_db()

# --- データ取得関数 ---
def get_events():
    with sqlite3.connect(DB_FILE) as conn:
        return pd.read_sql("SELECT * FROM events", conn)

def get_responses(ev_id):
    with sqlite3.connect(DB_FILE) as conn:
        resps = pd.read_sql(f"SELECT name, ans, dislikes FROM responses WHERE event_id={ev_id}", conn)
    if resps.empty: return pd.DataFrame()
    rows = []
    for _, r in resps.iterrows():
        d_row = json.loads(r["ans"])
        d_row["名前"] = r["name"]
        d_row["苦手・アレルギー"] = r["dislikes"]
        rows.append(d_row)
    df = pd.DataFrame(rows)
    cols = ["名前", "苦手・アレルギー"] + [c for c in df.columns if c not in ["名前", "苦手・アレルギー"]]
    return df[cols]

# --- メインUI ---
st.sidebar.title("🤝 懇親会調整ツール")
mode = st.sidebar.radio("モード切替", ["参加者画面", "管理者画面"])

if mode == "管理者画面":
    st.title("⚙️ 管理者パネル")
    
    # イベント作成
    with st.expander("➕ 新しいイベントを作成する"):
        with st.form("create_ev"):
            new_title = st.text_input("イベント名")
            new_pass = st.text_input("管理パスワード", type="password")
            if st.form_submit_button("作成"):
                if new_title and new_pass:
                    with sqlite3.connect(DB_FILE) as conn:
                        conn.cursor().execute("INSERT INTO events (title, password) VALUES (?, ?)", (new_title, new_pass))
                    st.success("作成しました！")
                    st.rerun()

    event_list = get_events()
    if event_list.empty: st.stop()

    sel_title = st.selectbox("管理するイベントを選択", event_list["title"])
    target_ev = event_list[event_list["title"] == sel_title].iloc[0]
    ev_id = target_ev["id"]
    
    # 認証
    auth_key = f"auth_{ev_id}"
    if auth_key not in st.session_state: st.session_state[auth_key] = False
    if not st.session_state[auth_key]:
        if st.text_input("パスワード", type="password") == target_ev["password"]:
            if st.button("ログイン"):
                st.session_state[auth_key] = True
                st.rerun()
        st.stop()

    t1, t2, t3 = st.tabs(["🗓 日程管理", "📊 回答・苦手確認", "🍺 会場検索"])

    with t1:
        st.subheader("候補日の追加")
        d = st.date_input("日付")
        if st.button("日程を追加"):
            dt_str = d.strftime('%m/%d')
            with sqlite3.connect(DB_FILE) as conn:
                conn.cursor().execute("INSERT INTO dates (event_id, dt_text) VALUES (?, ?)", (int(ev_id), dt_str))
            st.rerun()

    with t2:
        df_resp = get_responses(ev_id)
        if not df_resp.empty:
            st.dataframe(df_resp, use_container_width=True)
            # 苦手なものをリスト化
            dislike_list = [x for x in df_resp["苦手・アレルギー"].tolist() if x]
            if dislike_list:
                st.warning(f"⚠️ 参加者の苦手なもの: {', '.join(dislike_list)}")
                st.session_state.current_dislikes = dislike_list
        else: st.write("回答待ちです。")

    with t3:
        st.subheader("お店の検索（苦手フィルタ適用）")
        with sqlite3.connect(DB_FILE) as conn:
            saved_dates = pd.read_sql(f"SELECT dt_text FROM dates WHERE event_id={ev_id}", conn)["dt_text"].tolist()
        
        if not saved_dates: st.warning("日程を先に設定してください")
        else:
            c1, c2, c3 = st.columns([2, 1, 1])
            sel_date = c1.selectbox("開催日", saved_dates)
            area = c2.text_input("検索エリア", "所沢")
            budget = c3.selectbox("予算", list(BUDGET_MAP.keys()))
            
            # フィルタリング設定
            use_filter = st.checkbox("参加者の苦手なものを含む店を除外する", value=True)
            
            if st.button("お店を検索する", use_container_width=True):
                params = {"key": API_KEY, "keyword": area, "budget": BUDGET_MAP[budget], "count": 20, "format": "json"}
                res = requests.get("http://webservice.recruit.co.jp/hotpepper/gourmet/v1/", params=params)
                shops = res.json().get('results', {}).get('shop', [])
                
                # --- フィルタリングロジック ---
                filtered_shops = []
                dislikes = st.session_state.get('current_dislikes', [])
                
                for s in shops:
                    # 店名、キャッチコピー、料理ジャンルの中に苦手ワードがあるかチェック
                    shop_info_text = (s['name'] + s['catch'] + s['genre']['name'] + s['sub_genre']['name']).lower()
                    is_bad = False
                    if use_filter:
                        for word in dislikes:
                            if word.lower() in shop_info_text:
                                is_bad = True
                                break
                    if not is_bad:
                        filtered_shops.append(s)
                
                st.session_state.shop_results = filtered_shops[:5] # 上位5件表示
                st.success(f"{len(shops)}件中、条件に合う{len(filtered_shops)}件を表示しています。")

            if "shop_results" in st.session_state:
                for s in st.session_state.shop_results:
                    gmap_url = f"https://www.google.com/maps/search/?api=1&query={urllib.parse.quote(s['name'] + ' ' + s['address'])}"
                    with st.container(border=True):
                        c1, c2 = st.columns([1, 2])
                        with c1: st.image(s['photo']['pc']['l'])
                        with c2:
                            st.subheader(s['name'])
                            st.write(f"🍴 ジャンル: {s['genre']['name']} / 💰 {s['budget']['name']}")
                            st.write(f"🗺️ [Googleマップで開く]({gmap_url})")
                            if st.button(f"「{s['name']}」に決定！", key=f"btn_{s['id']}"):
                                st.session_state.final_msg = f"【懇親会のお知らせ】\n\n日時：{sel_date}\n場所：{s['name']}\n住所：{s['address']}\n地図：{gmap_url}\n予算：{s['budget']['name']}"
                                st.rerun()

            if "final_msg" in st.session_state:
                st.text_area("案内文", value=st.session_state.final_msg, height=200)

# --- 参加者画面 ---
else:
    st.title("🤝 懇親会アンケート")
    event_list = get_events()
    if event_list.empty: st.info("準備中")
    else:
        sel_ev = st.selectbox("イベントを選択", event_list["title"])
        ev_id = event_list[event_list["title"] == sel_ev]["id"].values[0]
        with sqlite3.connect(DB_FILE) as conn:
            d_list = pd.read_sql(f"SELECT dt_text FROM dates WHERE event_id={ev_id}", conn)["dt_text"].tolist()

        if d_list:
            with st.form("ans_form"):
                n = st.text_input("お名前")
                # 苦手なもの入力欄を追加
                dislikes = st.text_input("苦手な食べ物・アレルギー（任意）", placeholder="例：パクチー、生魚、ナッツ類など")
                st.divider()
                ans = {d: st.radio(d, ["○", "△", "×"], horizontal=True) for d in d_list}
                if st.form_submit_button("回答を送信"):
                    if n:
                        with sqlite3.connect(DB_FILE) as conn:
                            conn.cursor().execute("INSERT INTO responses (event_id, name, ans, dislikes) VALUES (?, ?, ?, ?)", 
                                                 (int(ev_id), n, json.dumps(ans, ensure_ascii=False), dislikes))
                        st.success("回答を送信しました！")
                        st.rerun()
            
            st.divider()
            st.subheader("📊 現在の回答状況")
            df_resp = get_responses(ev_id)
            if not df_resp.empty: st.dataframe(df_resp, use_container_width=True, hide_index=True)
