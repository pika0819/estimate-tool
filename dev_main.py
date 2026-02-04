import streamlit as st
import pandas as pd
import uuid
from datetime import datetime

# 作成したモジュールをインポート
from modules.data_loader import load_master_db, load_project_db, save_project_data, add_master_price_item
from modules.calc_logic import calculate_dataframe, renumber_sort_keys
from modules.ui_dashboard import render_folder_tree, render_playlist_editor

# --- ページ設定 ---
st.set_page_config(layout="wide", page_title="Dev: 見積システム")

# CSS: 見やすさ調整
st.markdown("""
<style>
    .stApp { font-size: 1.05rem; }
    /* テーブルヘッダーの背景色 */
    div[data-testid="stDataFrame"] th { background-color: #f0f2f6; }
    /* ボタンの余白調整 */
    .stButton { margin-top: 10px; }
</style>
""", unsafe_allow_html=True)

# --- セッション状態の初期化 (ここが消えているとエラーになります) ---
if 'df_main' not in st.session_state: st.session_state.df_main = None
if 'df_prices' not in st.session_state: st.session_state.df_prices = None
if 'info_dict' not in st.session_state: st.session_state.info_dict = {}
if 'project_url' not in st.session_state: st.session_state.project_url = ""

# ==========================================
# サイドバー：DB接続 & フォルダツリー
# ==========================================
with st.sidebar:
    st.header("🛠️ 開発用メニュー")
    
    # 1. DB接続エリア (データ未ロード時のみ開く)
    with st.expander("🔌 DB接続設定", expanded=(st.session_state.df_main is None)):
        # Secretsから案件URLのデフォルトを取得
        default_url = st.secrets["app_config"].get("default_project_url", "")
        input_url = st.text_input("案件シートURL", value=default_url)
        
        if st.button("接続・読み込み"):
            try:
                with st.spinner("マスタと案件データをロード中..."):
                    secrets = dict(st.secrets)
                    
                    # A. マスタ読込 (定価表・項目表)
                    df_items, df_prices = load_master_db(secrets)
                    st.session_state.df_prices = df_prices
                    
                    # B. 案件読込
                    df_est, info, url = load_project_db(secrets, input_url)
                    
                    if df_est is not None:
                        # ---------------------------------------------------------
                        # 【修正済】ロード時のID処理ロジック (増殖バグ対策)
                        # ---------------------------------------------------------
                        # 1. sort_key を強制的に数値化（空文字対策）
                        if 'sort_key' in df_est.columns:
                            # エラー(空文字など)はNaNになり、その後0に変換
                            df_est['sort_key'] = pd.to_numeric(df_est['sort_key'], errors='coerce').fillna(0)
                        else:
                            df_est['sort_key'] = 0

                        # 2. IDが0の行（新規または未設定）は、連番（100, 200...）を振る
                        #    (全行0なら全行リナンバリングする)
                        if (df_est['sort_key'] == 0).all():
                            df_est['sort_key'] = (df_est.index + 1) * 100
                        
                        # 3. 計算実行
                        st.session_state.df_main = calculate_dataframe(df_est)
                        st.session_state.info_dict = info
                        st.session_state.project_url = url
                        st.success("ロード完了")
                        st.rerun()

            except Exception as e:
                st.error(f"接続エラー: {e}")

    st.markdown("---")

    # 2. フォルダツリー (データがある場合のみ表示)
    sel_large, sel_mid, sel_small = "(すべて)", "(すべて)", "(すべて)"
    
    if st.session_state.df_main is not None:
        # 階層選択ツリーを表示
        sel_large, sel_mid, sel_small = render_folder_tree(st.session_state.df_main)
        
        # 簡易集計
        st.markdown("---")
        total = st.session_state.df_main['見積金額'].sum()
        cost = st.session_state.df_main['実行金額'].sum()
        profit = total - cost
        st.metric("見積総額 (税抜)", f"¥{total:,.0f}")
        st.metric("想定粗利", f"¥{profit:,.0f}")
        
        # 保存ボタン
        st.markdown("---")
        if st.button("💾 保存して整理", type="primary", use_container_width=True):
            with st.spinner("ソート順を整理して保存中..."):
                # 1. リナンバリング (100, 200...)
                clean_df = renumber_sort_keys(st.session_state.df_main)
                # 2. 保存実行
                secrets = dict(st.secrets)
                if save_project_data(secrets, st.session_state.project_url, clean_df):
                    st.session_state.df_main = clean_df
                    st.success("保存完了！シートを更新しました。")
                else:
                    st.error("保存失敗")

