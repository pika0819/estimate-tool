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

# ---------------------------------------------------------
# ■ 設定エリア
# ---------------------------------------------------------
# あなたのスプレッドシートのURLから、d/〇〇/edit の「〇〇」の部分（ID）をここに貼る
SPREADSHEET_KEY = "ここにスプレッドシートIDを貼り付けてください"
SHEET_NAME = "T_見積入力"

# フォント設定（同階層に ipaexg.ttf がある前提）
FONT_FILE = "ipaexg.ttf"
FONT_NAME = "IPAexGothic"

# ---------------------------------------------------------
# 1. データ取得（スプレッドシート接続）
# ---------------------------------------------------------
def get_data_from_gsheet():
    # StreamlitのSecretsから鍵情報を取得（GitHub/Streamlit Cloud用）
    # ※ローカルで動かす場合は、jsonファイルを指定する方法に書き換えます
    try:
        scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
        # st.secrets 経由で認証情報を作る
        creds_dict = dict(st.secrets["gcp_service_account"])
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        client = gspread.authorize(creds)
        
        sheet = client.open_by_key(SPREADSHEET_KEY).worksheet(SHEET_NAME)
        data = sheet.get_all_values()
        
        # 1行目をヘッダーとしてDataFrame化
        df = pd.DataFrame(data[1:], columns=data[0])
        return df
    except Exception as e:
        st.error(f"スプレッドシートの読み込みに失敗しました: {e}")
        return None

