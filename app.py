import streamlit as st
import uuid
from datetime import datetime
from data_utils import load_data, calculate_dataframe, save_data
from pdf_exporter import EstimatePDFGenerator

def main():
    # Step 1: 画面構成とスタイルの設定 #
    st.set_page_config(layout="wide", page_title="見積コントロールセンター")
    st.markdown("""
    <style>
        .stApp { font-size: 1.1rem; }
        .metric-label { font-size: 1.2rem; font-weight: bold; color: #555; }
        .metric-value-lg { font-size: 2.2rem; font-weight: bold; color: #1f77b4; line-height: 1.2; }
        div[data-testid="stSidebar"] { min-width: 350px; }
    </style>
    """, unsafe_allow_html=True)

    # Step 2: セッション状態の初期化 #
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
                    secrets = dict(st.secrets["gcp_service_account"])
                    with st.spinner("最新データを取得中..."):
                        df, info = load_data(input_url, secrets)
                        if df is not None:
                            if 'sort_key' not in df.columns:
                                df['sort_key'] = [str(uuid.uuid4()) for _ in range(len(df))]
                            st.session_state.info_dict = info
                            st.session_state.sheet_url = input_url
                            st.session_state.df_main = calculate_dataframe(df, st.session_state.overhead_rates_map)
                            st.rerun()
                except Exception as e:
                    st.error(f"接続エラー: {e}")

        # Step 3: 諸経費設定と集計表示 #
        if st.session_state.df_main is not None:
            st.subheader("💰 諸経費設定")
            df_cur = st.session_state.df_main
            overhead_rows = df_cur[df_cur['大項目'] == '諸経費']
            if not overhead_rows.empty:
                rates_updated = False
                for _, row in overhead_rows.iterrows():
                    s_key = str(row['sort_key'])
                    current_rate = st.session_state.overhead_rates_map.get(s_key, 0.0)
                    new_rate = st.number_input(f"{row['名称']} (%)", 0.0, 100.0, float(current_rate), 0.5, key=f"rate_{s_key}")
                    if new_rate != current_rate:
                        st.session_state.overhead_rates_map[s_key] = new_rate
                        rates_updated = True
                if rates_updated:
                    st.session_state.df_main = calculate_dataframe(df_cur, st.session_state.overhead_rates_map)
                    st.rerun()

            total_est = df_cur['見積金額'].sum()
            st.markdown(f'<div class="metric-label">見積総額 (税抜)</div><div class="metric-value-lg">¥{total_est:,.0f}</div>', unsafe_allow_html=True)
            
            if st.button("💾 保存", type="primary", use_container_width=True):
                if save_data(st.session_state.sheet_url, dict(st.secrets["gcp_service_account"]), st.session_state.df_main):
                    st.success("保存完了")

    # Step 4: メインエディタ（型保証を適用） #
    if st.session_state.df_main is not None:
        display_cols = ['確認', '大項目', '中項目', '名称', '規格', '数量', '単位', 'NET', '原単価', '掛率', '売単価', '見積金額', '荒利率', '備考', 'sort_key']
        
        # 物理的制約への防波堤：表示直前に型を強制固定
        for c in display_cols:
            if c not in st.session_state.df_main.columns:
                st.session_state.df_main[c] = ""
            if c in ['大項目', '中項目', '名称', '規格', '単位', '備考', 'sort_key']:
                st.session_state.df_main[c] = st.session_state.df_main[c].fillna('').astype(str)

        edited_df = st.data_editor(
            st.session_state.df_main[display_cols],
            num_rows="dynamic",
            use_container_width=True,
            key="editor"
        )

        if not edited_df.equals(st.session_state.df_main[display_cols]):
            st.session_state.df_main = calculate_dataframe(edited_df, st.session_state.overhead_rates_map)
            st.rerun()

if __name__ == "__main__":
    main()
