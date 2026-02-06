import streamlit as st
import pandas as pd
import uuid
from datetime import datetime

# モジュールインポート
# ※ファイル構成が変わっていない前提です
from modules.data_loader import load_master_db, load_project_db, save_project_data, add_master_price_item
from modules.calc_logic import calculate_dataframe, renumber_sort_keys
from modules.ui_dashboard import render_folder_tree, render_playlist_editor

# --- [1. ページ設定] ---
# ページ全体のレイアウトを「ワイド」に設定し、タイトルを定義します。
st.set_page_config(layout="wide", page_title="Dev: 見積システム")

# CSSでデザインを微調整（テーブルのヘッダー色やボタンの間隔など）
st.markdown("""
<style>
    .stApp { font-size: 1.05rem; }
    div[data-testid="stDataFrame"] th { background-color: #f0f2f6; }
    .stButton { margin-top: 10px; }
</style>
""", unsafe_allow_html=True)

# --- [2. 初期化セクション] ---
# アプリ内で使うデータを保持するための「箱（session_state）」を用意します。
if 'df_main' not in st.session_state: st.session_state.df_main = None
if 'df_prices' not in st.session_state: st.session_state.df_prices = None
if 'info_dict' not in st.session_state: st.session_state.info_dict = {}
if 'project_url' not in st.session_state: st.session_state.project_url = ""
if 'general_exp_rate' not in st.session_state: st.session_state.general_exp_rate = 10.0

# ==========================================
# サイドバーエリア（全体制御・設定）
# ※ここはフラグメントの外側です。ここを操作すると全体が再描画されます。
# ==========================================
with st.sidebar:
    st.header("🛠️ 開発用メニュー")
    
    # --- [DB接続機能] ---
    with st.expander("🔌 DB接続設定", expanded=(st.session_state.df_main is None)):
        default_url = st.secrets["app_config"].get("default_project_url", "")
        input_url = st.text_input("案件シートURL", value=default_url)
        
        if st.button("接続・読み込み"):
            try:
                with st.spinner("マスタと案件データをロード中..."):
                    secrets = dict(st.secrets)
                    # マスタデータの読み込み
                    df_items, df_prices = load_master_db(secrets)
                    st.session_state.df_prices = df_prices
                    # 案件データの読み込み
                    df_est, info, url = load_project_db(secrets, input_url)
                    
                    if df_est is not None:
                        # 並び順（sort_key）の初期処理
                        if 'sort_key' in df_est.columns:
                            df_est['sort_key'] = pd.to_numeric(df_est['sort_key'], errors='coerce').fillna(0)
                        else:
                            df_est['sort_key'] = 0

                        # 全て0の場合は初期連番を振る
                        if (df_est['sort_key'] == 0).all():
                            df_est['sort_key'] = (df_est.index + 1) * 100
                        
                        # 計算を実行してセッションに保存
                        st.session_state.df_main = calculate_dataframe(df_est)
                        st.session_state.info_dict = info
                        st.session_state.project_url = url
                        st.success("ロード完了")
                        st.rerun()
            except Exception as e:
                st.error(f"接続エラー: {e}")

    st.markdown("---")

    # --- [フォルダツリー機能] ---
    # 選択されたフィルタ条件を変数に格納します
    sel_large, sel_mid, sel_small, sel_part = "(すべて)", "(すべて)", "(すべて)", "(すべて)"
    
    if st.session_state.df_main is not None:
        sel_large, sel_mid, sel_small, sel_part = render_folder_tree(st.session_state.df_main)
        
        st.markdown("---")
        # 諸経費率の設定
        st.write("💰 **諸経費設定**")
        st.session_state.general_exp_rate = st.number_input(
            "諸経費率 (%)", value=st.session_state.general_exp_rate, step=1.0, format="%.1f"
        )
        
        # --- [保存ボタン] ---
        st.markdown("---")
        # ここを押すと、変更内容が一括でスプレッドシートに書き込まれます
        if st.button("💾 保存して整理", type="primary", use_container_width=True):
            with st.spinner("保存中..."):
                # 並び順を綺麗に整番（10, 20, 30...）
                clean_df = renumber_sort_keys(st.session_state.df_main)
                secrets = dict(st.secrets)
                # スプレッドシートへの保存実行
                if save_project_data(secrets, st.session_state.project_url, clean_df):
                    st.session_state.df_main = clean_df
                    st.success("保存完了！")
                else:
                    st.error("保存失敗")

# ==========================================
# メインエリア（フラグメント化）
# ==========================================

