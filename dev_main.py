import streamlit as st
import pandas as pd
import uuid
from datetime import datetime

# モジュールインポート
from modules.data_loader import load_master_db, load_project_db, save_project_data, add_master_price_item
from modules.calc_logic import calculate_dataframe, renumber_sort_keys
from modules.ui_dashboard import render_folder_tree, render_playlist_editor

# --- [1. ページ設定] ---
st.set_page_config(layout="wide", page_title="Dev: 見積システム")

# CSS: 右上の「動く人」を消し、テーブルを見やすく調整
st.markdown("""
<style>
    .stApp { font-size: 1.05rem; }
    div[data-testid="stDataFrame"] th { background-color: #f0f2f6; }
    .stButton { margin-top: 10px; }
    
    /* 右上のRunningインジケータとデプロイボタンを隠す */
    div[data-testid="stStatusWidget"] { visibility: hidden; }
    .stDeployButton { display: none; }
    
    /* 集計ボックスのデザイン */
    .summary-box {
        padding: 10px;
        border-radius: 5px;
        margin-bottom: 10px;
        text-align: center;
    }
</style>
""", unsafe_allow_html=True)

# --- [2. 初期化セクション] ---
if 'df_main' not in st.session_state: st.session_state.df_main = None
if 'df_prices' not in st.session_state: st.session_state.df_prices = None
if 'info_dict' not in st.session_state: st.session_state.info_dict = {}
if 'project_url' not in st.session_state: st.session_state.project_url = ""
if 'general_exp_rate' not in st.session_state: st.session_state.general_exp_rate = 10.0

# ==========================================
# サイドバーエリア
# ==========================================
with st.sidebar:
    st.header("🛠️ 開発用メニュー")
    
    # DB接続
    with st.expander("🔌 DB接続設定", expanded=(st.session_state.df_main is None)):
        default_url = st.secrets["app_config"].get("default_project_url", "")
        input_url = st.text_input("案件シートURL", value=default_url)
        
        if st.button("接続・読み込み"):
            try:
                with st.spinner("ロード中..."):
                    secrets = dict(st.secrets)
                    df_items, df_prices = load_master_db(secrets)
                    st.session_state.df_prices = df_prices
                    df_est, info, url = load_project_db(secrets, input_url)
                    
                    if df_est is not None:
                        # 初期処理
                        if 'sort_key' in df_est.columns:
                            df_est['sort_key'] = pd.to_numeric(df_est['sort_key'], errors='coerce').fillna(0)
                        else:
                            df_est['sort_key'] = 0
                        if (df_est['sort_key'] == 0).all():
                            df_est['sort_key'] = (df_est.index + 1) * 100
                        
                        st.session_state.df_main = calculate_dataframe(df_est)
                        st.session_state.info_dict = info
                        st.session_state.project_url = url
                        st.success("ロード完了")
                        st.rerun()
            except Exception as e:
                st.error(f"接続エラー: {e}")

    st.markdown("---")

    # フォルダツリー
    # 重要: ここでの操作が「df_main」を書き換えない限り、サイドバーは再描画されません
    sel_large, sel_mid, sel_small, sel_part = "(すべて)", "(すべて)", "(すべて)", "(すべて)"
    
    if st.session_state.df_main is not None:
        sel_large, sel_mid, sel_small, sel_part = render_folder_tree(st.session_state.df_main)
        
        st.markdown("---")
        st.write("💰 **諸経費設定**")
        st.session_state.general_exp_rate = st.number_input(
            "諸経費率 (%)", value=st.session_state.general_exp_rate, step=1.0, format="%.1f"
        )
        
        st.markdown("---")
        if st.button("💾 保存して整理", type="primary", use_container_width=True):
            with st.spinner("保存中..."):
                clean_df = renumber_sort_keys(st.session_state.df_main)
                secrets = dict(st.secrets)
                if save_project_data(secrets, st.session_state.project_url, clean_df):
                    st.session_state.df_main = clean_df
                    st.success("保存完了！")
                else:
                    st.error("保存失敗")

# ==========================================
# メインエリア（フラグメント化）
# ==========================================