# ---------------------------------------------------------
# 2. PDF生成エンジン (ReportLab)
# ---------------------------------------------------------
def create_estimate_pdf(df):
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    
    # フォント登録
    try:
        pdfmetrics.registerFont(TTFont(FONT_NAME, FONT_FILE))
    except:
        st.warning(f"フォントファイル({FONT_FILE})が見つかりません。")
        return None

    # --- レイアウト設定 ---
    x_base = 15 * mm
    y_start = height - 50 * mm
    line_height = 5.5 * mm # 行間を少し詰めました
    
    # 列位置（X座標）
    col_x = {
        'name': x_base + 5 * mm,   # 名称
        'spec': x_base + 70 * mm,  # 規格
        'qty':  x_base + 115 * mm, # 数量
        'unit': x_base + 128 * mm, # 単位
        'price': x_base + 150 * mm, # 単価
        'amt':   x_base + 180 * mm  # 金額
    }

    # 変数初期化
    y = y_start
    page_num = 1
    
    # 階層判定用
    prev_L1 = None # 大
    prev_L2 = None # 中
    prev_L3 = None # 小
    prev_L4 = None # 部分

    # 金額計算（Q列：(自)金額 を合計）
    # ※カンマや円マークを除去して計算
    try:
        total_amount = df['(自)金額'].astype(str).str.replace(r'[¥,]', '', regex=True).replace('', '0').astype(float).sum()
    except:
        total_amount = 0

    # --- ヘッダー描画関数 ---
    def draw_header():
        nonlocal y
        y = height - 40 * mm
        
        c.setFont(FONT_NAME, 18)
        c.drawString(width/2 - 20*mm, height - 25*mm, "御 見 積 書")
        
        # 宛名・自社名（仮）
        c.setFont(FONT_NAME, 11)
        c.drawString(x_base, height - 25*mm, "〇〇 様")
        
        c.setFont(FONT_NAME, 10)
        c.drawRightString(width - 15*mm, height - 20*mm, "株式会社 〇〇工務店")
        c.drawRightString(width - 15*mm, height - 25*mm, "長野県木曽郡〇〇町...")

        # 合計金額表示
        c.setFont(FONT_NAME, 12)
        c.drawString(x_base, height - 35*mm, f"御見積合計金額： ￥{int(total_amount):,}- (税込)")
        
        # 表ヘッダー線
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

    # 初回ヘッダー
    draw_header()

    # --- データ行ループ ---
    for index, row in df.iterrows():
        # 改ページ判定
        if y < 20 * mm:
            c.setFont(FONT_NAME, 9)
            c.drawCentredString(width/2, 10*mm, f"- {page_num} -")
            c.showPage()
            page_num += 1
            draw_header()
            # 改ページ後は見出しをリセット（再度表示させたい場合はここを調整）
            prev_L1 = None; prev_L2 = None; prev_L3 = None; prev_L4 = None

        # 値の取得（19列構成に対応）
        # A:大, B:中, C:小, D:部分, E:名称, F:規格, L:単位, O:単価, Q:金額
        l1 = str(row['大項目'])
        l2 = str(row['中項目'])
        l3 = str(row['小項目'])
        l4 = str(row['部分項目'])
        name = str(row['名称'])
        spec = str(row['規格'])
        unit = str(row['単位'])
        
        # 数値の整形
        qty_raw = str(row['数量']).replace(',', '')
        qty = f"{float(qty_raw):,.2f}" if qty_raw and qty_raw != '' else ""
        
        price_raw = str(row['(自)単価']).replace('¥', '').replace(',', '')
        price = f"{int(float(price_raw)):,}" if price_raw and price_raw != '' else ""
        
        amt_raw = str(row['(自)金額']).replace('¥', '').replace(',', '')
        amt = f"{int(float(amt_raw)):,}" if amt_raw and amt_raw != '' else ""

        # --- 4段階階層ロジック ---
        
        # Level 1: 大項目
        if l1 != prev_L1 and l1 != "":
            y -= 2*mm
            c.setFont(FONT_NAME, 11)
            c.drawString(x_base, y, f"■ {l1}")
            c.line(x_base, y - 1*mm, width - 15*mm, y - 1*mm) # 下線
            y -= line_height
            prev_L1 = l1
            prev_L2 = None; prev_L3 = None; prev_L4 = None # リセット

        # Level 2: 中項目
        if l2 != prev_L2 and l2 != "":
            c.setFont(FONT_NAME, 10)
            c.drawString(x_base + 5*mm, y, f"● {l2}")
            y -= line_height
            prev_L2 = l2
            prev_L3 = None; prev_L4 = None

        # Level 3: 小項目
        if l3 != prev_L3 and l3 != "":
            c.setFont(FONT_NAME, 9)
            c.drawString(x_base + 10*mm, y, f"・ {l3}")
            y -= line_height
            prev_L3 = l3
            prev_L4 = None

        # Level 4: 部分項目（NEW!）
        if l4 != prev_L4 and l4 != "":
            c.setFont(FONT_NAME, 9)
            c.drawString(x_base + 15*mm, y, f"- {l4}")
            y -= line_height
            prev_L4 = l4

        # 明細行描画
        # 名称が空ならスキップ（見出しだけの行かもしれないので）
        if name != "":
            c.setFont(FONT_NAME, 9)
            
            indent = 20 * mm
            c.drawString(col_x['name'] + 15*mm, y, name) # 名称
            
            # 規格（長すぎる場合はフォントを小さくする等の処理を入れるとGood）
            if spec:
                c.setFont(FONT_NAME, 8)
                c.drawString(col_x['spec'], y, spec)
                c.setFont(FONT_NAME, 9)

            c.drawRightString(col_x['qty'], y, qty)
            c.drawCentredString(col_x['unit'], y, unit)
            c.drawRightString(col_x['price'], y, price)
            c.drawRightString(col_x['amt'], y, amt)
            
            y -= line_height

    # 最終ページ番号
    c.drawCentredString(width/2, 10*mm, f"- {page_num} -")
    
    c.save()
    buffer.seek(0)
    return buffer

# ---------------------------------------------------------
# 3. Streamlit UI
# ---------------------------------------------------------
st.title("📄 自動見積書作成システム")

if st.button("スプレッドシートからデータを読み込む"):
    with st.spinner('データを取得中...'):
        df = get_data_from_gsheet()
        
        if df is not None:
            st.success("データの読み込みに成功しました！")
            st.dataframe(df.head()) # 確認用表示
            
            # PDF作成
            pdf_bytes = create_estimate_pdf(df)
            if pdf_bytes:
                st.download_button(
                    label="📥 見積書PDFをダウンロード",
                    data=pdf_bytes,
                    file_name="見積書.pdf",
                    mime="application/pdf"
                )