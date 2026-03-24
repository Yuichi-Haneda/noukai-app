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
DB_FILE = "multi_event_v3.db"

# サイトオーナー用パスワード（全イベント削除権限）
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

# --- データ取得・操作関数 ---
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

# --- サイドバー・ナビゲーション ---
st.sidebar.title("🤝 懇親会調整ツール")
mode = st.sidebar.radio("モード切替", ["参加者画面", "管理者画面", "サイトオーナー画面"])

# URLパラメータからイベントIDを取得 (?event_id=123)
params = st.query_params
query_ev_id = params.get("event_id")

# --- サイトオーナー画面 (全イベント管理) ---
if mode == "サイトオーナー画面":
    st.title("👑 サイトオーナー・コントロール")
    pw = st.text_input("オーナーパスワードを入力", type="password")
    if pw == OWNER_PASS:
        st.subheader("全イベント一覧・削除")
        evs = get_events()
        if evs.empty:
            st.info("現在作成されているイベントはありません。")
        else:
            for _, row in evs.iterrows():
                col_a, col_b = st.columns([4, 1])
                col_a.write(f"ID: {row['id']} | **{row['title']}**")
                if col_b.button("削除", key=f"del_ev_{row['id']}"):
                    with sqlite3.connect(DB_FILE) as conn:
                        c = conn.cursor()
                        c.execute("DELETE FROM events WHERE id=?", (row['id'],))
                        c.execute("DELETE FROM dates WHERE event_id=?", (row['id'],))
                        c.execute("DELETE FROM responses WHERE event_id=?", (row['id'],))
                    st.success(f"イベント {row['id']} を削除しました。")
                    st.rerun()
    elif pw: st.error("パスワードが違います")

# --- 管理者画面 ---
elif mode == "管理者画面":
    st.title("⚙️ イベント管理者パネル")
    
    with st.expander("➕ 新しい懇親会イベントを作成する"):
        with st.form("create_ev"):
            new_title = st.text_input("イベント名")
            new_pass = st.text_input("管理パスワード設定", type="password")
            if st.form_submit_button("作成"):
                if new_title and new_pass:
                    with sqlite3.connect(DB_FILE) as conn:
                        conn.cursor().execute("INSERT INTO events (title, password) VALUES (?, ?)", (new_title, new_pass))
                    st.success("作成しました！下のリストから選んでください。")
                    st.rerun()

    event_list = get_events()
    if event_list.empty: st.stop()

    sel_title = st.selectbox("管理するイベントを選択", event_list["title"])
    target_ev = event_list[event_list["title"] == sel_title].iloc[0]
    ev_id = target_ev["id"]

    # ログインチェック
    auth_key = f"auth_{ev_id}"
    if auth_key not in st.session_state: st.session_state[auth_key] = False
    if not st.session_state[auth_key]:
        input_p = st.text_input(f"「{sel_title}」のパスワード", type="password")
        if st.button("ログイン"):
            if input_p == target_ev["password"]:
                st.session_state[auth_key] = True
                st.rerun()
            else: st.error("不一致")
        st.stop()

    # 専用URLの案内
    base_url = "https://your-app-name.streamlit.app/" # デプロイ後のURLに変更してください
    share_url = f"{base_url}?event_id={ev_id}"
    st.info(f"🔗 **このイベント専用の参加者用URL:** \n`{share_url}`")

    t1, t2, t3 = st.tabs(["🗓 日程・時刻設定", "📊 回答確認", "🍺 会場決定"])

    with t1:
        st.subheader("候補日時の追加")
        c1, c2 = st.columns(2)
        d = c1.date_input("日付")
        t = c2.time_input("開始時間", value=datetime.strptime("18:30", "%H:%M").time())
        if st.button("この日時をリストに追加"):
            dt_str = f"{d.strftime('%m/%d')}({['月','火','水','木','金','土','日'][d.weekday()]}) {t.strftime('%H:%M')}～"
            with sqlite3.connect(DB_FILE) as conn:
                conn.cursor().execute("INSERT INTO dates (event_id, dt_text) VALUES (?, ?)", (int(ev_id), dt_str))
            st.rerun()
        
        # 登録済み日程の個別削除
        with sqlite3.connect(DB_FILE) as conn:
            d_rows = pd.read_sql(f"SELECT * FROM dates WHERE event_id={ev_id}", conn)
        for _, dr in d_rows.iterrows():
            col_d1, col_d2 = st.columns([4, 1])
            col_d1.write(dr["dt_text"])
            if col_d2.button("削除", key=f"date_{dr['id']}"):
                with sqlite3.connect(DB_FILE) as conn:
                    conn.cursor().execute("DELETE FROM dates WHERE id=?", (dr['id'],))
                st.rerun()

    with t2:
        df_res = get_responses(ev_id)
        if not df_res.empty:
            st.dataframe(df_res, use_container_width=True)
            st.download_button("CSVダウンロード", df_res.to_csv(index=False).encode('utf-8-sig'), f"{sel_title}.csv")
            dislikes = [x for x in df_res["苦手・アレルギー"].tolist() if x]
            if dislikes: st.warning(f"⚠️ 苦手なもの: {', '.join(dislikes)}")
            st.session_state.current_dislikes = dislikes

    with t3:
        # (会場検索ロジック - 前回と同様)
        st.subheader("お店の決定")
        with sqlite3.connect(DB_FILE) as conn:
            saved_dates = pd.read_sql(f"SELECT dt_text FROM dates WHERE event_id={ev_id}", conn)["dt_text"].tolist()
        
        if not saved_dates: st.warning("日程を登録してください")
        else:
            c_d, c_a, c_b = st.columns([2, 2, 1])
            sel_date = c_d.selectbox("決定日", saved_dates)
            area = c_a.text_input("検索エリア", "所沢")
            bud = c_b.selectbox("予算", list(BUDGET_MAP.keys()))
            
            if st.button("検索実行"):
                params = {"key": API_KEY, "keyword": area, "budget": BUDGET_MAP[bud], "count": 10, "format": "json"}
                res = requests.get("http://webservice.recruit.co.jp/hotpepper/gourmet/v1/", params=params)
                st.session_state.shop_results = res.json().get('results', {}).get('shop', [])

            if "shop_results" in st.session_state:
                for s in st.session_state.shop_results:
                    # フィルタリング（簡易版）
                    dis_list = st.session_state.get('current_dislikes', [])
                    if any(word in (s['name']+s['catch']+s['genre']['name']) for word in dis_list):
                        continue
                    
                    with st.container(border=True):
                        st.write(f"**{s['name']}**")
                        if st.button(f"「{s['name']}」に決定", key=s['id']):
                            g_url = f"https://www.google.com/maps/search/?api=1&query={urllib.parse.quote(s['name'] + ' ' + s['address'])}"
                            st.session_state.final_msg = f"【懇親会決定】\n日時：{sel_date}\n会場：{s['name']}\n地図：{g_url}"
                            st.rerun()
            
            if "final_msg" in st.session_state:
                st.text_area("案内文", value=st.session_state.final_msg, height=150)

