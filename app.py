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
DB_FILE = "multi_event_v6.db"
OWNER_PASS = st.secrets.get("OWNER_PASS", "owner2026") # Secrets管理を推奨
API_KEY = st.secrets.get("HOTPEPPER_API_KEY", "")
BUDGET_MAP = {
    "指定なし": "", "2001〜3000円": "B002", "3001〜4000円": "B003", 
    "4001〜5000円": "B008", "5001〜7000円": "B004"
}

# --- データベース共通関数 ---
def run_query(query, params=(), is_select=False):
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute(query, params)
        if is_select:
            return cursor.fetchall()
        conn.commit()

def init_db():
    run_query('CREATE TABLE IF NOT EXISTS events (id INTEGER PRIMARY KEY, title TEXT, password TEXT)')
    run_query('CREATE TABLE IF NOT EXISTS dates (id INTEGER PRIMARY KEY, event_id INTEGER, dt_text TEXT)')
    run_query('CREATE TABLE IF NOT EXISTS responses (id INTEGER PRIMARY KEY, event_id INTEGER, name TEXT, ans TEXT, dislikes TEXT)')

def delete_event_data(ev_id):
    """イベントに関連するすべてのデータを削除"""
    run_query("DELETE FROM events WHERE id=?", (ev_id,))
    run_query("DELETE FROM dates WHERE event_id=?", (ev_id,))
    run_query("DELETE FROM responses WHERE event_id=?", (ev_id,))

init_db()

# --- データ取得関数 ---
def get_events_df():
    with sqlite3.connect(DB_FILE) as conn:
        return pd.read_sql("SELECT * FROM events", conn)

def get_responses_df(ev_id):
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
        except json.JSONDecodeError:
            continue
    
    df = pd.DataFrame(rows)
    # カラム並び替え
    fixed_cols = ["名前", "苦手・アレルギー"]
    other_cols = [c for c in df.columns if c not in fixed_cols]
    return df[fixed_cols + other_cols]

# --- ユーティリティ ---
def get_app_url(ev_id=None):
    """環境に応じたURLを生成"""
    # Streamlit Cloudなどの環境でURLパラメータを付与
    try:
        # 実際はデプロイ環境のホスト名を取得するのが理想だが、簡易的に構築
        # browser.serverAddress が使えないため、運用に合わせて調整が必要
        base = "https://your-app.streamlit.app" 
        return f"{base}/?event_id={ev_id}" if ev_id else base
    except:
        return f"http://localhost:8501/?event_id={ev_id}"

# --- メインロジック ---
st.sidebar.title("🤝 懇親会調整くん")
mode = st.sidebar.radio("モード切替", ["参加者画面", "管理者画面", "サイトオーナー画面"])

# URLパラメータ取得
q_ev_id = st.query_params.get("event_id")

# --- 1. サイトオーナー画面 ---
if mode == "サイトオーナー画面":
    st.title("👑 全イベント管理")
    if st.text_input("オーナーパスワード", type="password") == OWNER_PASS:
        evs = get_events_df()
        if evs.empty:
            st.info("イベントは登録されていません。")
        for _, row in evs.iterrows():
            c1, c2 = st.columns([4, 1])
            c1.write(f"ID: {row['id']} | **{row['title']}**")
            if c2.button("削除", key=f"own_del_{row['id']}"):
                delete_event_data(row['id'])
                st.rerun()

