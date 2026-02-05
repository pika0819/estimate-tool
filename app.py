import streamlit as st
import uuid
from datetime import datetime
from data_utils import load_data, calculate_dataframe, save_data
from pdf_exporter import EstimatePDFGenerator

def main():
    st.set_page_config(layout="wide", page_title="見積コントロールセンター")

    # CSS設定
    st.markdown("""
    <style>
        .stApp { font-size: 1.1rem; }
        .metric-label { font-size: 1.2rem; font-weight: bold; color: #555; }
        .metric-value-lg { font-size: 2.2rem; font-weight: bold; color: #1f77b4; line-height: 1.2; }
        .metric-value-md { font-size: 1.5rem; font-weight: bold; color: #333; }
        .total-box { padding: 15px; background-color: #f0f2f6; border-radius: 10px; margin-bottom: 20px; }
        div[data-testid="stSidebar"] { min-width: 350px; }
    </style>
    """, unsafe_allow_html=True)

    # Session Init
    if 'df_main' not in st.session_state: st.session_state.df_main = None
    if 'info_dict' not in st.session_state: st.session_state.info_dict = {}
    if 'sheet_url' not in st.session_state: st.session_state.sheet_url = ""

    # ------------------
    # Sidebar
    # ------------------
    with st.sidebar:
        st.title("🛠️ 見積管理盤")
        
        with st.expander("📂 データ接続設定", expanded=(st.session_state.df_main is None)):
            input_url = st.text_input("スプレッドシートURL", value=st.session_state.sheet_url)
            if st.button("データを読み込む"):
                try:
                    secrets = dict(st.secrets["gcp_service_account"])
                    with st.spinner("シートから最新データを取得中..."):
                        df, info = load_data(input_url, secrets)
                        if df is not None:
                            if 'sort_key' not in df.columns:
                                df['sort_key'] = [str(uuid.uuid4()) for _ in range(len(df))]
                            
                            st.session_state.df_main = calculate_dataframe(df)
                            st.session_state.info_dict = info
                            st.session_state.sheet_url = input_url
                            st.success("読み込み完了")
                            st.rerun()
                except Exception as e:
                    st.error(f"接続エラー: {e}")

        st.markdown("---")

        if st.session_state.df_main is not None:
            df_cur = st.session_state.df_main
            
            # 数値表示用計算
            total_kouji = df_cur['見積金額'].sum()
            total_cost = df_cur['実行金額'].sum()
            overhead = total_kouji * 0.15
            total_est = total_kouji + overhead
            tax = total_est * 0.1
            grand_total = total_est + tax
            profit = total_kouji - total_cost
            margin = (profit / total_kouji * 100) if total_kouji > 0 else 0

            st.markdown('<div class="metric-label">工事価格 (小計)</div>', unsafe_allow_html=True)
            st.markdown(f'<div class="metric-value-md">¥{total_kouji:,.0f}</div>', unsafe_allow_html=True)
            st.markdown('<div class="metric-label">諸経費 (15%)</div>', unsafe_allow_html=True)
            st.info(f"¥{overhead:,.0f}")
            st.markdown('<div class="metric-label">見積総額 (税抜)</div>', unsafe_allow_html=True)
            st.markdown(f'<div class="metric-value-lg">¥{total_est:,.0f}</div>', unsafe_allow_html=True)
            st.write(f"消費税(10%): ¥{tax:,.0f}")
            st.markdown(f"### 税込合計: ¥{grand_total:,.0f}")
            st.markdown("---")
            st.metric("現場想定粗利", f"¥{profit:,.0f}", f"{margin:.1f}%")
            
            st.markdown("---")
            st.subheader("操作メニュー")
            
            if st.button("💾 シートに保存・更新", type="primary", use_container_width=True):
                secrets = dict(st.secrets["gcp_service_account"])
                with st.spinner("Google Sheetsへ書き込み中..."):
                    if save_data(st.session_state.sheet_url, secrets, st.session_state.df_main):
                        st.success("保存しました！")
                    else:
                        st.error("保存に失敗しました。")

            if st.button("📄 PDFを発行する", use_container_width=True):
                params = {
                    'client_name': st.session_state.info_dict.get('施主名', ''),
                    'project_name': st.session_state.info_dict.get('工事名', ''),
                    'location': st.session_state.info_dict.get('工事場所', ''),
                    'term': st.session_state.info_dict.get('工期', ''),
                    'expiry': st.session_state.info_dict.get('見積もり書有効期限', ''),
                    'date': st.session_state.info_dict.get('発行日', datetime.today().strftime('%Y/%m/%d')),
                    'company_name': st.session_state.info_dict.get('会社名', ''),
                    'ceo': st.session_state.info_dict.get('代表取締役', ''),
                    'address': st.session_state.info_dict.get('住所', ''),
                    'phone': st.session_state.info_dict.get('電話番号', ''),
                    'fax': st.session_state.info_dict.get('FAX番号', '')
                }
                gen = EstimatePDFGenerator(st.session_state.df_main, params)
                pdf_data = gen.generate()
                fname = f"{params['date'].replace('/','')}_{params['client_name']}_{params['project_name']}.pdf"
                st.download_button("📥 PDFをダウンロード", pdf_data, fname, "application/pdf", type="secondary")

    # ------------------
    # Main Editor
    # ------------------
    if st.session_state.df_main is not None:
        st.subheader(f"📋 見積明細: {st.session_state.info_dict.get('工事名', '未設定')}")
        
        column_config = {
            "確認": st.column_config.CheckboxColumn("確認", width="small"),
            "大項目": st.column_config.TextColumn("大項目", width="medium"),
            "中項目": st.column_config.TextColumn("中項目", width="medium"),
            "名称": st.column_config.TextColumn("名称", width="large", required=True),
            "規格": st.column_config.TextColumn("規格", width="medium"),
            "数量": st.column_config.NumberColumn("数量", min_value=0, step=0.1, format="%.2f"),
            "単位": st.column_config.TextColumn("単位", width="small"),
            "NET": st.column_config.NumberColumn("NET(参考)", format="¥%d", width="small", help="仕入れ値"),
            "原単価": st.column_config.NumberColumn("原単価(当方)", format="¥%d", step=100, width="small"),
            "掛率": st.column_config.NumberColumn("掛率", min_value=0.0, max_value=2.0, step=0.01, format="%.2f", width="small"),
            "売単価": st.column_config.NumberColumn("売単価", format="¥%d", disabled=True),
            "見積金額": st.column_config.NumberColumn("見積金額", format="¥%d", disabled=True),
            "(自)荒利率": st.column_config.NumberColumn("粗利率", format="%.1f%%", disabled=True),
            "備考": st.column_config.TextColumn("備考", width="medium"),
            "sort_key": st.column_config.TextColumn("ID", disabled=True, width="small")
        }

        display_cols = [
            '確認', '大項目', '中項目', '名称', '規格', '数量', '単位',
            'NET', '原単価', '掛率', '売単価', '見積金額', '(自)荒利率', '備考', 'sort_key'
        ]
        
        for c in display_cols:
            if c not in st.session_state.df_main.columns:
                st.session_state.df_main[c] = ""

        edited_df = st.data_editor(
            st.session_state.df_main[display_cols],
            column_config=column_config,
            num_rows="dynamic",
            use_container_width=True,
            height=600,
            key="editor"
        )

        if not edited_df.equals(st.session_state.df_main[display_cols]):
            recalc_df = calculate_dataframe(edited_df)
            st.session_state.df_main = recalc_df
            st.rerun()
            
    else:
        st.info("👈 左側のサイドバーからスプレッドシートのURLを入力してデータを読み込んでください。")

if __name__ == "__main__":
    main()
