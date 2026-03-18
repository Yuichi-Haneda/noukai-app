import streamlit as st
import pandas as pd
import requests
from datetime import datetime

# --- 設定 ---
st.set_page_config(page_title="納会日程・お店調整くん", layout="wide")

# ホットペッパーAPIキー（Streamlit Secretsから取得）
API_KEY = st.secrets.get("HOTPEPPER_API_KEY", "YOUR_DUMMY_KEY")

# --- 簡易DB代わりのセッション状態（本来はSQLite等で保存） ---
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

# --- UI: サイドバーで画面切り替え ---
mode = st.sidebar.radio("モード選択", ["管理者画面", "参加者画面"])

# --- 管理者画面 ---
if mode == "管理者画面":
    st.title("📢 幹事用：イベント設定")
    
    # 1. 日時候補の設定
    new_dates = st.multiselect("候補日を選択してください", 
                                ["12/18(金)", "12/24(木)", "12/25(金)", "12/28(月)"],
                                default=st.session_state.events["dates"])
    
    if st.button("候補日を確定して参加者に共有"):
        st.session_state.events["dates"] = new_dates
        # 新しい日程に合わせて回答表の列を更新
        st.session_state.events["responses"] = pd.DataFrame(columns=["名前"] + new_dates)
        st.success("候補日をセットしました！参加者画面に切り替えてURLを共有してください。")

    st.divider()

    # 2. 回答状況の確認
    st.subheader("📊 現在の回答状況")
    st.dataframe(st.session_state.events["responses"])

    # 3. 日程決定とお見せピックアップ
    if len(st.session_state.events["dates"]) > 0:
        st.subheader("決定・お店選び")
        final_date = st.selectbox("開催日を決定する", st.session_state.events["dates"])
        area = st.text_input("検索エリア（例：小手指、所沢）", value="所沢")
        
        if st.button("おすすめのお店を検索"):
            shops = search_shops(area)
            if shops:
                for shop in shops:
                    col1, col2 = st.columns([1, 3])
                    with col1:
                        st.image(shop['photo']['pc']['l'], width=150)
                    with col2:
                        st.write(f"**{shop['name']}**")
                        st.write(f"予算: {shop['budget']['name']} / ジャンル: {shop['genre']['name']}")
                        if st.button(f"{shop['name']}に決定！", key=shop['id']):
                            st.session_state.events["fixed_date"] = final_date
                            st.session_state.events["selected_shop"] = shop
                            st.balloons()
            else:
                st.warning("お店が見つかりませんでした。APIキーを確認してください。")

    # 4. 案内文生成
    if st.session_state.events["fixed_date"] and st.session_state.events["selected_shop"]:
        st.divider()
        st.subheader("📝 そのまま送れる案内文")
        shop = st.session_state.events["selected_shop"]
        msg = f"""【納会のお知らせ】
調整の結果、以下の内容で決定しました！

■日時：{st.session_state.events['fixed_date']}
■場所：{shop['name']}
■地図：{shop['urls']['pc']}

皆様、よろしくお願いします！"""
        st.text_area("コピーしてSlack等に貼り付け", value=msg, height=150)

# --- 参加者画面 ---
else:
    st.title("🗓 納会日程アンケート")
    if not st.session_state.events["dates"]:
        st.info("現在、幹事が日程を調整中です。しばらくお待ちください。")
    else:
        with st.form("response_form"):
            name = st.text_input("お名前")
            answers = {}
            for d in st.session_state.events["dates"]:
                answers[d] = st.radio(f"{d}の予定は？", ["○", "△", "×"], horizontal=True)
            
            if st.form_submit_button("回答を送信"):
                new_row = {"名前": name}
                new_row.update(answers)
                # DataFrameを更新
                st.session_state.events["responses"] = pd.concat([
                    st.session_state.events["responses"], 
                    pd.DataFrame([new_row])
                ], ignore_index=True)
                st.success("回答ありがとうございます！")
