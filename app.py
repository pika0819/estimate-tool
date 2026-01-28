import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import io
import re

# ---------------------------------------------------------
# ■ 設定エリア（固定値は廃止！）
# ---------------------------------------------------------
SHEET_NAME = "T_見積入力" # シート名は固定でOK（テンプレート運用だと思うので）

# フォント設定
FONT_FILE = "ipaexg.ttf"
FONT_NAME = "IPAexGothic"

# ---------------------------------------------------------
# 1. データ取得（URLから動的に接続）
# ---------------------------------------------------------
def get_data_from_url(sheet_url):
    try:
        # URLからIDを抽出するロジック
        # (https://docs.google.com/spreadsheets/d/xxxxx/edit...) の xxxxx を抜く
        match = re.search(r"/d/([a-zA-Z0-9-_]+)", sheet_url)
        if not match:
            st.error("URLの形式が正しくありません。正しいスプレッドシートのURLを入力してください。")
            return None
        spreadsheet_key = match.group(1)

        # 認証
        scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
        creds_dict = dict(st.secrets["gcp_service_account"])
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        client = gspread.authorize(creds)
        
        # シートを開く
        sheet = client.open_by_key(spreadsheet_key).worksheet(SHEET_NAME)
        data = sheet.get_all_values()
        
        # DataFrame化
        df = pd.DataFrame(data[1:], columns=data[0])
        return df
    except gspread.exceptions.WorksheetNotFound:
        st.error(f"シート「{SHEET_NAME}」が見つかりません。スプレッドシートの中にこの名前のシートがあるか確認してください。")
        return None
    except Exception as e:
        st.error(f"読み込みエラー: {e}")
        return None

