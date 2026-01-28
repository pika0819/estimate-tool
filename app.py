import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib import colors
import io
import re
from datetime import datetime

# ---------------------------------------------------------
# ■ 設定エリア
# ---------------------------------------------------------
SHEET_NAME = "T_見積入力" 
FONT_FILE = "ipaexg.ttf"
FONT_NAME = "IPAexGothic"

# ---------------------------------------------------------
# 1. データ取得
# ---------------------------------------------------------
def get_data_from_url(sheet_url):
    try:
        match = re.search(r"/d/([a-zA-Z0-9-_]+)", sheet_url)
        if not match:
            st.error("URLの形式が正しくありません。")
            return None
        spreadsheet_key = match.group(1)

        scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
        creds_dict = dict(st.secrets["gcp_service_account"])
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        client = gspread.authorize(creds)
        
        sheet = client.open_by_key(spreadsheet_key).worksheet(SHEET_NAME)
        data = sheet.get_all_values()
        df = pd.DataFrame(data[1:], columns=data[0])
        return df
    except Exception as e:
        st.error(f"読み込みエラー: {e}")
        return None

# ---------------------------------------------------------
# 2. PDF生成エンジン (表紙 + 明細)
# ---------------------------------------------------------
def create_estimate_pdf(df, params):
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=landscape(A4))
    width, height = landscape(A4)
    
    try:
        pdfmetrics.registerFont(TTFont(FONT_NAME, FONT_FILE))
    except:
        st.warning(f"フォントファイル({FONT_FILE})が見つかりません。")
        return None

    # --- 数値変換ヘルパー ---
    def parse_amount(val):
        try:
            return float(str(val).replace('¥', '').replace(',', ''))
        except:
            return 0.0

    # 合計金額計算
    total_grand = df['(自)金額'].apply(parse_amount).sum()

    # ==========================================
    # 1ページ目：表紙 (Cover Page)
    # ==========================================
    def draw_cover():
        # タイトル「御 見 積 書」
        c.setFont(FONT_NAME, 32)
        c.setFillColor(colors.darkblue) # 青文字
        title = "御   見   積   書"
        title_w = c.stringWidth(title, FONT_NAME, 32)
        c.drawCentredString(width/2, height - 50*mm, title)
        
        # 二重線 (タイトル下)
        line_width = title_w + 40*mm
        line_x = (width - line_width) / 2
        line_y = height - 55*mm
        c.setStrokeColor(colors.darkblue)
        c.setLineWidth(1)
        c.line(line_x, line_y, line_x + line_width, line_y) # 上線
        c.line(line_x, line_y - 1.5*mm, line_x + line_width, line_y - 1.5*mm) # 下線
        
        c.setFillColor(colors.black) # 黒に戻す

        # 宛名 (施主名)
        c.setFont(FONT_NAME, 24)
        c.drawCentredString(width/2, height - 90*mm, f"{params['client_name']}  様")
        c.setLineWidth(0.5)
        c.line(width/2 - 60*mm, height - 92*mm, width/2 + 60*mm, height - 92*mm) # 下線

        # 工事名
        c.setFont(FONT_NAME, 18)
        c.drawCentredString(width/2, height - 120*mm, f"工 事 名 ：  {params['project_name']}")
        c.line(width/2 - 60*mm, height - 122*mm, width/2 + 60*mm, height - 122*mm)

        # 見積金額 (ドカンと)
        c.setFont(FONT_NAME, 22)
        amount_str = f"¥ {int(total_grand):,}-  (税込)"
        c.drawCentredString(width/2, height - 150*mm, f"見積金額 ：  {amount_str}")
        c.line(width/2 - 60*mm, height - 152*mm, width/2 + 60*mm, height - 152*mm)

        # 日付 (左下)
        c.setFont(FONT_NAME, 12)
        c.drawString(30*mm, 40*mm, f"日付： {params['date']}")

        # 会社情報 (右下)
        x_company = width - 90*mm
        y_company = 55*mm
        c.setFont(FONT_NAME, 14)
        c.drawString(x_company, y_company, params['company_name'])
        c.setFont(FONT_NAME, 11)
        c.drawString(x_company, y_company - 8*mm, f"代表取締役  {params['ceo']}")
        c.setFont(FONT_NAME, 10)
        c.drawString(x_company, y_company - 15*mm, f"〒 {params['address']}")
        c.drawString(x_company, y_company - 20*mm, f"TEL: {params['phone']}")

        # 簡易印鑑 (赤丸に「印」)
        c.setStrokeColor(colors.red)
        c.setFillColor(colors.red)
        c.setLineWidth(1.5)
        stamp_x = x_company + 65*mm
        stamp_y = y_company - 5*mm
        stamp_r = 9*mm
        c.circle(stamp_x, stamp_y, stamp_r, stroke=1, fill=0)
        c.setFont(FONT_NAME, 12)
        c.drawCentredString(stamp_x, stamp_y - 4*mm, "印") # 文字位置はフォントにより微調整

        c.showPage() # 改ページ

    draw_cover()

    # ==========================================
    # 2ページ目以降：明細 (Detail Pages)
    # ==========================================
    
    # --- レイアウト設定 ---
    x_base = 15 * mm
    col_widths = {
        'name': 85 * mm, 'spec': 60 * mm, 'qty': 20 * mm, 
        'unit': 15 * mm, 'price': 30 * mm, 'amt': 35 * mm, 'rem': 25 * mm
    }
    # 座標計算
    col_x = {}
    cur_x = x_base
    for k, w in col_widths.items():
        col_x[k] = cur_x
        cur_x += w
    right_edge = cur_x
    
    header_height = 8 * mm
    row_height = 7 * mm
    y_start = height - 30 * mm # 明細ページの開始位置（少し上から）
    y = y_start
    page_num = 1

    def draw_grid_line(y_pos):
        c.setLineWidth(0.5); c.setStrokeColor(colors.black); c.setFillColor(colors.black)
        c.line(x_base, y_pos, right_edge, y_pos)

    def draw_vertical_lines(y_top, y_bottom):
        c.setLineWidth(0.5); c.setStrokeColor(colors.grey)
        for k in col_x: c.line(col_x[k], y_top, col_x[k], y_bottom)
        c.line(right_edge, y_top, right_edge, y_bottom)

    def draw_header_detail(p_num):
        nonlocal y
        y = height - 30 * mm
        
        # ページ右上の情報
        c.setFillColor(colors.black)
        c.setFont(FONT_NAME, 10)
        c.drawRightString(right_edge, height - 15*mm, f"{params['project_name']} (No. {p_num})")

        # 表ヘッダー
        c.setFillColor(colors.Color(0.9, 0.9, 0.9))
        c.rect(x_base, y - header_height, right_edge - x_base, header_height, fill=1, stroke=0)
        c.setFillColor(colors.black)
        
        c.setFont(FONT_NAME, 10)
        off_y = y - header_height + 2.5*mm
        labels = {'name':"名 称", 'spec':"規 格", 'qty':"数 量", 'unit':"単位", 'price':"単 価", 'amt':"金 額", 'rem':"備 考"}
        for k, txt in labels.items():
            c.drawCentredString(col_x[k] + col_widths[k]/2, off_y, txt)
        
        c.setStrokeColor(colors.black)
        c.rect(x_base, y - header_height, right_edge - x_base, header_height, stroke=1, fill=0)
        draw_vertical_lines(y, y - header_height)
        y -= header_height

    draw_header_detail(page_num)

    # --- データ処理 ---
    rows = df.to_dict('records')
    n = len(rows)
    subtotal_l1 = 0; subtotal_l2 = 0; subtotal_l3 = 0
    curr_l1 = ""; curr_l2 = ""; curr_l3 = ""

    for i in range(n):
        row = rows[i]
        # 改ページ判定
        if y < 20 * mm:
            c.setFont(FONT_NAME, 9)
            c.drawCentredString(width/2, 10*mm, f"- {page_num} -")
            c.showPage()
            page_num += 1
            draw_header_detail(page_num)

        # データ取得
        l1 = str(row.get('大項目', '')).strip(); l2 = str(row.get('中項目', '')).strip()
        l3 = str(row.get('小項目', '')).strip(); name = str(row.get('名称', ''))
        spec = str(row.get('規格', '')); unit = str(row.get('単位', ''))
        rem = str(row.get('備考', ''))
        qty = parse_amount(row.get('数量', 0)); price = parse_amount(row.get('(自)単価', 0))
        amt = parse_amount(row.get('(自)金額', 0))

        # 見出し描画
        if l1 and l1 != curr_l1:
            c.setFont(FONT_NAME, 11); c.setFillColor(colors.black)
            c.drawString(col_x['name'] + 2*mm, y - 5*mm, f"■ {l1}")
            draw_grid_line(y - row_height); draw_vertical_lines(y, y - row_height)
            y -= row_height; curr_l1 = l1; subtotal_l1 = 0; curr_l2=""; curr_l3=""
        
        if l2 and l2 != curr_l2:
            c.setFont(FONT_NAME, 10)
            c.drawString(col_x['name'] + 6*mm, y - 5*mm, f"● {l2}")
            draw_grid_line(y - row_height); draw_vertical_lines(y, y - row_height)
            y -= row_height; curr_l2 = l2; subtotal_l2 = 0; curr_l3=""
        
        if l3 and l3 != curr_l3:
            c.setFont(FONT_NAME, 10)
            c.drawString(col_x['name'] + 10*mm, y - 5*mm, f"・ {l3}")
            draw_grid_line(y - row_height); draw_vertical_lines(y, y - row_height)
            y -= row_height; curr_l3 = l3; subtotal_l3 = 0

        # 明細行
        if name:
            subtotal_l3 += amt; subtotal_l2 += amt; subtotal_l1 += amt
            c.setFont(FONT_NAME, 9)
            c.drawString(col_x['name'] + 12*mm, y - 5*mm, name)
            c.setFont(FONT_NAME, 8)
            c.drawString(col_x['spec'] + 1*mm, y - 5*mm, spec)
            c.setFont(FONT_NAME, 9)
            if qty: c.drawRightString(col_x['qty'] + col_widths['qty'] - 2*mm, y - 5*mm, f"{qty:,.2f}")
            c.drawCentredString(col_x['unit'] + col_widths['unit']/2, y - 5*mm, unit)
            if price: c.drawRightString(col_x['price'] + col_widths['price'] - 2*mm, y - 5*mm, f"{int(price):,}")
            if amt: c.drawRightString(col_x['amt'] + col_widths['amt'] - 2*mm, y - 5*mm, f"{int(amt):,}")
            c.setFont(FONT_NAME, 8)
            c.drawString(col_x['rem'] + 1*mm, y - 5*mm, rem)
            
            draw_grid_line(y - row_height); draw_vertical_lines(y, y - row_height)
            y -= row_height

        # 小計処理 (先読み)
        next_row = rows[i+1] if i+1 < n else None
        n_l1 = str(next_row.get('大項目', '')).strip() if next_row else ""
        n_l2 = str(next_row.get('中項目', '')).strip() if next_row else ""
        n_l3 = str(next_row.get('小項目', '')).strip() if next_row else ""

        # 小項目計
        if curr_l3 and (n_l3 != curr_l3 or n_l2 != curr_l2 or n_l1 != curr_l1 or not next_row):
            if subtotal_l3 > 0:
                c.setFont(FONT_NAME, 9); c.setFillColor(colors.Color(0,0.4,0))
                c.drawString(col_x['name'] + 10*mm, y - 5*mm, f"【{curr_l3} 小計】")
                c.drawRightString(col_x['amt'] + col_widths['amt'] - 2*mm, y - 5*mm, f"{int(subtotal_l3):,}")
                c.setFillColor(colors.black)
                draw_grid_line(y - row_height); draw_vertical_lines(y, y - row_height)
                y -= row_height
        
        # 中項目計
        if curr_l2 and (n_l2 != curr_l2 or n_l1 != curr_l1 or not next_row):
            if subtotal_l2 > 0:
                c.setFont(FONT_NAME, 9); c.setFillColor(colors.Color(0,0.4,0))
                c.drawString(col_x['name'] + 6*mm, y - 5*mm, f"【{curr_l2} 計】")
                c.drawRightString(col_x['amt'] + col_widths['amt'] - 2*mm, y - 5*mm, f"{int(subtotal_l2):,}")
                c.setFillColor(colors.black)
                c.setLineWidth(1); c.line(x_base, y, right_edge, y) # 上太線
                draw_grid_line(y - row_height); draw_vertical_lines(y, y - row_height)
                y -= row_height
        
        # 大項目計
        if curr_l1 and (n_l1 != curr_l1 or not next_row):
            if subtotal_l1 > 0:
                c.setFont(FONT_NAME, 10); c.setFillColor(colors.black)
                c.drawString(col_x['name'] + 2*mm, y - 5*mm, f"■ {curr_l1} 合計")
                c.drawRightString(col_x['amt'] + col_widths['amt'] - 2*mm, y - 5*mm, f"{int(subtotal_l1):,}")
                c.setLineWidth(1); c.line(x_base, y, right_edge, y)
                draw_grid_line(y - row_height); draw_vertical_lines(y, y - row_height)
                y -= row_height; y -= 3*mm

    c.drawCentredString(width/2, 10*mm, f"- {page_num} -")
    c.save()
    buffer.seek(0)
    return buffer

