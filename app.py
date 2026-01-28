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
# ★変更：明朝体を使う設定
FONT_FILE = "ipaexm.ttf" 
FONT_NAME = "IPAexMincho"

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
# 2. PDF生成エンジン
# ---------------------------------------------------------
def create_estimate_pdf(df, params):
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=landscape(A4))
    width, height = landscape(A4)
    
    try:
        pdfmetrics.registerFont(TTFont(FONT_NAME, FONT_FILE))
    except:
        st.warning(f"フォントファイル({FONT_FILE})が見つかりません。フォルダに配置してください。")
        return None

    def parse_amount(val):
        try:
            return float(str(val).replace('¥', '').replace(',', ''))
        except:
            return 0.0

    total_grand = df['(自)金額'].apply(parse_amount).sum()

    # --- 和暦変換関数 ---
    def to_wareki(dt_obj):
        y = dt_obj.year
        m = dt_obj.month
        d = dt_obj.day
        if y >= 2019:
            reiwa_y = y - 2018
            if reiwa_y == 1: str_y = "元"
            else: str_y = str(reiwa_y)
            return f"令和 {str_y}年 {m}月 {d}日"
        return dt_obj.strftime("%Y年 %m月 %d日") # 平成以前は割愛

    # ==========================================
    # 1ページ目：表紙 (Cover Page)
    # ==========================================
    def draw_cover():
        # タイトル「御 見 積 書」
        c.setFont(FONT_NAME, 42) # ★サイズアップ
        c.setFillColor(colors.darkblue)
        title = "御   見   積   書"
        c.drawCentredString(width/2, height - 55*mm, title)
        
        # 二重線
        line_w = 120*mm
        lx = (width - line_w) / 2
        ly = height - 60*mm
        c.setStrokeColor(colors.darkblue)
        c.setLineWidth(1.5) # 少し太く
        c.line(lx, ly, lx + line_w, ly)
        c.setLineWidth(0.5)
        c.line(lx, ly - 2*mm, lx + line_w, ly - 2*mm)
        c.setFillColor(colors.black) 

        # 宛名
        c.setFont(FONT_NAME, 28) # ★サイズアップ
        c.drawCentredString(width/2, height - 100*mm, f"{params['client_name']}  様")
        c.setStrokeColor(colors.black)
        c.setLineWidth(0.5)
        c.line(width/2 - 70*mm, height - 102*mm, width/2 + 70*mm, height - 102*mm)

        # 下記のとおり...
        c.setFont(FONT_NAME, 12)
        c.drawString(width/2 - 70*mm, height - 120*mm, "下記のとおり御見積申し上げます")

        # 工事名等エリア
        # 実物写真のような「四角い枠」または「下線リスト」にします
        box_top = height - 130*mm
        left_label_x = width/2 - 60*mm
        content_x = width/2 - 20*mm
        line_r_x = width/2 + 70*mm
        line_gap = 15*mm

        # 見積金額 (特大)
        c.setFont(FONT_NAME, 16)
        c.drawString(left_label_x, box_top, "御見積金額 ：")
        c.setFont(FONT_NAME, 24) # 金額ドン
        amount_str = f"¥ {int(total_grand):,}-"
        c.drawString(content_x, box_top, amount_str)
        c.setFont(FONT_NAME, 12)
        c.drawString(content_x + c.stringWidth(amount_str, FONT_NAME, 24) + 5*mm, box_top, "(税込)")
        c.line(left_label_x, box_top - 2*mm, line_r_x, box_top - 2*mm)

        # 工事名
        y_pos = box_top - line_gap
        c.setFont(FONT_NAME, 14)
        c.drawString(left_label_x, y_pos, "工  事  名 ：")
        c.setFont(FONT_NAME, 16)
        c.drawString(content_x, y_pos, params['project_name'])
        c.line(left_label_x, y_pos - 2*mm, line_r_x, y_pos - 2*mm)

        # 会社情報 (右下)
        # ★位置調整：被らないようにX座標を調整
        x_company = width - 100*mm
        y_company = 50*mm
        
        # 日付 (和暦)
        wareki_date = to_wareki(datetime.strptime(params['date'], '%Y年 %m月 %d日'))
        c.setFont(FONT_NAME, 12)
        c.drawString(40*mm, y_company, wareki_date)

        # 会社名
        c.setFont(FONT_NAME, 16)
        c.drawString(x_company, y_company, params['company_name'])
        
        # 代表
        c.setFont(FONT_NAME, 12)
        c.drawString(x_company, y_company - 8*mm, f"代表取締役   {params['ceo']}")
        
        # 住所・TEL
        c.setFont(FONT_NAME, 10)
        c.drawString(x_company, y_company - 16*mm, f"〒 {params['address']}")
        c.drawString(x_company, y_company - 21*mm, f"TEL: {params['phone']}")

        # 印鑑は削除しました

        c.showPage()

    draw_cover()

    # ==========================================
    # 2ページ目以降：明細
    # ==========================================
    x_base = 15 * mm
    # 列幅調整 (文字を大きくするため、少しゆとりを持たせる)
    col_widths = {
        'name': 90 * mm, 'spec': 55 * mm, 'qty': 20 * mm, 
        'unit': 15 * mm, 'price': 30 * mm, 'amt': 35 * mm, 'rem': 22 * mm
    }
    col_x = {}
    cur_x = x_base
    for k, w in col_widths.items():
        col_x[k] = cur_x
        cur_x += w
    right_edge = cur_x
    
    header_height = 9 * mm # 少し高く
    row_height = 6.5 * mm  # ★行間を少し詰める
    y_start = height - 30 * mm
    y = y_start
    page_num = 1

    def draw_grid_line(y_pos):
        c.setLineWidth(0.5); c.setStrokeColor(colors.black)
        c.line(x_base, y_pos, right_edge, y_pos)

    def draw_vertical_lines(y_top, y_bottom):
        c.setLineWidth(0.5); c.setStrokeColor(colors.grey)
        for k in col_x: c.line(col_x[k], y_top, col_x[k], y_bottom)
        c.line(right_edge, y_top, right_edge, y_bottom)

    def draw_header_detail(p_num):
        nonlocal y
        y = height - 30 * mm
        
        c.setFillColor(colors.black)
        c.setFont(FONT_NAME, 10)
        c.drawRightString(right_edge, height - 15*mm, f"{params['project_name']} (No. {p_num})")

        c.setFillColor(colors.Color(0.95, 0.95, 0.95)) # かなり薄いグレー
        c.rect(x_base, y - header_height, right_edge - x_base, header_height, fill=1, stroke=0)
        c.setFillColor(colors.black)
        
        c.setFont(FONT_NAME, 11) # ★ヘッダー文字サイズUP
        off_y = y - header_height + 2.5*mm
        labels = {'name':"名 称", 'spec':"規 格", 'qty':"数 量", 'unit':"単位", 'price':"単 価", 'amt':"金 額", 'rem':"備 考"}
        for k, txt in labels.items():
            c.drawCentredString(col_x[k] + col_widths[k]/2, off_y, txt)
        
        c.setStrokeColor(colors.black)
        c.rect(x_base, y - header_height, right_edge - x_base, header_height, stroke=1, fill=0)
        draw_vertical_lines(y, y - header_height)
        y -= header_height

    draw_header_detail(page_num)

    rows = df.to_dict('records')
    n = len(rows)
    subtotal_l1 = 0; subtotal_l2 = 0; subtotal_l3 = 0
    curr_l1 = ""; curr_l2 = ""; curr_l3 = ""

    for i in range(n):
        row = rows[i]
        if y < 20 * mm:
            c.setFont(FONT_NAME, 10)
            c.drawCentredString(width/2, 10*mm, f"- {page_num} -")
            c.showPage()
            page_num += 1
            draw_header_detail(page_num)

        l1 = str(row.get('大項目', '')).strip(); l2 = str(row.get('中項目', '')).strip()
        l3 = str(row.get('小項目', '')).strip(); name = str(row.get('名称', ''))
        spec = str(row.get('規格', '')); unit = str(row.get('単位', ''))
        rem = str(row.get('備考', ''))
        qty = parse_amount(row.get('数量', 0)); price = parse_amount(row.get('(自)単価', 0))
        amt = parse_amount(row.get('(自)金額', 0))

        # 見出し描画 (文字サイズUP)
        if l1 and l1 != curr_l1:
            c.setFont(FONT_NAME, 12); c.setFillColor(colors.black)
            c.drawString(col_x['name'] + 2*mm, y - 5*mm, f"■ {l1}")
            draw_grid_line(y - row_height); draw_vertical_lines(y, y - row_height)
            y -= row_height; curr_l1 = l1; subtotal_l1 = 0; curr_l2=""; curr_l3=""
        
        if l2 and l2 != curr_l2:
            c.setFont(FONT_NAME, 11)
            c.drawString(col_x['name'] + 6*mm, y - 5*mm, f"● {l2}")
            draw_grid_line(y - row_height); draw_vertical_lines(y, y - row_height)
            y -= row_height; curr_l2 = l2; subtotal_l2 = 0; curr_l3=""
        
        if l3 and l3 != curr_l3:
            c.setFont(FONT_NAME, 11)
            c.drawString(col_x['name'] + 10*mm, y - 5*mm, f"・ {l3}")
            draw_grid_line(y - row_height); draw_vertical_lines(y, y - row_height)
            y -= row_height; curr_l3 = l3; subtotal_l3 = 0

        # 明細行 (文字サイズUP: 9pt -> 10.5pt)
        if name:
            subtotal_l3 += amt; subtotal_l2 += amt; subtotal_l1 += amt
            c.setFont(FONT_NAME, 10.5) # ★標準サイズ
            c.drawString(col_x['name'] + 12*mm, y - 5*mm, name)
            c.setFont(FONT_NAME, 9)
            c.drawString(col_x['spec'] + 1*mm, y - 5*mm, spec)
            
            c.setFont(FONT_NAME, 10.5)
            if qty: c.drawRightString(col_x['qty'] + col_widths['qty'] - 2*mm, y - 5*mm, f"{qty:,.2f}")
            c.drawCentredString(col_x['unit'] + col_widths['unit']/2, y - 5*mm, unit)
            if price: c.drawRightString(col_x['price'] + col_widths['price'] - 2*mm, y - 5*mm, f"{int(price):,}")
            if amt: c.drawRightString(col_x['amt'] + col_widths['amt'] - 2*mm, y - 5*mm, f"{int(amt):,}")
            
            c.setFont(FONT_NAME, 9)
            c.drawString(col_x['rem'] + 1*mm, y - 5*mm, rem)
            
            draw_grid_line(y - row_height); draw_vertical_lines(y, y - row_height)
            y -= row_height

        # 小計 (文字サイズUP)
        next_row = rows[i+1] if i+1 < n else None
        n_l1 = str(next_row.get('大項目', '')).strip() if next_row else ""
        n_l2 = str(next_row.get('中項目', '')).strip() if next_row else ""
        n_l3 = str(next_row.get('小項目', '')).strip() if next_row else ""

        if curr_l3 and (n_l3 != curr_l3 or n_l2 != curr_l2 or n_l1 != curr_l1 or not next_row):
            if subtotal_l3 > 0:
                c.setFont(FONT_NAME, 10); c.setFillColor(colors.Color(0,0.4,0))
                c.drawString(col_x['name'] + 10*mm, y - 5*mm, f"【{curr_l3} 小計】")
                c.drawRightString(col_x['amt'] + col_widths['amt'] - 2*mm, y - 5*mm, f"{int(subtotal_l3):,}")
                c.setFillColor(colors.black)
                draw_grid_line(y - row_height); draw_vertical_lines(y, y - row_height)
                y -= row_height
        
        if curr_l2 and (n_l2 != curr_l2 or n_l1 != curr_l1 or not next_row):
            if subtotal_l2 > 0:
                c.setFont(FONT_NAME, 10); c.setFillColor(colors.Color(0,0.4,0))
                c.drawString(col_x['name'] + 6*mm, y - 5*mm, f"【{curr_l2} 計】")
                c.drawRightString(col_x['amt'] + col_widths['amt'] - 2*mm, y - 5*mm, f"{int(subtotal_l2):,}")
                c.setFillColor(colors.black)
                c.setLineWidth(1); c.line(x_base, y, right_edge, y)
                draw_grid_line(y - row_height); draw_vertical_lines(y, y - row_height)
                y -= row_height
        
        if curr_l1 and (n_l1 != curr_l1 or not next_row):
            if subtotal_l1 > 0:
                c.setFont(FONT_NAME, 11); c.setFillColor(colors.black)
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
# 3. Streamlit UI
# ---------------------------------------------------------
st.set_page_config(layout="wide")
st.title("📄 自動見積書作成システム")

with st.sidebar:
    st.header("📝 見積書 情報入力")
    sheet_url = st.text_input("スプレッドシートURL", placeholder="https://docs.google.com/...")
    client_name = st.text_input("施主名 (様は自動)", value="")
    project_name = st.text_input("工事名", value="住宅新築工事")
    target_date = st.date_input("日付", value=datetime.today())
    
    st.markdown("---")
    st.subheader("🏢 会社情報")
    company_name = st.text_input("会社名", value="株式会社 〇〇工務店")
    ceo_name = st.text_input("代表取締役", value="〇〇 〇〇")
    address = st.text_input("住所", value="長野県木曽郡〇〇町...")
    phone = st.text_input("電話番号", value="0264-xx-xxxx")

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
