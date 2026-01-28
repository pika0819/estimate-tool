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
FONT_NAME = "IPAexMincho"

# 色設定
COLOR_L1 = colors.Color(0, 0.4, 0)      # 緑
COLOR_L2 = colors.Color(0, 0, 0.6)      # 紺
COLOR_L3 = colors.Color(0.8, 0.3, 0)    # オレンジ
COLOR_TEXT = colors.black
COLOR_TOTAL = colors.Color(0.8, 0, 0)   # 赤

# インデント幅
INDENT_L1 = 1.0 * mm
INDENT_L2 = 2.5 * mm
INDENT_L3 = 4.5 * mm
INDENT_ITEM = 6.0 * mm

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

    def parse_amount(val):
        try: return float(str(val).replace('¥', '').replace(',', ''))
        except: return 0.0

    def to_wareki(dt_obj):
        y = dt_obj.year; m = dt_obj.month; d = dt_obj.day
        if y >= 2019:
            r_y = y - 2018
            return f"令和 {r_y}年 {m}月 {d}日" if r_y != 1 else f"令和 元年 {m}月 {d}日"
        return dt_obj.strftime("%Y年 %m月 %d日")

    def draw_bold_string(x, y, text, size, color=colors.black):
        c.saveState()
        c.setLineWidth(size * 0.03)
        t_obj = c.beginText(x, y)
        t_obj.setFont(FONT_NAME, size)
        t_obj.setFillColor(color); t_obj.setStrokeColor(color)
        t_obj.setTextRenderMode(2)
        t_obj.textOut(text)
        c.drawText(t_obj)
        c.restoreState()

    def draw_bold_centered_string(x, y, text, size, color=colors.black):
        tw = c.stringWidth(text, FONT_NAME, size)
        draw_bold_string(x - tw/2, y, text, size, color)

    total_grand = df['(自)金額'].apply(parse_amount).sum()
    tax_amount = total_grand * 0.1
    final_total = total_grand + tax_amount

    # --- グリッド設定 ---
    x_base = 15 * mm; content_width = width - 30 * mm
    col_widths = {'name': 80*mm, 'spec': 50*mm, 'qty': 18*mm, 'unit': 12*mm, 'price': 25*mm, 'amt': 30*mm, 'rem': 0*mm}
    col_widths['rem'] = content_width - sum(col_widths.values())
    col_x = {}
    curr_x = x_base
    for k in col_widths.keys(): col_x[k] = curr_x; curr_x += col_widths[k]
    right_edge = curr_x
    
    header_height = 9 * mm; row_height = 7 * mm
    top_margin = 35 * mm; bottom_margin = 20 * mm
    y_start = height - top_margin
    rows_per_page = int((height - top_margin - bottom_margin) / row_height)

    def draw_grid_line(y_pos, color=colors.black, width=0.5):
        c.setLineWidth(width); c.setStrokeColor(color); c.line(x_base, y_pos, right_edge, y_pos)
    
    def draw_vertical_lines(y_top, y_btm):
        c.setLineWidth(0.5); c.setStrokeColor(colors.grey)
        for k in col_x: c.line(col_x[k], y_top, col_x[k], y_btm)
        c.line(right_edge, y_top, right_edge, y_btm)

    def draw_page_header_common(p_num):
        hy = height - 20 * mm
        c.setFillColor(colors.black)
        c.setFont(FONT_NAME, 16); title = "内 訳 明 細 書"; tw = c.stringWidth(title, FONT_NAME, 16)
        c.drawCentredString(width/2, hy, title)
        c.setLineWidth(0.5); c.line(width/2 - tw/2 - 5*mm, hy - 2*mm, width/2 + tw/2 + 5*mm, hy - 2*mm)
        c.setFont(FONT_NAME, 10); c.drawRightString(right_edge, hy, params['company_name'])
        
        # ★ページ番号を中央下に変更
        c.drawCentredString(width/2, 10*mm, f"- {p_num} -")

        hy_grid = y_start
        c.setFillColor(colors.Color(0.95, 0.95, 0.95)); c.rect(x_base, hy_grid, right_edge - x_base, header_height, fill=1, stroke=0)
        c.setFillColor(colors.black); c.setFont(FONT_NAME, 10)
        txt_y = hy_grid + 2.5*mm
        labels = {'name':"名 称", 'spec':"規 格", 'qty':"数 量", 'unit':"単位", 'price':"単 価", 'amt':"金 額", 'rem':"備 考"}
        for k, txt in labels.items(): c.drawCentredString(col_x[k] + col_widths[k]/2, txt_y, txt)
        c.setStrokeColor(colors.black); c.setLineWidth(0.5); c.rect(x_base, hy_grid, right_edge - x_base, header_height, stroke=1, fill=0)
        draw_vertical_lines(hy_grid + header_height, hy_grid)

    # 1. 表紙
    def draw_page1():
        draw_bold_centered_string(width/2, height - 60*mm, "御   見   積   書", 50, colors.darkblue)
        lw = 140*mm; lx = (width - lw)/2; ly = height - 65*mm
        c.setStrokeColor(colors.darkblue); c.setLineWidth(2); c.line(lx, ly, lx+lw, ly)
        c.setLineWidth(0.5); c.line(lx, ly-2*mm, lx+lw, ly-2*mm)
        c.setFillColor(colors.black); c.setStrokeColor(colors.black)

        draw_bold_centered_string(width/2, height - 110*mm, f"{params['client_name']}  様", 36)
        c.setLineWidth(1); c.line(width/2 - 80*mm, height - 112*mm, width/2 + 80*mm, height - 112*mm)
        draw_bold_centered_string(width/2, height - 140*mm, f"{params['project_name']}", 24)
        c.setLineWidth(0.5); c.line(width/2 - 80*mm, height - 142*mm, width/2 + 80*mm, height - 142*mm)
        
        wareki = to_wareki(datetime.strptime(params['date'], '%Y年 %m月 %d日'))
        c.setFont(FONT_NAME, 14); c.drawString(40*mm, 50*mm, wareki)
        x_co = width - 100*mm; y_co = 50*mm
        draw_bold_string(x_co, y_co, params['company_name'], 18)
        c.setFont(FONT_NAME, 13); c.drawString(x_co, y_co - 10*mm, f"代表取締役   {params['ceo']}")
        c.setFont(FONT_NAME, 11); c.drawString(x_co, y_co - 20*mm, f"〒 {params['address']}")
        c.drawString(x_co, y_co - 26*mm, f"TEL: {params['phone']}")
        if params['fax']: c.drawString(x_co + 40*mm, y_co - 26*mm, f"FAX: {params['fax']}")
        c.showPage()

    # 2. 概要
    def draw_page2():
        draw_bold_centered_string(width/2, height - 30*mm, "御   見   積   書", 32)
        c.setLineWidth(1); c.line(width/2 - 60*mm, height - 32*mm, width/2 + 60*mm, height - 32*mm)
        c.setLineWidth(0.5); c.line(width/2 - 60*mm, height - 33*mm, width/2 + 60*mm, height - 33*mm)
        c.setFont(FONT_NAME, 20); c.drawString(40*mm, height - 50*mm, f"{params['client_name']}  様")
        c.setFont(FONT_NAME, 12); c.drawString(40*mm, height - 60*mm, "下記のとおり御見積申し上げます")

        box_top = height - 65*mm
        box_left = 40*mm; box_width = width - 80*mm; box_height = 100*mm
        box_bottom = box_top - box_height
        c.setLineWidth(1.5); c.rect(box_left, box_bottom, box_width, box_height)
        c.setLineWidth(0.5); c.rect(box_left+1*mm, box_bottom+1*mm, box_width-2*mm, box_height-2*mm)

        line_sx = box_left + 10*mm
        label_end_x = line_sx + 28*mm
        colon_x = label_end_x + 1*mm
        val_start_x = colon_x + 5*mm 
        line_ex = box_left + box_width - 10*mm
        curr_y = box_top - 15*mm; gap = 12*mm

        c.setFont(FONT_NAME, 14); c.drawRightString(label_end_x, curr_y, "見積金額")
        draw_bold_string(colon_x, curr_y, "：", 14)
        amt_s = f"¥ {int(total_grand):,}-"
        draw_bold_string(val_start_x, curr_y, amt_s, 18)
        tax_s = f"(別途消費税  ¥ {int(tax_amount):,})"
        c.setFont(FONT_NAME, 12); c.drawString(val_start_x + c.stringWidth(amt_s, FONT_NAME, 18) + 5*mm, curr_y, tax_s)
        c.setLineWidth(0.5); c.line(line_sx, curr_y-2*mm, line_ex, curr_y-2*mm)
        curr_y -= gap * 1.5

        items = [("工 事 名", params['project_name']), ("工事場所", params['location']),
                 ("工    期", params['term']), ("そ の 他", "別紙内訳書による"), ("見積有効期限", params['expiry'])]
        for label, val in items:
            c.setFont(FONT_NAME, 12); c.drawRightString(label_end_x, curr_y, label)
            c.drawString(colon_x, curr_y, "：")
            c.setFont(FONT_NAME, 13); c.drawString(val_start_x, curr_y, val)
            c.line(line_sx, curr_y-2*mm, line_ex, curr_y-2*mm)
            curr_y -= gap

        x_co = width - 100*mm; y_co = box_bottom + 20*mm
        wareki = to_wareki(datetime.strptime(params['date'], '%Y年 %m月 %d日'))
        c.setFont(FONT_NAME, 12); c.drawString(width - 80*mm, box_top + 5*mm, wareki)
        c.setFont(FONT_NAME, 13); c.drawString(x_co, y_co, params['company_name'])
        c.setFont(FONT_NAME, 11); c.drawString(x_co, y_co - 7*mm, f"代表取締役   {params['ceo']}")
        c.setFont(FONT_NAME, 10); c.drawString(x_co, y_co - 14*mm, f"〒 {params['address']}")
        c.drawString(x_co, y_co - 19*mm, f"TEL {params['phone']}  FAX {params['fax']}")
        c.showPage()

    # 3. 大項目集計
    def draw_page3_l1_summary(p_num):
        draw_page_header_common(p_num)
        y = y_start
        
        l1_summary = df.groupby('大項目', sort=False)['(自)金額'].apply(lambda x: x.apply(parse_amount).sum()).reset_index()
        for idx, row in l1_summary.iterrows():
            l1_name = row['大項目']; amount = row['(自)金額']
            if not l1_name: continue
            draw_bold_string(col_x['name'] + INDENT_L1, y-5*mm, f"■ {l1_name}", 10, COLOR_L1)
            c.setFont(FONT_NAME, 10); c.setFillColor(colors.black)
            c.drawRightString(col_x['amt'] + col_widths['amt'] - 2*mm, y-5*mm, f"{int(amount):,}")
            draw_grid_line(y - row_height); y -= row_height
        
        footer_rows = 3
        footer_start_y = y_start - (rows_per_page - footer_rows) * row_height
        while y > footer_start_y + 0.1: 
            draw_grid_line(y - row_height); y -= row_height
            
        labels = [("小計", total_grand), ("消費税", tax_amount), ("総合計", final_total)]
        for lbl, val in labels:
            c.setFillColor(colors.black)
            draw_bold_string(col_x['name'] + 20*mm, y-5*mm, f"【 {lbl} 】", 11, COLOR_TOTAL)
            c.setFont(FONT_NAME, 11); c.setFillColor(COLOR_TOTAL)
            c.drawRightString(col_x['amt'] + col_widths['amt'] - 2*mm, y-5*mm, f"{int(val):,}")
            draw_grid_line(y - row_height); y -= row_height
            
        draw_vertical_lines(y_start, y); c.showPage(); return p_num + 1

    # 4. 明細書
    def draw_details(start_p_num):
        p_num = start_p_num
        print_items = []
        raw_rows = df.to_dict('records')
        curr_l1, curr_l2, curr_l3, curr_l4 = "", "", "", ""
        sub_l1, sub_l2, sub_l3, sub_l4 = 0, 0, 0, 0

        for i, row in enumerate(raw_rows):
            l1 = str(row.get('大項目', '')).strip(); l2 = str(row.get('中項目', '')).strip()
            l3 = str(row.get('小項目', '')).strip(); l4 = str(row.get('部分項目', '')).strip()
            name = str(row.get('名称', '')); amt = parse_amount(row.get('(自)金額', 0))

            l1_chg = (l1 and l1 != curr_l1); l2_chg = (l2 and l2 != curr_l2)
            l3_chg = (l3 and l3 != curr_l3); l4_chg = (l4 and l4 != curr_l4)

            # Footer
            if curr_l4 and (l4_chg or l3_chg or l2_chg or l1_chg):
                 print_items.append({'type': 'footer_l4', 'label': f"【{curr_l4}】 小計", 'amt': sub_l4}); curr_l4 = ""; sub_l4 = 0
            if curr_l3 and (l3_chg or l2_chg or l1_chg):
                 print_items.append({'type': 'footer_l3', 'label': f"【{curr_l3} 小計】", 'amt': sub_l3}); curr_l3 = ""; sub_l3 = 0
            if curr_l2 and (l2_chg or l1_chg):
                 print_items.append({'type': 'footer_l2', 'label': f"【{curr_l2} 計】", 'amt': sub_l2}); curr_l2 = ""; sub_l2 = 0
            if curr_l1 and l1_chg:
                 print_items.append({'type': 'footer_l1', 'label': f"■ {curr_l1} 合計", 'amt': sub_l1}); curr_l1 = ""; sub_l1 = 0

            # Header
            if l1_chg: print_items.append({'type': 'header_l1', 'label': f"■ {l1}"}); curr_l1 = l1
            if l2_chg: print_items.append({'type': 'header_l2', 'label': f"● {l2}"}); curr_l2 = l2
            if l3_chg: print_items.append({'type': 'header_l3', 'label': f"・ {l3}"}); curr_l3 = l3
            if l4_chg: print_items.append({'type': 'header_l4', 'label': f"【{l4}】"}); curr_l4 = l4

            if name:
                sub_l1 += amt; sub_l2 += amt; sub_l3 += amt; sub_l4 += amt
                d = row.copy(); d.update({'amt_val': amt, 'qty_val': parse_amount(row.get('数量', 0)), 'price_val': parse_amount(row.get('(自)単価', 0))})
                print_items.append({'type': 'item', 'data': d})

        if curr_l4: print_items.append({'type': 'footer_l4', 'label': f"【{curr_l4}】 小計", 'amt': sub_l4})
        if curr_l3: print_items.append({'type': 'footer_l3', 'label': f"【{curr_l3} 小計】", 'amt': sub_l3})
        if curr_l2: print_items.append({'type': 'footer_l2', 'label': f"【{curr_l2} 計】", 'amt': sub_l2})
        if curr_l1: print_items.append({'type': 'footer_l1', 'label': f"■ {curr_l1} 合計", 'amt': sub_l1})

        # 空行挿入
        final_items = []
        for i, item in enumerate(print_items):
            final_items.append(item)
            if i + 1 < len(print_items):
                curr = item['type']; next_t = print_items[i+1]['type']
                if curr in ['footer_l3', 'footer_l4'] and next_t.startswith('header'):
                    final_items.append({'type': 'empty_row'})
                if curr == 'footer_l2' and next_t.startswith('header'):
                    final_items.append({'type': 'empty_row'})
                if curr == 'footer_l1':
                    final_items.append({'type': 'empty_row'})

        # 描画ループ
        curr_idx = 0
        while curr_idx < len(final_items):
            draw_page_header_common(p_num); y = y_start
            rows_drawn = 0
            while rows_drawn < rows_per_page:
                if curr_idx < len(final_items):
                    item = final_items[curr_idx]
                    itype = item['type']
                    
                    # ★改ページ判定の修正
                    is_header = itype in ['header_l1', 'header_l2']
                    # 直前の項目を取得
                    prev_item = final_items[curr_idx-1] if curr_idx > 0 else None
                    # 「大項目(L1)」の直後に「中項目(L2)」が来た場合は、改ページ禁止（例外扱い）
                    is_l2_after_l1 = (itype == 'header_l2' and prev_item and prev_item['type'] == 'header_l1')
                    
                    # ページの先頭(rows_drawn=0)以外で、ヘッダーが来て、かつ「L1->L2連続」でないなら改ページ
                    if rows_drawn > 0 and is_header and not is_l2_after_l1:
                        rem = rows_per_page - rows_drawn
                        for _ in range(rem): draw_grid_line(y-row_height); y -= row_height
                        break

                    if itype == 'header_l1': draw_bold_string(col_x['name']+INDENT_L1, y-5*mm, item['label'], 10, COLOR_L1)
                    elif itype == 'header_l2': draw_bold_string(col_x['name']+INDENT_L2, y-5*mm, item['label'], 10, COLOR_L2)
                    elif itype == 'header_l3': draw_bold_string(col_x['name']+INDENT_L3, y-5*mm, item['label'], 10, COLOR_L3)
                    elif itype == 'header_l4': draw_bold_string(col_x['name']+INDENT_ITEM, y-5*mm, item['label'], 9, colors.black)
                    elif itype == 'item':
                        d = item['data']; c.setFont(FONT_NAME, 9); c.setFillColor(colors.black)
                        c.drawString(col_x['name']+INDENT_ITEM, y-5*mm, d.get('名称',''))
                        c.setFont(FONT_NAME, 8); c.drawString(col_x['spec']+1*mm, y-5*mm, d.get('規格',''))
                        c.setFont(FONT_NAME, 9)
                        if d['qty_val']: c.drawRightString(col_x['qty']+col_widths['qty']-2*mm, y-5*mm, f"{d['qty_val']:,.2f}")
                        c.drawCentredString(col_x['unit']+col_widths['unit']/2, y-5*mm, d.get('単位',''))
                        if d['price_val']: c.drawRightString(col_x['price']+col_widths['price']-2*mm, y-5*mm, f"{int(d['price_val']):,}")
                        if d['amt_val']: c.drawRightString(col_x['amt']+col_widths['amt']-2*mm, y-5*mm, f"{int(d['amt_val']):,}")
                        c.setFont(FONT_NAME, 8); c.drawString(col_x['rem']+1*mm, y-5*mm, d.get('備考',''))
                    elif itype == 'footer_l4':
                        draw_bold_string(col_x['name']+INDENT_ITEM, y-5*mm, item['label'], 9, colors.black)
                        c.setFont(FONT_NAME, 9); c.drawRightString(col_x['amt']+col_widths['amt']-2*mm, y-5*mm, f"{int(item['amt']):,}")
                    elif itype == 'footer_l3':
                        draw_bold_string(col_x['name']+INDENT_L3, y-5*mm, item['label'], 9, COLOR_L3)
                        c.setFont(FONT_NAME, 9); c.setFillColor(colors.black)
                        c.drawRightString(col_x['amt']+col_widths['amt']-2*mm, y-5*mm, f"{int(item['amt']):,}")
                    elif itype == 'footer_l2':
                        draw_bold_string(col_x['name']+INDENT_L2, y-5*mm, item['label'], 10, COLOR_L2)
                        c.setFont(FONT_NAME, 10); c.setFillColor(colors.black)
                        c.drawRightString(col_x['amt']+col_widths['amt']-2*mm, y-5*mm, f"{int(item['amt']):,}")
                        c.setLineWidth(1); c.setStrokeColor(COLOR_L2); c.line(x_base, y, right_edge, y)
                    elif itype == 'footer_l1':
                        draw_bold_string(col_x['name']+INDENT_L1, y-5*mm, item['label'], 10, COLOR_L1)
                        c.setFont(FONT_NAME, 10); c.setFillColor(colors.black)
                        c.drawRightString(col_x['amt']+col_widths['amt']-2*mm, y-5*mm, f"{int(item['amt']):,}")
                        c.setLineWidth(1); c.setStrokeColor(COLOR_L1); c.line(x_base, y, right_edge, y)
                    elif itype == 'empty_row': pass

                    draw_grid_line(y-row_height); y -= row_height; curr_idx += 1; rows_drawn += 1
                else:
                    rem = rows_per_page - rows_drawn
                    for _ in range(rem): draw_grid_line(y-row_height); y -= row_height
                    break
            
            draw_vertical_lines(y_start, y); c.showPage(); p_num += 1

    draw_page1()
    draw_page2()
    next_p = draw_page3_l1_summary(1)
    draw_details(next_p)
    c.save()
    buffer.seek(0)
    return buffer