# ==========================================
# メインエリア：プレイリスト編集
# ==========================================
if st.session_state.df_main is not None:
    # 1. ヘッダー情報
    project_name = st.session_state.info_dict.get('工事名', '新規案件')
    st.subheader(f"案件: {project_name}")
    
    # 2. データのフィルタリング (フォルダの中身を表示)
    df = st.session_state.df_main
    mask = [True] * len(df)
    
    current_path = []
    if sel_large != "(すべて)":
        mask = mask & (df['大項目'] == sel_large)
        current_path.append(sel_large)
    if sel_mid != "(すべて)":
        mask = mask & (df['中項目'] == sel_mid)
        current_path.append(sel_mid)
    if sel_small != "(すべて)":
        mask = mask & (df['小項目'] == sel_small)
        current_path.append(sel_small)
    
    # パンくずリスト表示
    path_str = " > ".join(current_path) if current_path else "全データ"
    st.caption(f"📂 現在の場所: **{path_str}**")

    # 表示用データフレーム作成
    filtered_df = df[mask].copy()
    
    # ソート順を適用 (sort_key昇順)
    if 'sort_key' in filtered_df.columns:
        filtered_df = filtered_df.sort_values('sort_key')

    # 3. エディタ (プレイリスト) の表示
    edited_df = render_playlist_editor(filtered_df)

    # 4. 編集内容の同期 & 計算
    # ---------------------------------------------------------
    # 【修正版】無限ループ防止 (空回り防止機能付き)
    # ---------------------------------------------------------
    
    # A. 本当に変更があったかチェック
    check_cols = ['確認', '名称', '規格', '数量', '単位', 'NET', '原単価', '掛率', '備考', '部分項目']
    check_cols = [c for c in check_cols if c in filtered_df.columns and c in edited_df.columns]
    
    # 値の比較（型ズレによる誤検知を防ぐため、一度文字列化して比較する）
    df_src = filtered_df[check_cols].fillna("").astype(str).reset_index(drop=True)
    df_dst = edited_df[check_cols].fillna("").astype(str).reset_index(drop=True)
    has_changes = not df_src.equals(df_dst)

    if has_changes:
        # 再計算
        recalc_fragment = calculate_dataframe(edited_df)
        
        # 実際にデータフレームを更新したかどうかのフラグ
        data_changed = False
        
        # 大元のデータ(st.session_state.df_main)を更新する
        for index, row in recalc_fragment.iterrows():
            key = row.get('sort_key', 0)
            
            # --- 新規行(keyが0または空)の場合 ---
            if pd.isna(key) or key == 0:
                # 名称が空の行は「追加しない」し、変更ともみなさない
                if not row['名称'] or str(row['名称']).strip() == "":
                    continue

                # ここまで来たら「本当に追加する」
                new_row = row.copy()
                new_row['大項目'] = sel_large if sel_large != "(すべて)" else ""
                new_row['中項目'] = sel_mid if sel_mid != "(すべて)" else ""
                new_row['小項目'] = sel_small if sel_small != "(すべて)" else ""
                
                max_key = st.session_state.df_main['sort_key'].max()
                if pd.isna(max_key): max_key = 0
                new_row['sort_key'] = max_key + 10
                
                st.session_state.df_main = pd.concat([st.session_state.df_main, pd.DataFrame([new_row])], ignore_index=True)
                data_changed = True
            
            # --- 既存行の場合 ---
            else:
                idxs = st.session_state.df_main[st.session_state.df_main['sort_key'] == key].index
                if not idxs.empty:
                    cols_to_upd = ['確認', '名称', '規格', '数量', '単位', 'NET', '原単価', '掛率', '売単価', '見積金額', '(自)荒利率', '備考', '部分項目']
                    valid_cols = [c for c in cols_to_upd if c in row.index and c in st.session_state.df_main.columns]
                    
                    # 値を書き込む
                    st.session_state.df_main.loc[idxs[0], valid_cols] = row[valid_cols].values
                    data_changed = True
        
        # 【重要】実際にデータの書き換えが発生したときだけ再描画する
        if data_changed:
            st.rerun()

    # 5. アクションエリア (マスタ登録など)
    st.markdown("---")
    col1, col2 = st.columns([1, 1])
    
    with col1:
        st.markdown("##### 📤 マスタ登録")
        if st.button("チェックした行を定価マスタに追加"):
            # 確認チェックがついている行を抽出
            checked_rows = edited_df[edited_df['確認'] == True]
            
            if checked_rows.empty:
                st.warning("マスタに追加したい行の「確認」列にチェックを入れてください。")
            else:
                # 先頭の1行を対象にする
                target = checked_rows.iloc[0]
                
                # ダイアログで入力させる
                @st.dialog("定価マスタへの追加")
                def register_dialog(item):
                    st.write("以下の内容で「定価表」に追加します。")
                    with st.form("master_add_form"):
                        # 検索名称は短いものを入力推奨
                        s_name = st.text_input("検索名称 (短い呼び名)", value=str(item['名称']))
                        f_name = st.text_input("正式名称", value=str(item['名称']))
                        spec = st.text_input("規格", value=str(item['規格']))
                        unit = st.text_input("単位", value=str(item['単位']))
                        # 単価は数値変換してから
                        try:
                            def_price = float(item['原単価'])
                        except:
                            def_price = 0.0
                        price = st.number_input("標準単価", value=def_price)
                        
                        if st.form_submit_button("登録実行"):
                            secrets = dict(st.secrets)
                            data = [s_name, f_name, spec, unit, price]
                            if add_master_price_item(secrets, data):
                                st.success("登録しました！次回から検索候補に出ます。")
                                st.rerun()
                            else:
                                st.error("登録に失敗しました。")
                
                register_dialog(target)

    with col2:
        st.markdown("##### ⚙️ ヘルプ")
        st.info("""
        - **行の追加**: 表の一番下の `+` 行に入力してください。
        - **計算**: 数値を変えてエンターを押すと自動計算されます。
        - **保存**: サイドバーの「保存して整理」を押すと、並び順が整理されて保存されます。
        """)

else:
    # データ未ロード時の表示
    st.info("👈 左側のサイドバーからDBに接続してください。")
    st.markdown("""
    ### 開発モードへようこそ
    1. サイドバーの **「接続・読み込み」** ボタンを押してください。
    2. データが読み込まれると、ここに編集画面が表示されます。
    """)
