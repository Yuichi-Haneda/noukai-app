# --- (前略：インポートやDB設定はそのまま) ---

    with t3:
        st.subheader("🍴 最適な会場を見つける")
        with sqlite3.connect(DB_FILE) as conn:
            conn.row_factory = sqlite3.Row
            date_rows = conn.execute("SELECT dt_text FROM dates WHERE event_id=?", (ev_id,)).fetchall()
        dates = [r['dt_text'] for r in date_rows]
        
        if not dates:
            st.warning("先に「日程設定」タブで候補日を登録してください。")
        else:
            # 検索条件入力エリア
            with st.container(border=True):
                c_d, c_a, c_b = st.columns([2, 2, 1])
                sel_date = c_d.selectbox("開催決定日", dates)
                area = c_a.text_input("エリア・駅名", placeholder="例：所沢, 新宿")
                bud = c_b.selectbox("予算", list(BUDGET_MAP.keys()))
                search_btn = st.button("🔍 この条件でお店を探す", use_container_width=True)

            if search_btn:
                if not area:
                    st.error("エリアを入力してください。")
                else:
                    params = {
                        "key": API_KEY,
                        "keyword": area,
                        "budget": BUDGET_MAP[bud],
                        "count": 10,
                        "format": "json"
                    }
                    try:
                        res = requests.get("http://webservice.recruit.co.jp/hotpepper/gourmet/v1/", params=params)
                        st.session_state.shops = res.json().get('results', {}).get('shop', [])
                        if not st.session_state.shops:
                            st.info("条件に合うお店が見つかりませんでした。")
                    except:
                        st.error("API連携に失敗しました。APIキーを確認してください。")

            # 店舗情報の表示
            if "shops" in st.session_state:
                st.write(f"### 検索結果 ({len(st.session_state.shops)}件)")
                dis_list = st.session_state.get(f"dis_{ev_id}", [])
                
                for s in st.session_state.shops:
                    # 苦手食材フィルタリング（簡易）
                    if any(word in (s['name'] + s['catch']) for word in dis_list):
                        continue

                    with st.container(border=True):
                        col1, col2 = st.columns([1, 2])
                        
                        with col1:
                            st.image(s['photo']['pc']['l'], use_container_width=True)
                        
                        with col2:
                            st.caption(f"📍 {s['genre']['name']} / {s['sub_genre']['name'] if 'sub_genre' in s else ''}")
                            st.subheader(f"{s['name']}")
                            st.write(f"「{s['catch']}」")
                            
                            # リッチなメタ情報表示
                            m1, m2, m3 = st.columns(3)
                            m1.markdown(f"💰 **予算**\n{s['budget']['name']}")
                            m2.markdown(f"🚬 **禁煙/喫煙**\n{s['non_smoking']}")
                            m3.markdown(f"座席: {s['capacity']}席")
                            
                            st.write(f"🏠 {s['address']}")
                            
                            # 地図URL生成
                            g_map_url = f"https://www.google.com/maps/search/?api=1&query={urllib.parse.quote(s['name'] + ' ' + s['address'])}"
                            
                            c1, c2 = st.columns(2)
                            with c1:
                                st.link_button("🔗 ホットペッパーで詳細を見る", s['urls']['pc'], use_container_width=True)
                            with c2:
                                if st.button(f"✅ このお店に決定", key=f"sel_{s['id']}", type="primary", use_container_width=True):
                                    # 案内文生成
                                    st.session_state[f"msg_{ev_id}"] = f"""【懇親会開催のお知らせ】

皆様、日程調整へのご協力ありがとうございました！
以下の内容で予約・決定いたしました。

━━━━━━━━━━━━━━
■日時：{sel_date}
■会場：{s['name']}
■予算目安：{s['budget']['name']}
■地図：{g_map_url}
■住所：{s['address']}
━━━━━━━━━━━━━━

詳細はこちら：
{s['urls']['pc']}

当日は皆様にお会いできるのを楽しみにしています！"""
                                    st.rerun()

            # 案内文の表示
            msg_key = f"msg_{ev_id}"
            if msg_key in st.session_state:
                st.divider()
                st.success("🎉 会場が決定しました！以下の文章をコピーして共有してください。")
                st.text_area("Slack / Teams / メール用 案内文", value=st.session_state[msg_key], height=300)

# --- (以下略) ---