# --- 参加者画面 ---
else:
    st.title("🤝 懇親会アンケート")
    evs = get_events()
    
    # URLパラメータからイベントを特定、なければセレクトボックス
    current_ev_id = None
    if query_ev_id:
        current_ev_id = int(query_ev_id[0])
        target_ev_row = evs[evs["id"] == current_ev_id]
        if not target_ev_row.empty:
            st.success(f"イベント：**{target_ev_row.iloc[0]['title']}** の回答画面です")
        else:
            st.error("指定されたイベントが見つかりません。")
            current_ev_id = None

    if not current_ev_id:
        if evs.empty: st.stop()
        sel_ev_title = st.selectbox("回答するイベントを選択してください", evs["title"])
        current_ev_id = evs[evs["title"] == sel_ev_title].iloc[0]["id"]

    # 日程の取得と表示
    with sqlite3.connect(DB_FILE) as conn:
        d_list = pd.read_sql(f"SELECT dt_text FROM dates WHERE event_id={current_ev_id}", conn)["dt_text"].tolist()

    if d_list:
        with st.form("ans"):
            name = st.text_input("お名前")
            dis = st.text_input("苦手なもの")
            ans = {d: st.radio(d, ["○", "△", "×"], horizontal=True) for d in d_list}
            if st.form_submit_button("回答送信"):
                if name:
                    with sqlite3.connect(DB_FILE) as conn:
                        conn.cursor().execute("INSERT INTO responses (event_id, name, ans, dislikes) VALUES (?, ?, ?, ?)", 
                                             (int(current_ev_id), name, json.dumps(ans, ensure_ascii=False), dis))
                    st.success("送信完了！")
                    st.rerun()
    
        st.subheader("回答状況")
        st.dataframe(get_responses(current_ev_id), use_container_width=True, hide_index=True)
