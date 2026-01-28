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
FONT_FILE = "ipaexg.ttf" # ファイル名はそのままで中身は明朝(ipaexm.ttf)の想定
FONT_NAME = "IPAexMincho" # 登録名

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
        st.warning(f"フォントファイル({FONT_FILE})が見つかりません。")
        return None

    # --- ヘルパー関数 ---
    def parse_amount(val):
        try:
            return float(str(val).replace('¥', '').replace(',', ''))
        except:
            return 0.0

    def to_wareki(dt_obj):
        y = dt_obj.year
        m = dt_obj.month
        d = dt_obj.day
        if y >= 2019:
            reiwa_y = y - 2018
            str_y = "元" if reiwa_y == 1 else str(reiwa_y)
            return f"令和 {str_y}年 {m}月 {d}日"
        return dt_obj.strftime("%Y年 %m月 %d日")

    # ★修正箇所：太字関数の書き方を変更しました
    def draw_bold_string(x, y, text, size, color=colors.black):
        # 線の太さを設定（文字サイズの3%）
        c.setLineWidth(size * 0.03)
        
        # テキストオブジェクトを作成して設定
        text_obj = c.beginText(x, y)
        text_obj.setFont(FONT_NAME, size)
        text_obj.setFillColor(color)
        text_obj.setStrokeColor(color)
        text_obj.setTextRenderMode(2) # 2 = Fill + Stroke (擬似ボールド)
        text_obj.textOut(text)
        
        # 描画実行
        c.drawText(text_obj)
        
        # 線の太さを戻す
        c.setLineWidth(1)

    def draw_bold_centered_string(x, y, text, size, color=colors.black):
        text_w = c.stringWidth(text, FONT_NAME, size)
        draw_bold_string(x - text_w/2, y, text, size, color)

    # 合計計算
    total_grand = df['(自)金額'].apply(parse_amount).sum()
    tax_amount = total_grand * 0.1

    # ==========================================
    # 1ページ目：表紙 (Simple Cover)
    # ==========================================
    def draw_page1_cover():
        # タイトル
        draw_bold_centered_string(width/2, height - 60*mm, "御   見   積   書", 50, colors.darkblue)
        
        # 二重線
        lw = 140*mm
        lx = (width - lw)/2
        ly = height - 65*mm
        c.setStrokeColor(colors.darkblue)
        c.setLineWidth(2); c.line(lx, ly, lx+lw, ly)
        c.setLineWidth(0.5); c.line(lx, ly-2*mm, lx+lw, ly-2*mm)
        c.setFillColor(colors.black)

        # 宛名
        draw_bold_centered_string(width/2, height - 110*mm, f"{params['client_name']}  様", 36)
        c.setStrokeColor(colors.black)
        c.setLineWidth(1)
        c.line(width/2 - 80*mm, height - 112*mm, width/2 + 80*mm, height - 112*mm)

        # 工事名
        draw_bold_centered_string(width/2, height - 140*mm, f"{params['project_name']}", 24)
        c.setLineWidth(0.5)
        c.line(width/2 - 80*mm, height - 142*mm, width/2 + 80*mm, height - 142*mm)

        # 日付
        wareki = to_wareki(datetime.strptime(params['date'], '%Y年 %m月 %d日'))
        c.setFont(FONT_NAME, 14)
        c.drawString(40*mm, 50*mm, wareki)

        # 会社情報
        x_co = width - 100*mm
        y_co = 50*mm
        draw_bold_string(x_co, y_co, params['company_name'], 18)
        c.setFont(FONT_NAME, 13)
        c.drawString(x_co, y_co - 10*mm, f"代表取締役   {params['ceo']}")
        c.setFont(FONT_NAME, 11)
        c.drawString(x_co, y_co - 20*mm, f"〒 {params['address']}")
        c.drawString(x_co, y_co - 26*mm, f"TEL: {params['phone']}")
        if params['fax']:
            c.drawString(x_co + 40*mm, y_co - 26*mm, f"FAX: {params['fax']}")

        c.showPage()

    draw_page1_cover()

    # ==========================================
    # 2ページ目：見積概要書 (Summary Box)
    # ==========================================
    def draw_page2_summary():
        # タイトル
        draw_bold_centered_string(width/2, height - 30*mm, "御   見   積   書", 32)
        c.setLineWidth(1)
        c.line(width/2 - 60*mm, height - 32*mm, width/2 + 60*mm, height - 32*mm)
        c.setLineWidth(0.5)
        c.line(width/2 - 60*mm, height - 33*mm, width/2 + 60*mm, height - 33*mm)

        # 宛名
        c.setFont(FONT_NAME, 20)
        c.drawString(40*mm, height - 50*mm, f"{params['client_name']}  様")
        
        c.setFont(FONT_NAME, 12)
        c.drawString(40*mm, height - 60*mm, "下記のとおり御見積申し上げます")

        # --- 大きな枠線 ---
        box_top = height - 70*mm
        box_left = 40*mm
        box_width = width - 80*mm
        box_height = 110*mm
        box_bottom = box_top - box_height

        c.setLineWidth(1.5); c.rect(box_left, box_bottom, box_width, box_height)
        c.setLineWidth(0.5); c.rect(box_left+1*mm, box_bottom+1*mm, box_width-2*mm, box_height-2*mm)

        line_start_x = box_left + 10*mm
        label_width = 30*mm
        content_start_x = line_start_x + label_width
        line_end_x = box_left + box_width - 10*mm
        
        current_y = box_top - 15*mm
        gap = 12*mm

        # 1. 見積金額
        draw_bold_string(line_start_x, current_y, "見積金額：", 14)
        amount_str = f"¥ {int(total_grand):,}-"
        draw_bold_string(content_start_x, current_y, amount_str, 18)
        
        tax_str = f"(別途消費税  ¥ {int(tax_amount):,})"
        c.setFont(FONT_NAME, 12)
        c.drawString(content_start_x + c.stringWidth(amount_str, FONT_NAME, 18) + 5*mm, current_y, tax_str)
        
        c.setLineWidth(0.5)
        c.line(line_start_x, current_y - 2*mm, line_end_x, current_y - 2*mm)
        current_y -= gap * 1.5

        # 2. 工事名
        c.setFont(FONT_NAME, 12)
        c.drawString(line_start_x, current_y, "工 事 名 ：")
        c.setFont(FONT_NAME, 13)
        c.drawString(content_start_x, current_y, params['project_name'])
        c.line(line_start_x, current_y - 2*mm, line_end_x, current_y - 2*mm)
        current_y -= gap

        # 3. 工事場所
        c.setFont(FONT_NAME, 12)
        c.drawString(line_start_x, current_y, "工事場所 ：")
        c.setFont(FONT_NAME, 13)
        c.drawString(content_start_x, current_y, params['location'])
        c.line(line_start_x, current_y - 2*mm, line_end_x, current_y - 2*mm)
        current_y -= gap

        # 4. 工期
        c.setFont(FONT_NAME, 12)
        c.drawString(line_start_x, current_y, "工    期 ：")
        c.setFont(FONT_NAME, 13)
        c.drawString(content_start_x, current_y, params['term'])
        c.line(line_start_x, current_y - 2*mm, line_end_x, current_y - 2*mm)
        current_y -= gap

        # 5. その他
        c.setFont(FONT_NAME, 12)
        c.drawString(line_start_x, current_y, "そ の 他 ：")
        c.drawString(content_start_x, current_y, "別紙内訳書による")
        c.line(line_start_x, current_y - 2*mm, line_end_x, current_y - 2*mm)
        current_y -= gap

        # 6. 有効期限
        c.drawString(line_start_x, current_y, "見積有効期限：")
        c.drawString(content_start_x, current_y, params['expiry'])
        c.line(line_start_x, current_y - 2*mm, line_end_x, current_y - 2*mm)

        # 会社情報
        x_co = width - 100*mm
        y_co = box_bottom - 20*mm
        wareki = to_wareki(datetime.strptime(params['date'], '%Y年 %m月 %d日'))
        c.setFont(FONT_NAME, 12)
        c.drawString(width - 80*mm, box_top + 5*mm, wareki)

        c.setFont(FONT_NAME, 13)
        c.drawString(x_co, y_co, params['company_name'])
        c.setFont(FONT_NAME, 11)
        c.drawString(x_co, y_co - 7*mm, f"代表取締役   {params['ceo']}")
        c.setFont(FONT_NAME, 10)
        c.drawString(x_co, y_co - 14*mm, f"〒 {params['address']}")
        c.drawString(x_co, y_co - 19*mm, f"TEL {params['phone']}  FAX {params['fax']}")

        c.showPage()

    draw_page2_summary()

    # ==========================================
    # 3ページ目以降：明細 (Grid)
    # ==========================================
    x_base = 20 * mm 
    width_content = width - 40 * mm
    
    col_widths = {
        'name': 90 * mm, 'spec': 60 * mm, 'qty': 20 * mm, 
        'unit': 15 * mm, 'price': 30 * mm, 'amt': 35 * mm, 'rem': 0 * mm
    }
    used_width = sum(col_widths.values())
    col_widths['rem'] = width_content - used_width

    col_x = {}
    cur_x = x_base
    for k in col_widths.keys():
        col_x[k] = cur_x
        cur_x += col_widths[k]
    right_edge = cur_x
    
    header_height = 10 * mm
    row_height = 8 * mm
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

        c.setFillColor(colors.Color(0.95, 0.95, 0.95))
        c.rect(x_base, y - header_height, right_edge - x_base, header_height, fill=1, stroke=0)
        c.setFillColor(colors.black)
        
        c.setFont(FONT_NAME, 11)
        off_y = y - header_height + 3*mm
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
        
        l1 = str(row.get('大項目', '')).strip(); l2 = str(row.get('中項目', '')).strip()
        l3 = str(row.get('小項目', '')).strip(); name = str(row.get('名称', ''))
        spec = str(row.get('規格', '')); unit = str(row.get('単位', ''))
        rem = str(row.get('備考', ''))
        qty = parse_amount(row.get('数量', 0)); price = parse_amount(row.get('(自)単価', 0))
        amt = parse_amount(row.get('(自)金額', 0))

        # 改ページ判定
        is_l1_change = (l1 and l1 != curr_l1)
        is_l2_change = (l2 and l2 != curr_l2)
        is_page_full = (y < 20 * mm)

        if (is_l1_change or is_l2_change or is_page_full) and i > 0:
            c.setFont(FONT_NAME, 10)
            c.drawCentredString(width/2, 10*mm, f"- {page_num} -")
            c.showPage()
            page_num += 1
            draw_header_detail(page_num)

        # 見出し (太字)
        if l1 and l1 != curr_l1:
            draw_bold_string(col_x['name'] + 2*mm, y - 6*mm, f"■ {l1}", 13)
            draw_grid_line(y - row_height); draw_vertical_lines(y, y - row_height)
            y -= row_height; curr_l1 = l1; subtotal_l1 = 0; curr_l2=""; curr_l3=""
        
        if l2 and l2 != curr_l2:
            draw_bold_string(col_x['name'] + 6*mm, y - 6*mm, f"● {l2}", 12)
            draw_grid_line(y - row_height); draw_vertical_lines(y, y - row_height)
            y -= row_height; curr_l2 = l2; subtotal_l2 = 0; curr_l3=""
        
        if l3 and l3 != curr_l3:
            c.setFont(FONT_NAME, 12)
            c.drawString(col_x['name'] + 10*mm, y - 6*mm, f"・ {l3}")
            draw_grid_line(y - row_height); draw_vertical_lines(y, y - row_height)
            y -= row_height; curr_l3 = l3; subtotal_l3 = 0

        # 明細
        if name:
            subtotal_l3 += amt; subtotal_l2 += amt; subtotal_l1 += amt
            c.setFont(FONT_NAME, 12)
            c.drawString(col_x['name'] + 12*mm, y - 6*mm, name)
            c.setFont(FONT_NAME, 10)
            c.drawString(col_x['spec'] + 1*mm, y - 6*mm, spec)
            
            c.setFont(FONT_NAME, 12)
            if qty: c.drawRightString(col_x['qty'] + col_widths['qty'] - 2*mm, y - 6*mm, f"{qty:,.2f}")
            c.drawCentredString(col_x['unit'] + col_widths['unit']/2, y - 6*mm, unit)
            if price: c.drawRightString(col_x['price'] + col_widths['price'] - 2*mm, y - 6*mm, f"{int(price):,}")
            if amt: c.drawRightString(col_x['amt'] + col_widths['amt'] - 2*mm, y - 6*mm, f"{int(amt):,}")
            
            c.setFont(FONT_NAME, 9)
            c.drawString(col_x['rem'] + 1*mm, y - 6*mm, rem)
            
            draw_grid_line(y - row_height); draw_vertical_lines(y, y - row_height)
            y -= row_height

        # 小計
        next_row = rows[i+1] if i+1 < n else None
        n_l1 = str(next_row.get('大項目', '')).strip() if next_row else ""
        n_l2 = str(next_row.get('中項目', '')).strip() if next_row else ""
        n_l3 = str(next_row.get('小項目', '')).strip() if next_row else ""

        if curr_l3 and (n_l3 != curr_l3 or n_l2 != curr_l2 or n_l1 != curr_l1 or not next_row):
            if subtotal_l3 > 0:
                c.setFont(FONT_NAME, 11); c.setFillColor(colors.Color(0,0.4,0))
                c.drawString(col_x['name'] + 10*mm, y - 6*mm, f"【{curr_l3} 小計】")
                c.drawRightString(col_x['amt'] + col_widths['amt'] - 2*mm, y - 6*mm, f"{int(subtotal_l3):,}")
                c.setFillColor(colors.black)
                draw_grid_line(y - row_height); draw_vertical_lines(y, y - row_height)
                y -= row_height
        
        if curr_l2 and (n_l2 != curr_l2 or n_l1 != curr_l1 or not next_row):
            if subtotal_l2 > 0:
                draw_bold_string(col_x['name'] + 6*mm, y - 6*mm, f"【{curr_l2} 計】", 11, colors.Color(0,0.4,0))
                c.setFont(FONT_NAME, 11); c.setFillColor(colors.Color(0,0.4,0))
                c.drawRightString(col_x['amt'] + col_widths['amt'] - 2*mm, y - 6*mm, f"{int(subtotal_l2):,}")
                c.setFillColor(colors.black)
                c.setLineWidth(1); c.line(x_base, y, right_edge, y)
                draw_grid_line(y - row_height); draw_vertical_lines(y, y - row_height)
                y -= row_height
        
        if curr_l1 and (n_l1 != curr_l1 or not next_row):
            if subtotal_l1 > 0:
                draw_bold_string(col_x['name'] + 2*mm, y - 6*mm, f"■ {curr_l1} 合計", 12)
                c.setFont(FONT_NAME, 12)
                c.drawRightString(col_x['amt'] + col_widths['amt'] - 2*mm, y - 6*mm, f"{int(subtotal_l1):,}")
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
    client_name = st.text_input("施主名", value="")
    project_name = st.text_input("工事名", value="住宅新築工事")
    
    st.markdown("---")
    st.subheader("📋 工事概要")
    location = st.text_input("工事場所", value="木曽郡木曽町...")
    term = st.text_input("工期", value="令和 7年 12月 20日")
    expiry = st.text_input("有効期限", value="2ヶ月")
    target_date = st.date_input("発行日", value=datetime.today())
    
    st.markdown("---")
    st.subheader("🏢 会社情報")
    company_name = st.text_input("会社名", value="株式会社 〇〇工務店")
    ceo_name = st.text_input("代表取締役", value="〇〇 〇〇")
    address = st.text_input("住所", value="長野県木曽郡〇〇町...")
    phone = st.text_input("電話番号", value="0264-xx-xxxx")
    fax = st.text_input("FAX番号", value="0264-xx-xxxx")

st.markdown("#### 手順")
st.markdown("1. 左のサイドバーに、情報を入力してください。")
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
                    'location': location,
                    'term': term,
                    'expiry': expiry,
                    'date': target_date.strftime('%Y年 %m月 %d日'),
                    'company_name': company_name,
                    'ceo': ceo_name,
                    'address': address,
                    'phone': phone,
                    'fax': fax
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