# --- 2. 管理者画面 ---
elif mode == "管理者画面":
    st.title("⚙️ イベント管理者パネル")
    
    with st.expander("➕ 新しい懇親会イベントを作成する"):
        with st.form("create_new"):
            t = st.text_input("イベント名")
            p = st.text_input("管理パスワード設定", type="password")
            if st.form_submit_button("作成実行"):
                if t and p:
                    run_query("INSERT INTO events (title, password) VALUES (?, ?)", (t, p))
                    st.success(f"イベント「{t}」を作成しました。選択してログインしてください。")
                    st.rerun()

    ev_df = get_events_df()
    if ev_df.empty:
        st.info("イベントがありません。上記から作成してください。")
        st.stop()
    
    sel_title = st.selectbox("管理するイベントを選択", ev_df["title"])
    target_ev = ev_df[ev_df["title"] == sel_title].iloc[0]
    ev_id = target_ev["id"]

    # 認証
    auth_key = f"auth_{ev_id}"
    if not st.session_state.get(auth_key):
        with st.form(f"login_{ev_id}"):
            st.subheader(f"🔓 {sel_title}")
            input_pw = st.text_input("管理パスワード", type="password")
            if st.form_submit_button("ログイン"):
                if input_pw == target_ev["password"]:
                    st.session_state[auth_key] = True
                    st.rerun()
                else: st.error("パスワードが正しくありません")
        st.stop()

    # ログイン後のメイン画面
    st.header(f"📍 {sel_title}")
    share_url = get_app_url(ev_id)
    st.code(share_url, language=None)
    st.caption("👆 参加者に送るURLをコピーしてください")
    
    t1, t2, t3, t4 = st.tabs(["📅 日程設定", "📊 回答状況", "🍴 会場決定", "❌ イベント削除"])

    with t1:
        st.subheader("候補日時の追加")
        col1, col2 = st.columns(2)
        d = col1.date_input("日付")
        tm = col2.time_input("時間", value=datetime.strptime("18:30", "%H:%M").time())
        if st.button("この日時を追加"):
            dt_str = f"{d.strftime('%m/%d')}({['月','火','水','木','金','土','日'][d.weekday()]}) {tm.strftime('%H:%M')}～"
            run_query("INSERT INTO dates (event_id, dt_text) VALUES (?, ?)", (ev_id, dt_str))
            st.rerun()

    with t2:
        res_df = get_responses_df(ev_id)
        if not res_df.empty:
            st.dataframe(res_df, use_container_width=True)
            st.download_button("集計CSVダウンロード", res_df.to_csv(index=False).encode('utf-8-sig'), f"{sel_title}_集計.csv")
            # 苦手なものを抽出
            dislikes = [x for x in res_df["苦手・アレルギー"].tolist() if x]
            if dislikes:
                st.warning(f"⚠️ **参加者の苦手なもの:** {', '.join(dislikes)}")
                st.session_state[f"dis_list_{ev_id}"] = dislikes
        else:
            st.info("まだ回答がありません。")

    with t3:
        st.subheader("会場検索と案内文作成")
        date_list = [r[0] for r in run_query("SELECT dt_text FROM dates WHERE event_id=?", (ev_id,), True)]
        
        if not date_list:
            st.warning("先に日程を登録してください。")
        else:
            c_d, c_a, c_b = st.columns([2, 2, 1])
            sel_date = c_d.selectbox("開催決定日", date_list)
            area = c_a.text_input("エリア（駅名など）", placeholder="例：所沢")
            bud = c_b.selectbox("予算", list(BUDGET_MAP.keys()))
            
            if st.button("検索実行"):
                if not area: st.warning("エリアを入力してください。")
                else:
                    params = {"key": API_KEY, "keyword": area, "budget": BUDGET_MAP[bud], "count": 10, "format": "json"}
                    res = requests.get("http://webservice.recruit.co.jp/hotpepper/gourmet/v1/", params=params)
                    st.session_state.shop_results = res.json().get('results', {}).get('shop', [])

            if "shop_results" in st.session_state:
                dis_list = st.session_state.get(f"dis_list_{ev_id}", [])
                for s in st.session_state.shop_results:
                    # 簡易フィルタリング
                    if any(word in (s['name']+s['catch']+s['genre']['name']) for word in dis_list):
                        continue
                    
                    with st.container(border=True):
                        col_i, col_t = st.columns([1, 2])
                        with col_i: st.image(s['photo']['pc']['l'])
                        with col_t:
                            st.subheader(s['name'])
                            st.write(f"💰 {s['budget']['name']} | 🚬 {s['non_smoking']}")
                            g_url = f"https://www.google.com/maps/search/?api=1&query={urllib.parse.quote(s['name'] + ' ' + s['address'])}"
                            
                            if st.button(f"「{s['name']}」に決定", key=f"sel_{s['id']}"):
                                st.session_state[f"msg_{ev_id}"] = f"【懇親会開催のお知らせ】\n\n皆様、ご協力ありがとうございました。\n以下に決定しました！\n\n■日時：{sel_date}\n■会場：{s['name']}\n■地図：{g_url}\n■住所：{s['address']}\n■詳細：{s['urls']['pc']}\n\nよろしくお願いします！"
                                st.rerun()

            msg_key = f"msg_{ev_id}"
            if msg_key in st.session_state:
                st.divider()
                st.subheader("📝 コピペ用案内文")
                st.text_area("そのままSlack等に貼れます", value=st.session_state[msg_key], height=220)

    with t4:
        st.subheader("イベントの完全削除")
        if st.button("このイベントを今すぐ削除する", type="primary"):
            delete_event_data(ev_id)
            st.success("削除しました。")
            st.rerun()

# --- 3. 参加者画面 ---
else:
    st.title("🤝 懇親会アンケート")
    ev_df = get_events_df()
    current_ev_id = None

    # パラメータからの特定
    if q_ev_id:
        try:
            current_ev_id = int(q_ev_id)
            target = ev_df[ev_df["id"] == current_ev_id]
            if not target.empty:
                st.subheader(f"イベント：{target.iloc[0]['title']}")
            else: current_ev_id = None
        except: current_ev_id = None

    if not current_ev_id:
        if ev_df.empty:
            st.info("現在募集中のイベントはありません。")
            st.stop()
        sel_title = st.selectbox("回答するイベントを選択してください", ev_df["title"])
        current_ev_id = ev_df[ev_df["title"] == sel_title].iloc[0]["id"]

    # 回答フォーム
    date_rows = run_query("SELECT dt_text FROM dates WHERE event_id=?", (current_ev_id,), True)
    date_list = [r[0] for r in date_rows]
    
    if not date_list:
        st.info("幹事が日程を調整中です。少々お待ちください。")
    else:
        with st.form("ans_form"):
            name = st.text_input("お名前")
            dis = st.text_input("苦手な食べ物・アレルギー（任意）")
            st.divider()
            answers = {d: st.radio(d, ["○", "△", "×"], horizontal=True, index=0) for d in date_list}
            
            if st.form_submit_button("回答を送信する"):
                if name:
                    run_query(
                        "INSERT INTO responses (event_id, name, ans, dislikes) VALUES (?, ?, ?, ?)",
                        (current_ev_id, name, json.dumps(answers, ensure_ascii=False), dis)
                    )
                    st.success("回答ありがとうございました！")
                    st.rerun()
                else:
                    st.error("お名前を入力してください。")
        
        # 回答一覧
        st.subheader("📊 現在の回答状況")
        st.dataframe(get_responses_df(current_ev_id), use_container_width=True, hide_index=True)
