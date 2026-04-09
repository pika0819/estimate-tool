import streamlit as st
import pandas as pd
import uuid
from datetime import datetime
from data_utils import load_data, calculate_dataframe, save_data
from pdf_exporter import EstimatePDFGenerator

def main():
    # Step 1: ページ設定とスタイル定義
    st.set_page_config(layout="wide", page_title="見積コントロールセンター")
    st.markdown("""
    <style>
        .stApp { font-size: 1.1rem; }
        .metric-label { font-size: 1.2rem; font-weight: bold; color: #555; }
        .metric-value-lg { font-size: 2.2rem; font-weight: bold; color: #1f77b4; line-height: 1.2; }
        div[data-testid="stSidebar"] { min-width: 350px; }
    </style>
    """, unsafe_allow_html=True)

    # Step 2: セッション状態の初期化
    if 'df_main' not in st.session_state: st.session_state.df_main = None
    if 'info_dict' not in st.session_state: st.session_state.info_dict = {}
    if 'sheet_url' not in st.session_state: st.session_state.sheet_url = ""
    if 'overhead_rates_map' not in st.session_state: st.session_state.overhead_rates_map = {}

    with st.sidebar:
        st.title("🛠️ 見積管理盤")
        
        with st.expander("📂 データ接続設定", expanded=(st.session_state.df_main is None)):
            input_url = st.text_input("スプレッドシートURL", value=st.session_state.sheet_url)
            if st.button("データを読み込む"):
                try:
                    # secretsの存在確認（エッジケース対策）
                    if "gcp_service_account" not in st.secrets:
                        st.error("Secretsに 'gcp_service_account' が設定されていません。")
                        return
                    
                    secrets = dict(st.secrets["gcp_service_account"])
                    with st.spinner("シートから直接データを取得中..."):
                        df, info = load_data(input_url, secrets)
                        if df is not None:
                            # IDの自動付与
                            if 'sort_key' not in df.columns:
                                df['sort_key'] = [str(uuid.uuid4()) for _ in range(len(df))]
                            
                            st.session_state.info_dict = info
                            st.session_state.sheet_url = input_url
                            st.session_state.df_main = calculate_dataframe(df, st.session_state.overhead_rates_map)
                            st.rerun()
                except Exception as e:
                    st.error(f"接続エラー: {e}")

        st.markdown("---")

        if st.session_state.df_main is not None:
            # Step 3: 諸経費設定と集計
            st.subheader("💰 諸経費設定")
            df_cur = st.session_state.df_main
            overhead_rows = df_cur[df_cur['大項目'] == '諸経費']
            
            if not overhead_rows.empty:
                rates_updated = False
                for _, row in overhead_rows.iterrows():
                    s_key = str(row['sort_key'])
                    current_rate = st.session_state.overhead_rates_map.get(s_key, 0.0)
                    st.markdown(f"**{row['名称']}**", unsafe_allow_html=True)
                    new_rate = st.number_input(f"諸経費率 (%)", 0.0, 100.0, float(current_rate), 0.5, key=f"rate_{s_key}")
                    
                    if new_rate != current_rate:
                        st.session_state.overhead_rates_map[s_key] = new_rate
                        rates_updated = True
                
                if rates_updated:
                    st.session_state.df_main = calculate_dataframe(df_cur, st.session_state.overhead_rates_map)
                    st.rerun()

            total_est = df_cur['見積金額'].sum()
            st.markdown(f'<div class="metric-label">見積総額 (税抜)</div>', unsafe_allow_html=True)
            st.markdown(f'<div class="metric-value-lg">¥{total_est:,.0f}</div>', unsafe_allow_html=True)
            
            if st.button("💾 シートに保存・更新", type="primary", use_container_width=True):
                if save_data(st.session_state.sheet_url, dict(st.secrets["gcp_service_account"]), st.session_state.df_main):
                    st.success("保存完了")
                else:
                    st.error("保存失敗")

    # Step 4: メインエディタ表示（型保証とUI設定の実施）
    if st.session_state.df_main is not None:
        st.subheader(f"📋 見積明細: {st.session_state.info_dict.get('工事名', '未設定')}")
        display_cols = ['確認', '大項目', '中項目', '名称', '規格', '数量', '単位', 'NET', '原単価', '掛率', '売単価', '見積金額', '荒利率', '備考', 'sort_key']
        
        # --- 物理的制約への防波堤：厳密な型サニタイズ ---
        for c in display_cols:
            if c not in st.session_state.df_main.columns:
                if c == '確認':
                    st.session_state.df_main[c] = False
                elif c in ['数量', 'NET', '原単価', '掛率', '売単価', '見積金額', '荒利率']:
                    st.session_state.df_main[c] = 0.0
                else:
                    st.session_state.df_main[c] = ""
                    
        for c in ['大項目', '中項目', '名称', '規格', '単位', '備考', 'sort_key']:
            st.session_state.df_main[c] = st.session_state.df_main[c].fillna('').astype(str)
            
        for c in ['数量', 'NET', '原単価', '掛率', '売単価', '見積金額', '荒利率']:
            st.session_state.df_main[c] = pd.to_numeric(st.session_state.df_main[c], errors='coerce').fillna(0.0)
            
        st.session_state.df_main['確認'] = st.session_state.df_main['確認'].astype(bool)
        # ------------------------------------------------

        # 消えていた column_config の復元
        column_config = {
            "確認": st.column_config.CheckboxColumn("確認", width="small"),
            "大項目": st.column_config.TextColumn("大項目", width="medium"),
            "中項目": st.column_config.TextColumn("中項目", width="medium"),
            "名称": st.column_config.TextColumn("名称", width="large", required=True),
            "規格": st.column_config.TextColumn("規格", width="medium"),
            "数量": st.column_config.NumberColumn("数量", min_value=0, step=0.1, format="%.2f"),
            "単位": st.column_config.TextColumn("単位", width="small"),
            "NET": st.column_config.NumberColumn("NET(参考)", format="¥%d", width="small"),
            "原単価": st.column_config.NumberColumn("原単価(当方)", format="¥%d", step=100, width="small"),
            "掛率": st.column_config.NumberColumn("掛率", min_value=0.0, max_value=2.0, step=0.01, format="%.2f", width="small"),
            "売単価": st.column_config.NumberColumn("売単価", format="¥%d", disabled=True),
            "見積金額": st.column_config.NumberColumn("見積金額", format="¥%d", disabled=True),
            "荒利率": st.column_config.NumberColumn("粗利率", format="%.1f%%", disabled=True),
            "備考": st.column_config.TextColumn("備考", width="medium"),
            "sort_key": st.column_config.TextColumn("ID", disabled=True, width="small")
        }

        edited_df = st.data_editor(
            st.session_state.df_main[display_cols],
            column_config=column_config,
            num_rows="dynamic",
            use_container_width=True,
            height=600,
            key="editor"
        )

        if not edited_df.equals(st.session_state.df_main[display_cols]):
            st.session_state.df_main = calculate_dataframe(edited_df, st.session_state.overhead_rates_map)
            st.rerun()
    else:
        st.info("👈 サイドバーからスプレッドシートを読み込んでください。")

if __name__ == "__main__":
    main()