# ---------------------------------------------------------
# 3. UI
# ---------------------------------------------------------
st.set_page_config(layout="wide")
st.title("📄 自動見積書作成システム")

with st.sidebar:
    st.header("📝 情報入力")
    sheet_url = st.text_input("スプレッドシートURL", placeholder="https://docs.google.com/...")
    client_name = st.text_input("施主名", value="")
    project_name = st.text_input("工事名", value="住宅新築工事")
    st.markdown("---")
    location = st.text_input("工事場所", value="木曽郡木曽町...")
    term = st.text_input("工期", value="令和 7年 12月 20日")
    expiry = st.text_input("有効期限", value="2ヶ月")
    target_date = st.date_input("発行日", value=datetime.today())
    st.markdown("---")
    company_name = st.text_input("会社名", value="株式会社 〇〇工務店")
    ceo_name = st.text_input("代表取締役", value="〇〇 〇〇")
    address = st.text_input("住所", value="長野県木曽郡〇〇町...")
    phone = st.text_input("電話番号", value="0264-xx-xxxx")
    fax = st.text_input("FAX番号", value="0264-xx-xxxx")

if st.button("作成開始", type="primary"):
    if not sheet_url or not client_name:
        st.error("URLと施主名は必須です。")
    else:
        with st.spinner('PDF生成中...'):
            df = get_data_from_url(sheet_url)
            if df is not None:
                params = {'client_name': client_name, 'project_name': project_name, 'location': location, 'term': term, 'expiry': expiry, 'date': target_date.strftime('%Y年 %m月 %d日'), 'company_name': company_name, 'ceo': ceo_name, 'address': address, 'phone': phone, 'fax': fax}
                pdf_bytes = create_estimate_pdf(df, params)
                if pdf_bytes:
                    st.success("完了")
                    st.download_button("ダウンロード", pdf_bytes, f"見積書_{client_name}.pdf", "application/pdf")
