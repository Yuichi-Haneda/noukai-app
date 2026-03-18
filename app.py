import streamlit as st
import pandas as pd
import requests
from datetime import datetime

# --- 設定 ---
st.set_page_config(page_title="納会調整くん Pro", layout="wide")

# ホットペッパーAPIキー（Streamlit Secretsから取得）
API_KEY = st.secrets.get("HOTPEPPER_API_KEY", "")

# 管理者ログイン情報（本来はこれもSecretsに入れるのが安全です）
ADMIN_USER = "admin"
ADMIN_PASS = "noukai2026" # 好きなパスワードに変更してください

# --- データの保持 ---
if 'events' not in st.session_state:
    st.session_state.events = {
        "dates": [],
        "responses": pd.DataFrame(columns=["名前"]),
        "fixed_date": None,
        "selected_shop": None
    }

# --- 関数: お店検索 ---
def search_shops(keyword):
    url = "http://webservice.recruit.co.jp/hotpepper/gourmet/v1/"
    params = {
        "key": API_KEY,
        "keyword": f"{keyword} 宴会",
        "count": 3,
        "format": "json",
        "order": 4
    }
    res = requests.get(url, params=params)
    if res.status_code == 200:
        return res.json().get('results', {}).get('shop', [])
    return []

# --- サイドバー：ログイン機能 ---
st.sidebar.title("メニュー")
mode = st.sidebar.radio("表示切替", ["参加者画面", "管理者画面"])

# --- 管理者画面（ログイン制限あり） ---
if mode == "管理者画面":
    st.title("🔐 管理者専用パネル")
    
    # 簡易ログインチェック
    if 'logged_in' not in st.session_state:
        st.session_state.logged_in = False

    if not st.session_state.logged_in:
        with st.form("login_form"):
            user = st.text_input("ID")
            pw = st.text_input("Password", type="password")
            if st.form_submit_button("ログイン"):
                if user == ADMIN_USER and pw == ADMIN_PASS:
                    st.session_state.logged_in = True
                    st.rerun()
                else:
                    st.error("IDまたはパスワードが違います")
        st.stop() # ログインしてなければここで処理停止

    # ログイン後のコンテンツ
    tab1, tab2 = st.tabs(["日程設定・回答確認", "お店選び・案内作成"])

    with tab1:
        st.subheader("1. 候補日時の設定")
        col1, col2 = st.columns(2)
        with col1:
            d = st.date_input("候補日を追加")
        with col2:
            t = st.time_input("開始時間", value=datetime.strptime("18:30", "%H:%M").time())
        
        if st.button("この日時をリストに追加"):
            datetime_str = f"{d.strftime('%m/%d')}({['月','火','水','木','金','土','日'][d.weekday()]}) {t.strftime('%H:%M')}～"
            if datetime_str not in st.session_state.events["dates"]:
                st.session_state.events["dates"].append(datetime_str)
                # 表の列を更新
                st.session_state.events["responses"] = pd.DataFrame(columns=["名前"] + st.session_state.events["dates"])
                st.success(f"追加しました: {datetime_str}")

        if st.button("リストをリセット"):
            st.session_state.events["dates"] = []
            st.session_state.events["responses"] = pd.DataFrame(columns=["名前"])
            st.rerun()

        st.divider()
        st.subheader("📊 現在の回答状況")
        st.dataframe(st.session_state.events["responses"], use_container_width=True)

    with tab2:
        if not st.session_state.events["dates"]:
            st.warning("先に日程を設定してください")
        else:
            st.subheader("2. 開催日とお見せの決定")
            final_date = st.selectbox("最終決定日を選択", st.session_state.events["dates"])
            area = st.text_input("検索エリア", value="所沢")
            
            if st.button("おすすめのお店を検索"):
                shops = search_shops(area)
                if shops:
                    for shop in shops:
                        with st.container(border=True):
                            c1, c2 = st.columns([1, 2])
                            with c1:
                                st.image(shop['photo']['pc']['l'])
                            with c2:
                                st.subheader(shop['name'])
                                st.write(f"📍 {shop['address']}")
                                st.write(f"💰 予算: {shop['budget']['name']}")
                                st.write(f"🔗 [ホットペッパーで見る]({shop['urls']['pc']})")
                                if st.button(f"この店に決定", key=f"btn_{shop['id']}"):
                                    st.session_state.events["fixed_date"] = final_date
                                    st.session_state.events["selected_shop"] = shop
                                    st.success("決定しました！下に案内文が表示されます。")
                else:
                    st.error("お店が見つかりませんでした。")

            # 案内文の表示（決定している場合のみ）
            if st.session_state.events["fixed_date"] and st.session_state.events["selected_shop"]:
                st.divider()
                st.subheader("📝 送信用メッセージ")
                s = st.session_state.events["selected_shop"]
                msg = f"""【納会開催のお知らせ】
日時の調整が完了しました！

■日時：{st.session_state.events['fixed_date']}
■場所：{s['name']}
■地図：{s['urls']['pc']}
■予算：{s['budget']['name']}

皆様のご参加をお待ちしております！"""
                st.text_area("コピーして共有", value=msg, height=180)

# --- 参加者画面 ---
else:
    st.title("🗓 納会日程アンケート")
    if not st.session_state.events["dates"]:
        st.info("幹事が日程を調整中です。公開までお待ちください。")
    else:
        st.write("ご希望の日時を選択して送信してください。")
        with st.form("user_form"):
            name = st.text_input("お名前（必須）")
            ans_list = {}
            for d in st.session_state.events["dates"]:
                ans_list[d] = st.radio(f"{d}", ["○ (参加可能)", "△ (未定)", "× (不可)"], horizontal=True)
            
            if st.form_submit_button("回答を送信"):
                if name:
                    new_data = {"名前": name}
                    new_data.update(ans_list)
                    st.session_state.events["responses"] = pd.concat([
                        st.session_state.events["responses"], 
                        pd.DataFrame([new_data])
                    ], ignore_index=True)
                    st.success("回答を受け付けました。ありがとうございます！")
                else:
                    st.error("お名前を入力してください。")