# ---------------------------------------------------------
# 2. PDF生成エンジン (中身は変更なし)
# ---------------------------------------------------------
def create_estimate_pdf(df):
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    
    try:
        pdfmetrics.registerFont(TTFont(FONT_NAME, FONT_FILE))
    except:
        st.warning(f"フォントファイル({FONT_FILE})が見つかりません。")
        return None

    # --- レイアウト設定 ---
    x_base = 15 * mm
    y_start = height - 50 * mm
    line_height = 5.5 * mm
    
    col_x = {
        'name': x_base + 5 * mm,
        'spec': x_base + 70 * mm,
        'qty':  x_base + 115 * mm,
        'unit': x_base + 128 * mm,
        'price': x_base + 150 * mm,
        'amt':   x_base + 180 * mm
    }

    y = y_start
    page_num = 1
    
    prev_L1 = None; prev_L2 = None; prev_L3 = None; prev_L4 = None

    try:
        total_amount = df['(自)金額'].astype(str).str.replace(r'[¥,]', '', regex=True).replace('', '0').astype(float).sum()
    except:
        total_amount = 0

    def draw_header():
        nonlocal y
        y = height - 40 * mm
        c.setFont(FONT_NAME, 18)
        c.drawString(width/2 - 20*mm, height - 25*mm, "御 見 積 書")
        c.setFont(FONT_NAME, 11)
        c.drawString(x_base, height - 25*mm, "〇〇 様")
        c.setFont(FONT_NAME, 10)
        c.drawRightString(width - 15*mm, height - 20*mm, "株式会社 〇〇工務店")
        c.setFont(FONT_NAME, 12)
        c.drawString(x_base, height - 35*mm, f"御見積合計金額： ￥{int(total_amount):,}- (税込)")
        c.setLineWidth(1)
        c.line(x_base, y + 2*mm, width - 15*mm, y + 2*mm)
        c.setFont(FONT_NAME, 9)
        c.drawString(col_x['name'], y, "名　称")
        c.drawString(col_x['spec'], y, "規　格")
        c.drawString(col_x['qty'], y, "数 量")
        c.drawString(col_x['unit'], y, "単位")
        c.drawString(col_x['price'], y, "単 価")
        c.drawString(col_x['amt'], y, "金 額")
        c.line(x_base, y - 2*mm, width - 15*mm, y - 2*mm)
        y -= line_height * 1.5

    draw_header()

    for index, row in df.iterrows():
        if y < 20 * mm:
            c.setFont(FONT_NAME, 9)
            c.drawCentredString(width/2, 10*mm, f"- {page_num} -")
            c.showPage()
            page_num += 1
            draw_header()
            prev_L1 = None; prev_L2 = None; prev_L3 = None; prev_L4 = None

        l1 = str(row['大項目']); l2 = str(row['中項目']); l3 = str(row['小項目']); l4 = str(row['部分項目'])
        name = str(row['名称']); spec = str(row['規格']); unit = str(row['単位'])
        
        qty_raw = str(row['数量']).replace(',', '')
        qty = f"{float(qty_raw):,.2f}" if qty_raw and qty_raw != '' else ""
        price_raw = str(row['(自)単価']).replace('¥', '').replace(',', '')
        price = f"{int(float(price_raw)):,}" if price_raw and price_raw != '' else ""
        amt_raw = str(row['(自)金額']).replace('¥', '').replace(',', '')
        amt = f"{int(float(amt_raw)):,}" if amt_raw and amt_raw != '' else ""

        if l1 != prev_L1 and l1 != "":
            y -= 2*mm
            c.setFont(FONT_NAME, 11)
            c.drawString(x_base, y, f"■ {l1}")
            c.line(x_base, y - 1*mm, width - 15*mm, y - 1*mm)
            y -= line_height
            prev_L1 = l1; prev_L2 = None; prev_L3 = None; prev_L4 = None

        if l2 != prev_L2 and l2 != "":
            c.setFont(FONT_NAME, 10)
            c.drawString(x_base + 5*mm, y, f"● {l2}")
            y -= line_height
            prev_L2 = l2; prev_L3 = None; prev_L4 = None

        if l3 != prev_L3 and l3 != "":
            c.setFont(FONT_NAME, 9)
            c.drawString(x_base + 10*mm, y, f"・ {l3}")
            y -= line_height
            prev_L3 = l3; prev_L4 = None

        if l4 != prev_L4 and l4 != "":
            c.setFont(FONT_NAME, 9)
            c.drawString(x_base + 15*mm, y, f"- {l4}")
            y -= line_height
            prev_L4 = l4

        if name != "":
            c.setFont(FONT_NAME, 9)
            indent = 20 * mm
            c.drawString(col_x['name'] + 15*mm, y, name)
            if spec:
                c.setFont(FONT_NAME, 8)
                c.drawString(col_x['spec'], y, spec)
                c.setFont(FONT_NAME, 9)
            c.drawRightString(col_x['qty'], y, qty)
            c.drawCentredString(col_x['unit'], y, unit)
            c.drawRightString(col_x['price'], y, price)
            c.drawRightString(col_x['amt'], y, amt)
            y -= line_height

    c.drawCentredString(width/2, 10*mm, f"- {page_num} -")
    c.save()
    buffer.seek(0)
    return buffer

# ---------------------------------------------------------
# 3. Streamlit UI（入力フォーム化）
# ---------------------------------------------------------
st.title("📄 自動見積書作成システム")

st.markdown("""
### 手順
1. 見積入力済みの **スプレッドシートのURL** をコピーしてください。
2. 下の欄に貼り付けて「読み込む」ボタンを押してください。
""")

# URL入力欄を作成
sheet_url = st.text_input("スプレッドシートのURL", placeholder="https://docs.google.com/spreadsheets/d/...")

if st.button("スプレッドシートを読み込む"):
    if not sheet_url:
        st.warning("URLを入力してください。")
    else:
        with st.spinner('データを取得中...'):
            df = get_data_from_url(sheet_url)
            
            if df is not None:
                st.success("✅ 読み込み成功！")
                st.dataframe(df.head()) # 確認用

                # PDF作成
                pdf_bytes = create_estimate_pdf(df)
                if pdf_bytes:
                    st.download_button(
                        label="📥 見積書PDFをダウンロード",
                        data=pdf_bytes,
                        file_name="見積書.pdf",
                        mime="application/pdf"
                    )