@st.fragment
def view_project_editor(sel_large, sel_mid, sel_small, sel_part):
    
    project_name = st.session_state.info_dict.get('工事名', '新規案件')
    
    # --- [1. フィルタリング] ---
    df = st.session_state.df_main.fillna("")
    mask = [True] * len(df)
    
    current_path = []
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

    # --- [2. 絞り込みデータの作成] ---
    filtered_df = df[mask].copy()
    if 'sort_key' in filtered_df.columns:
        filtered_df = filtered_df.sort_values('sort_key')

    # --- [3. 金額集計（全体 & 表示中）] ---
    # 全体（諸経費計算用）
    total_direct = st.session_state.df_main['見積金額'].sum()
    gen_exp = int(total_direct * (st.session_state.general_exp_rate / 100))
    grand_total_taxed = int((total_direct + gen_exp) * 1.1)
    
    # ★追加: 表示中のデータのみの集計（原価管理用）
    sub_est = filtered_df['見積金額'].sum()
    sub_exec = filtered_df['実行金額'].sum() # 実行金額の合計
    sub_profit = sub_est - sub_exec
    sub_rate = (sub_profit / sub_est * 100) if sub_est > 0 else 0.0

    # --- [4. ヘッダー表示] ---
    st.subheader(f"案件: {project_name}")
    st.caption(f"📂 現在の場所: **{path_str}**")

    # 2段組みで表示（上段：全体総額、下段：現在表示中の内訳）
    st.markdown("#### 📊 全体総額 (税込): ¥{:,}".format(grand_total_taxed))
    
    # 現在表示中の項目の集計を表示（視認性重視）
    st.markdown(f"""
    <div style="display: flex; gap: 10px; flex-wrap: wrap; margin-bottom: 15px; background-color: #f8f9fa; padding: 10px; border-radius: 8px;">
        <div style="flex: 1; border-right: 1px solid #ddd; text-align: center;">
            <div style="font-size: 0.8rem; color: #666;">表示中の見積計</div>
            <div style="font-size: 1.1rem; font-weight: bold; color: #0d6efd;">¥{sub_est:,.0f}</div>
        </div>
        <div style="flex: 1; border-right: 1px solid #ddd; text-align: center;">
            <div style="font-size: 0.8rem; color: #666;">表示中の実行計</div>
            <div style="font-size: 1.1rem; font-weight: bold; color: #198754;">¥{sub_exec:,.0f}</div>
        </div>
        <div style="flex: 1; text-align: center;">
            <div style="font-size: 0.8rem; color: #666;">想定荒利</div>
            <div style="font-size: 1.1rem; font-weight: bold; color: #fd7e14;">¥{sub_profit:,.0f} ({sub_rate:.1f}%)</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # --- [5. データエディタ] ---
    # エディタを表示（実行金額は modules/ui_dashboard.py 側で表示列に含まれている必要がありますが、
    # もし表示されていない場合は column_config で追加可能です。ここではデータ自体には含まれています）
    edited_df = render_playlist_editor(filtered_df)

    # --- [6. 自動同期処理 (Local Sync)] ---
    check_cols = ['確認', '名称', '規格', '数量', '単位', 'NET', '原単価', '掛率', '備考']
    check_cols = [c for c in check_cols if c in filtered_df.columns and c in edited_df.columns]
    
    df_src = filtered_df[check_cols].fillna("").astype(str).reset_index(drop=True)
    df_dst = edited_df[check_cols].fillna("").astype(str).reset_index(drop=True)
    
    if not df_src.equals(df_dst):
        recalc_fragment = calculate_dataframe(edited_df)
        
        for index, row in recalc_fragment.iterrows():
            key = row.get('sort_key', 0)
            
            # 新規行
            if pd.isna(key) or key == 0:
                if not row['名称'] or str(row['名称']).strip() == "": continue
                new_row = row.copy()
                new_row['大項目'] = sel_large if sel_large != "(すべて)" else ""
                new_row['中項目'] = sel_mid if sel_mid != "(すべて)" else ""
                new_row['小項目'] = sel_small if sel_small != "(すべて)" else ""
                new_row['部分項目'] = sel_part if sel_part != "(すべて)" else ""
                
                max_key = st.session_state.df_main['sort_key'].max()
                if pd.isna(max_key): max_key = 0
                new_row['sort_key'] = max_key + 10
                
                st.session_state.df_main = pd.concat([st.session_state.df_main, pd.DataFrame([new_row])], ignore_index=True)
            
            # 既存行更新（実行金額も書き戻す）
            else:
                idxs = st.session_state.df_main[st.session_state.df_main['sort_key'] == key].index
                if not idxs.empty:
                    # '実行金額' も更新対象に含める
                    cols_to_upd = ['確認', '名称', '規格', '数量', '単位', 'NET', '原単価', '掛率', '売単価', '見積金額', '実行金額', '荒利金額', '(自)荒利率', '備考']
                    valid_cols = [c for c in cols_to_upd if c in row.index and c in st.session_state.df_main.columns]
                    st.session_state.df_main.loc[idxs[0], valid_cols] = row[valid_cols].values
        
        st.rerun()

    # --- [7. マスタ登録] ---
    st.markdown("---")
    col1, col2 = st.columns([1, 1])
    with col1:
        st.markdown("##### 📤 マスタ登録")
        if st.button("チェックした行を定価マスタに追加"):
            checked_rows = edited_df[edited_df['確認'] == True]
            if checked_rows.empty:
                st.warning("チェックを入れてください。")
            else:
                target = checked_rows.iloc[0]
                @st.dialog("定価マスタへの追加")
                def register_dialog(item):
                    with st.form("master_add_form"):
                        s_name = st.text_input("検索名称", value=str(item['名称']))
                        f_name = st.text_input("正式名称", value=str(item['名称']))
                        spec = st.text_input("規格", value=str(item['規格']))
                        unit = st.text_input("単位", value=str(item['単位']))
                        try: def_price = float(item['原単価'])
                        except: def_price = 0.0
                        price = st.number_input("標準単価", value=def_price)
                        if st.form_submit_button("登録"):
                            secrets = dict(st.secrets)
                            data = [s_name, f_name, spec, unit, price]
                            if add_master_price_item(secrets, data):
                                st.success("登録完了")
                                st.rerun()
                register_dialog(target)

# ==========================================
# 実行
# ==========================================
if st.session_state.df_main is not None:
    view_project_editor(sel_large, sel_mid, sel_small, sel_part)
else:
    st.info("👈 左側のサイドバーからDBに接続してください。")