# ---------------------------------------------------------
# 3. Streamlit UI (サイドバー入力付き)
# ---------------------------------------------------------
st.set_page_config(layout="wide") # 画面を広く使う
st.title("📄 自動見積書作成システム")

# --- サイドバー：入力フォーム ---
with st.sidebar:
    st.header("📝 見積書 情報入力")
    
    # 毎回変わる情報
    sheet_url = st.text_input("スプレッドシートURL", placeholder="https://docs.google.com/...")
    client_name = st.text_input("施主名 (様は自動)", value="")
    project_name = st.text_input("工事名", value="住宅新築工事")
    target_date = st.date_input("日付", value=datetime.today())
    
    st.markdown("---")
    st.subheader("🏢 会社情報 (固定)")
    # デフォルト値を設定しておけば、毎回打たなくてOK
    company_name = st.text_input("会社名", value="株式会社 〇〇工務店")
    ceo_name = st.text_input("代表取締役", value="〇〇 〇〇")
    address = st.text_input("住所", value="長野県木曽郡〇〇町...")
    phone = st.text_input("電話番号", value="0264-xx-xxxx")

# --- メインエリア ---
st.markdown("#### 手順")
st.markdown("1. 左のサイドバーに、**お客様名** や **工事名** を入力してください。")
st.markdown("2. **スプレッドシートのURL** を貼り付けてボタンを押してください。")

if st.button("見積書を作成する", type="primary"):
    if not sheet_url:
        st.error("URLを入力してください。")
    elif not client_name:
        st.error("施主名を入力してください。")
    else:
        with st.spinner('作成中...'):
            df = get_data_from_url(sheet_url)
            
            if df is not None:
                # パラメータをまとめる
                params = {
                    'client_name': client_name,
                    'project_name': project_name,
                    'date': target_date.strftime('%Y年 %m月 %d日'),
                    'company_name': company_name,
                    'ceo': ceo_name,
                    'address': address,
                    'phone': phone
                }
                
                pdf_bytes = create_estimate_pdf(df, params)
                
                if pdf_bytes:
                    st.success("✅ 作成完了！")
                    st.download_button(
                        label="📥 PDFをダウンロード",
                        data=pdf_bytes,
                        file_name=f"見積書_{client_name}様.pdf",
                        mime="application/pdf"
                    )
                    