# @st.fragment: この関数内での変更は、画面全体をリロードせず、この関数部分だけを更新します。
@st.fragment
def view_project_editor(sel_large, sel_mid, sel_small, sel_part):
    
    # 案件名の表示
    project_name = st.session_state.info_dict.get('工事名', '新規案件')
    st.subheader(f"案件: {project_name}")
    
    # --- [1. フィルタリング処理] ---
    # 空文字が入っていると計算でエラーになる場合があるので埋める
    df = st.session_state.df_main.fillna("")
    mask = [True] * len(df)
    
    current_path = []
    
    # ツリー選択結果に基づいてデータを絞り込み（AND検索）
    if sel_large:
        mask = mask & (df['大項目'] == sel_large)
        current_path.append(sel_large)
    if sel_mid:
        mask = mask & (df['中項目'] == sel_mid)
        current_path.append(sel_mid)
    if sel_small:
        mask = mask & (df['小項目'] == sel_small)
        current_path.append(sel_small)
    if sel_part:
        mask = mask & (df['部分項目'] == sel_part)
        current_path.append(sel_part)
    
    path_str = " > ".join(current_path) if current_path else "全データ"
    st.caption(f"📂 現在の場所: **{path_str}**")

    # --- [2. リアルタイム集計処理] ---
    # フィルタリングに関わらず、案件全体の金額を集計します
    direct_cost = st.session_state.df_main['見積金額'].sum() # 直接工事費
    gen_exp_amount = int(direct_cost * (st.session_state.general_exp_rate / 100)) # 諸経費
    total_ex_tax = direct_cost + gen_exp_amount # 税抜合計
    tax_amount = int(total_ex_tax * 0.1) # 消費税
    grand_total = total_ex_tax + tax_amount # 税込合計
    
    # 利益計算
    cost_total = st.session_state.df_main['実行金額'].sum()
    profit = total_ex_tax - cost_total

    # --- [3. 金額サマリー表示 (HTML/CSS)] ---
    st.markdown(f"""
    <div style="display: flex; gap: 10px; flex-wrap: wrap; margin-bottom: 20px;">
        <div style="flex: 1; min-width: 120px; background: #fff; padding: 10px; border: 1px solid #ddd; border-radius: 6px;">
            <div style="color: #666; font-size: 0.75rem;">直接工事費</div>
            <div style="font-weight: bold; font-size: 1.0rem;">¥{direct_cost:,.0f}</div>
        </div>
        <div style="flex: 1; min-width: 120px; background: #fff; padding: 10px; border: 1px solid #ddd; border-radius: 6px;">
            <div style="color: #666; font-size: 0.75rem;">諸経費 ({st.session_state.general_exp_rate}%)</div>
            <div style="font-weight: bold; font-size: 1.0rem;">¥{gen_exp_amount:,.0f}</div>
        </div>
        <div style="flex: 1; min-width: 140px; background: #e3f2fd; padding: 10px; border: 1px solid #2196f3; border-radius: 6px;">
            <div style="color: #1565c0; font-size: 0.75rem;">見積総額 (税抜)</div>
            <div style="font-weight: bold; font-size: 1.2rem; color: #1565c0;">¥{total_ex_tax:,.0f}</div>
        </div>
        <div style="flex: 1; min-width: 140px; background: #e0f2f1; padding: 10px; border: 1px solid #009688; border-radius: 6px;">
            <div style="color: #00695c; font-size: 0.75rem;">税込合計</div>
            <div style="font-weight: bold; font-size: 1.3rem; color: #00695c;">¥{grand_total:,.0f}</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # --- [4. データエディタの表示] ---
    # 表示用のDataFrameを作成
    filtered_df = df[mask].copy()
    if 'sort_key' in filtered_df.columns:
        filtered_df = filtered_df.sort_values('sort_key')

    # エディタを表示し、ユーザーの編集結果を受け取る
    # num_rows="dynamic" で行追加を許可
    edited_df = render_playlist_editor(filtered_df)

    # --- [5. 自動同期処理 (Local Sync)] ---
    # ユーザーが編集した内容を、メモリ上の df_main に反映させます。
    # 変更を検知するためのチェック対象列
    check_cols = ['確認', '名称', '規格', '数量', '単位', 'NET', '原単価', '掛率', '備考']
    check_cols = [c for c in check_cols if c in filtered_df.columns and c in edited_df.columns]
    
    # 文字列化して比較することで、NaNなどの判定揺れを防ぎます
    df_src = filtered_df[check_cols].fillna("").astype(str).reset_index(drop=True)
    df_dst = edited_df[check_cols].fillna("").astype(str).reset_index(drop=True)
    
    # 変更があった場合のみ実行
    if not df_src.equals(df_dst):
        # 変更された行だけ再計算（金額などの自動計算）
        recalc_fragment = calculate_dataframe(edited_df)
        
        # 行ごとに df_main を更新
        for index, row in recalc_fragment.iterrows():
            key = row.get('sort_key', 0)
            
            # --- 新規行の追加処理 ---
            if pd.isna(key) or key == 0:
                if not row['名称'] or str(row['名称']).strip() == "": continue # 空行は無視

                new_row = row.copy()
                # フィルタ中の項目を自動補完
                new_row['大項目'] = sel_large if sel_large != "(すべて)" else ""
                new_row['中項目'] = sel_mid if sel_mid != "(すべて)" else ""
                new_row['小項目'] = sel_small if sel_small != "(すべて)" else ""
                new_row['部分項目'] = sel_part if sel_part != "(すべて)" else ""
                
                # 新しい連番キーを発行（最大値+10）
                max_key = st.session_state.df_main['sort_key'].max()
                if pd.isna(max_key): max_key = 0
                new_row['sort_key'] = max_key + 10
                
                # メインデータに追加
                st.session_state.df_main = pd.concat([st.session_state.df_main, pd.DataFrame([new_row])], ignore_index=True)
            
            # --- 既存行の更新処理 ---
            else:
                idxs = st.session_state.df_main[st.session_state.df_main['sort_key'] == key].index
                if not idxs.empty:
                    cols_to_upd = ['確認', '名称', '規格', '数量', '単位', 'NET', '原単価', '掛率', '売単価', '見積金額', '(自)荒利率', '備考']
                    valid_cols = [c for c in cols_to_upd if c in row.index and c in st.session_state.df_main.columns]
                    # 値を書き換え
                    st.session_state.df_main.loc[idxs[0], valid_cols] = row[valid_cols].values
        
        # 重要: Fragmentの中で rerun することで、エディタ部分だけが更新されます
        # これにより、合計金額なども即座に再計算されて表示されます
        st.rerun()

    # --- [6. マスタ登録アクション] ---
    # エディタの下に配置（ここもFragment内なので、ボタンを押しても画面全体はリセットされません）
    st.markdown("---")
    col1, col2 = st.columns([1, 1])
    
    with col1:
        st.markdown("##### 📤 マスタ登録")
        if st.button("チェックした行を定価マスタに追加"):
            checked_rows = edited_df[edited_df['確認'] == True]
            if checked_rows.empty:
                st.warning("マスタに追加したい行の「確認」列にチェックを入れてください。")
            else:
                target = checked_rows.iloc[0]
                
                # ダイアログ（モーダルウィンドウ）の定義
                @st.dialog("定価マスタへの追加")
                def register_dialog(item):
                    st.write("以下の内容で「定価表」に追加します。")
                    with st.form("master_add_form"):
                        s_name = st.text_input("検索名称 (短い呼び名)", value=str(item['名称']))
                        f_name = st.text_input("正式名称", value=str(item['名称']))
                        spec = st.text_input("規格", value=str(item['規格']))
                        unit = st.text_input("単位", value=str(item['単位']))
                        try:
                            def_price = float(item['原単価'])
                        except:
                            def_price = 0.0
                        price = st.number_input("標準単価", value=def_price)
                        
                        if st.form_submit_button("登録実行"):
                            secrets = dict(st.secrets)
                            data = [s_name, f_name, spec, unit, price]
                            if add_master_price_item(secrets, data):
                                st.success("登録しました！")
                                st.rerun()
                            else:
                                st.error("登録失敗")
                
                register_dialog(target)

    with col2:
        st.markdown("##### ⚙️ ヘルプ")
        st.info("""
        - **部分更新モード**: 入力しても画面全体はリセットされません。
        - **保存**: 完全にデータを保存するには、サイドバーの「💾 保存して整理」を押してください。
        """)

# ==========================================
# 実行エントリーポイント
# ==========================================
# 最後にメイン関数を呼び出します
if st.session_state.df_main is not None:
    # フィルタ条件を引数として渡します
    view_project_editor(sel_large, sel_mid, sel_small, sel_part)
else:
    st.info("👈 左側のサイドバーからDBに接続してください。")
    st.markdown("""
    ### 開発モードへようこそ
    1. サイドバーの **「接続・読み込み」** ボタンを押してください。
    2. データが読み込まれると、ここに編集画面が表示されます。
    """)
