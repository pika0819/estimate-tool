# Step 1: ライブラリ読み込みとUI初期設定処理 #
import streamlit as st
import pandas as pd
import re
import urllib.parse
from datetime import datetime
from pdf_exporter import EstimatePDFGenerator

st.set_page_config(page_title="見積書PDF発行", layout="centered")
st.title("📄 見積書 PDF自動生成システム")

# Step 2: URLクエリパラメータの取得（シームレス自動発火ロジック） #
# ユーザーがGAS経由で飛んできた場合、URLから自動的にIDを抽出します
query_params = st.query_params
auto_id = query_params.get("id", None)

# Step 3: データ処理・PDF生成関数の定義 #
def process_and_generate_pdf(ss_id):
    try:
        with st.spinner("📥 データを取得中..."):
            url_mitsumori = f"https://docs.google.com/spreadsheets/d/{ss_id}/gviz/tq?tqx=out:csv&sheet={urllib.parse.quote('見積り集計表')}"
            url_info = f"https://docs.google.com/spreadsheets/d/{ss_id}/gviz/tq?tqx=out:csv&headers=0&sheet={urllib.parse.quote('現場情報')}"

            # 見積り集計表の処理
            df_raw = pd.read_csv(url_mitsumori, header=None, na_filter=False)
            header_idx = -1
            for i, row in enumerate(df_raw.values):
                row_clean = [re.sub(r'[\s\u3000]+', '', str(c)) for c in row]
                if '見積金額' in row_clean or '大項目' in row_clean:
                    header_idx = i; raw_cols = row_clean; break

            if header_idx == -1: raise ValueError("見積り項目が見つかりません。")

            df_main = pd.DataFrame(df_raw.values[header_idx + 1:], columns=raw_cols)
            cols = pd.Series(df_main.columns)
            for dup in cols[cols.duplicated()].unique(): 
                cols[cols == dup] = [f"{dup}_{i}" if i != 0 else dup for i in range(sum(cols == dup))]
            df_main.columns = cols

            # 現場情報の処理
            info_raw = pd.read_csv(url_info, header=None, na_filter=False).astype(str)
            def get_info_direct(target_key):
                clean_target = target_key.replace(" ", "").replace("　", "")
                for r in range(len(info_raw)):
                    key_in_sheet = str(info_raw.iloc[r, 0]).replace(" ", "").replace("　", "")
                    if clean_target in key_in_sheet:
                        val = str(info_raw.iloc[r, 1]).strip()
                        return val if val and val.lower() != 'nan' else ""
                return ""

            params = {
                'client_name': get_info_direct('施主名'), 'project_name': get_info_direct('工事名'),
                'location': get_info_direct('工事場所'), 'term': get_info_direct('工期'),
                'expiry': get_info_direct('見積もり書有効期限'), 'date': get_info_direct('発行日') or datetime.today().strftime('%Y/%m/%d'),
                'company_name': get_info_direct('会社名'), 'ceo': get_info_direct('代表取締役'),
                'address': get_info_direct('住所'), 'phone': get_info_direct('電話番号'),
                'fax': get_info_direct('FAX番号'), 'spec': get_info_direct('見積もり仕様') or "初版"
            }

        with st.spinner("📄 PDFを構築中..."):
            gen = EstimatePDFGenerator(df_main, params)
            pdf_buffer = gen.generate()
            p_name = params['project_name'] if params['project_name'] else "工事名不明"
            fname = f"{re.sub(r'[\\/*?:\"<>|]', '_', p_name)}_{params['spec']}.pdf"
            
            # 実務的エッジケース: 成功時はダウンロードボタンのみを大きく表示
            st.success("✅ PDFの準備が完了しました！")
            st.download_button(
                label="📥 PDFをダウンロード",
                data=pdf_buffer,
                file_name=fname,
                mime="application/pdf"
            )
    except Exception as e:
        st.error(f"❌ エラーが発生しました: {e}")


# Step 4: 実行分岐ロジック #
# GASから遷移してきた場合は自動実行、直接URLを開いた場合は手動入力画面を表示
if auto_id:
    st.info("🔄 スプレッドシートから連携されました。自動処理を開始します...")
    process_and_generate_pdf(auto_id)
else:
    st.write("スプレッドシートのURLを入力して「PDFを作成」を押してください。")
    base_url = st.text_input("スプレッドシートURL:")
    if st.button("PDFを作成", type="primary"):
        if not base_url:
            st.warning("⚠️ URLを入力してください。")
        else:
            match = re.search(r'/d/([a-zA-Z0-9-_]+)', base_url)
            if not match:
                st.error("❌ エラー: 正しいURLを認識できませんでした。")
            else:
                process_and_generate_pdf(match.group(1))
