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
INFO_SHEET_NAME = "現場情報"
FONT_FILE = "NotoSerifJP-Regular.ttf" 
FONT_NAME = "NotoSerifJP"

# 配色
COLOR_L1 = colors.Color(0.05, 0.35, 0.25) # 深緑
COLOR_L2 = colors.Color(0.1, 0.15, 0.45)  # 濃紺
COLOR_L3 = colors.Color(0.6, 0.3, 0.1)    # テラコッタ
COLOR_TEXT = colors.black
COLOR_TOTAL = colors.Color(0.7, 0.1, 0.15) # 深紅
COLOR_ACCENT_BLUE = colors.Color(0.15, 0.25, 0.55)

# インデント
INDENT_L1 = 1.0 * mm
INDENT_L2 = 2.5 * mm
INDENT_L3 = 4.5 * mm
INDENT_ITEM = 6.0 * mm

# ★ 表示順設定
SORT_ORDER = {
    "建築工事": [
        "共通仮設工事", "直接仮設工事", "特殊基礎工事", "基礎工事", 
        "木工事", "内装材", "外壁・断熱工事", "屋根・板金工事", "屋根改修工事",
        "鋼製建具工事", "木製建具工事", "塗装工事", "内装工事", "左官工事", "左官・タイル工事",
        "金物工事", "家具工事", "設備機器工事", "制震耐震工事", "雑工事",
        "玄関改修工事", "台所改修工事", "和室改修工事"
    ],
    "換気・暖房設備工事": ["換気工事"],
    "電気設備工事": ["配線工事", "照明工事"],
    "給排水衛生設備工事": [
        "屋外給水設備工事", "屋外排水工事", "屋外雨水工事", "器具・設置工事", 
        "屋内給水配管工事", "オイルタンク移設費", "諸経費"
    ],
    "諸経費": ["諸経費"]
}

# ---------------------------------------------------------
# 1. データ取得（現場情報シート対応版）
# ---------------------------------------------------------
def get_all_data_from_url(sheet_url):
    try:
        match = re.search(r"/d/([a-zA-Z0-9-_]+)", sheet_url)
        if not match:
            st.error("URLの形式が正しくありません。")
            return None, None
        spreadsheet_key = match.group(1)
        scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
        creds_dict = dict(st.secrets["gcp_service_account"])
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        client = gspread.authorize(creds)
        
        wb = client.open_by_key(spreadsheet_key)
        
        # 見積入力シートの取得
        sheet = wb.worksheet(SHEET_NAME)
        data = sheet.get_all_values()
        df = pd.DataFrame(data[1:], columns=data[0])
        
        # 現場情報シートの取得
        info_sheet = wb.worksheet(INFO_SHEET_NAME)
        info_data = info_sheet.get_all_values()
        info_dict = {str(row[0]).strip(): str(row[1]).strip() for row in info_data if len(row) >= 2}
        
        return df, info_dict
    except Exception as e:
        st.error(f"読み込みエラー: {e}")
        return None, None

# ---------------------------------------------------------
# 2. PDF生成エンジン（レイアウト変更なし）
# ---------------------------------------------------------
def create_estimate_pdf(df, params):
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=landscape(A4))
    width, height = landscape(A4)
    
    try:
        pdfmetrics.registerFont(TTFont(FONT_NAME, FONT_FILE))
    except:
        st.warning(f"フォントファイル({FONT_FILE})が見つかりません。")
        FONT_NAME_FB = "Helvetica" 

    def parse_amount(val):
        try: return float(str(val).replace('¥', '').replace(',', ''))
        except: return 0.0

    def to_wareki(date_str):
        # 現場情報シートから来る文字列を日付として解釈
        try:
            # 既に令和等の文字列ならそのまま、日付形式なら変換
            if '年' in date_str: return date_str
            dt_obj = pd.to_datetime(date_str)
            y = dt_obj.year; m = dt_obj.month; d = dt_obj.day
            if y >= 2019:
                r_y = y - 2018
                return f"令和 {r_y}年 {m}月 {d}日" if r_y != 1 else f"令和 元年 {m}月 {d}日"
            return dt_obj.strftime("%Y年 %m月 %d日")
        except:
            return date_str

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
    top_margin = 35 * mm; 
    
    # ★修正ポイント: 行の高さ(7mm)の倍数になるようにマージンを調整
    bottom_margin = 21 * mm 
    
    y_start = height - top_margin
    rows_per_page = int((height - top_margin - bottom_margin) / row_height)

    def draw_grid_line(y_pos, color=colors.black, width=0.5):
        c.setLineWidth(width); c.setStrokeColor(color); c.line(x_base, y_pos, right_edge, y_pos)
    
    def draw_vertical_lines(y_top, y_btm):
        c.setLineWidth(0.5); c.setStrokeColor(colors.grey)
        for k in col_x: c.line(col_x[k], y_top, col_x[k], y_btm)
        c.line(right_edge, y_top, right_edge, y_btm)

    def draw_page_header_common(p_num, title_text="内 訳 明 細 書"):
        hy = height - 20 * mm
        c.setFillColor(colors.black)
        c.setFont(FONT_NAME, 16); tw = c.stringWidth(title_text, FONT_NAME, 16)
        c.drawCentredString(width/2, hy, title_text)
        c.setLineWidth(0.5); c.line(width/2 - tw/2 - 5*mm, hy - 2*mm, width/2 + tw/2 + 5*mm, hy - 2*mm)
        c.setFont(FONT_NAME, 10); c.drawRightString(right_edge, hy, params['company_name'])
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
        draw_bold_centered_string(width/2, height - 60*mm, "御   見   積   書", 50, COLOR_ACCENT_BLUE)
        lw = 140*mm; lx = (width - lw)/2; ly = height - 65*mm
        c.setStrokeColor(COLOR_ACCENT_BLUE); c.setLineWidth(2); c.line(lx, ly, lx+lw, ly)
        c.setLineWidth(0.5); c.line(lx, ly-2*mm, lx+lw, ly-2*mm)
        c.setFillColor(colors.black); c.setStrokeColor(colors.black)

        draw_bold_centered_string(width/2, height - 110*mm, f"{params['client_name']}  様", 36)
        c.setLineWidth(1); c.line(width/2 - 80*mm, height - 112*mm, width/2 + 80*mm, height - 112*mm)
        draw_bold_centered_string(width/2, height - 140*mm, f"{params['project_name']}", 24)
        c.setLineWidth(0.5); c.line(width/2 - 80*mm, height - 142*mm, width/2 + 80*mm, height - 142*mm)
        
        wareki = to_wareki(params['date'])
        c.setFont(FONT_NAME, 14); c.drawString(40*mm, 50*mm, wareki)
        x_co = width - 100*mm; y_co = 50*mm
        draw_bold_string(x_co, y_co, params['company_name'], 18)
        c.setFont(FONT_NAME, 13); c.drawString(x_co, y_co - 10*mm, f"代表取締役   {params['ceo']}")
        c.setFont(FONT_NAME, 11); c.drawString(x_co, y_co - 20*mm, f"〒 {params['address']}")
        c.drawString(x_co, y_co - 26*mm, f"TEL: {params['phone']}")
        if params['fax']: c.drawString(x_co + 40*mm, y_co - 26*mm, f"FAX: {params['fax']}")
        c.showPage()

    # 2. 概要
    def draw_page2():
        draw_bold_centered_string(width/2, height - 30*mm, "御   見   積   書", 32)
        c.setLineWidth(1); c.line(width/2 - 60*mm, height - 32*mm, width/2 + 60*mm, height - 32*mm)
        c.setLineWidth(0.5); c.line(width/2 - 60*mm, height - 33*mm, width/2 + 60*mm, height - 33*mm)
        c.setFont(FONT_NAME, 20); c.drawString(40*mm, height - 50*mm, f"{params['client_name']}  様")
        c.setFont(FONT_NAME, 12); c.drawString(40*mm, height - 60*mm, "下記のとおり御見積申し上げます")

        box_top = height - 65*mm
        box_left = 30*mm; box_width = width - 60*mm; box_height = 120*mm
        box_bottom = box_top - box_height
        c.setLineWidth(1.5); c.rect(box_left, box_bottom, box_width, box_height)
        c.setLineWidth(0.5); c.rect(box_left+1.5*mm, box_bottom+1.5*mm, box_width-3*mm, box_height-3*mm)

        line_sx = box_left + 10*mm; label_end_x = line_sx + 28*mm; colon_x = label_end_x + 1*mm
        val_start_x = colon_x + 5*mm; line_ex = box_left + box_width - 10*mm
        curr_y = box_top - 15*mm; gap = 12*mm

        c.setFont(FONT_NAME, 14); c.drawRightString(label_end_x, curr_y, "見積金額")
        draw_bold_string(colon_x, curr_y, "：", 14)
        amt_s = f"¥ {int(total_grand):,}-"
        draw_bold_string(val_start_x, curr_y, amt_s, 18)
        tax_s = f"(別途消費税  ¥ {int(tax_amount):,})"
        c.setFont(FONT_NAME, 12); c.drawString(val_start_x + c.stringWidth(amt_s, FONT_NAME, 18) + 5*mm, curr_y, tax_s)
        c.setLineWidth(0.5); c.line(line_sx, curr_y-2*mm, line_ex, curr_y-2*mm)
        curr_y -= gap * 1.5

        items = [("工 事 名", params['project_name']), ("工事場所", params['location']),
                 ("工   期", params['term']), ("そ の 他", "別紙内訳書による"), ("見積有効期限", params['expiry'])]
        for label, val in items:
            c.setFont(FONT_NAME, 12); c.drawRightString(label_end_x, curr_y, label)
            c.drawString(colon_x, curr_y, "：")
            c.setFont(FONT_NAME, 13); c.drawString(val_start_x, curr_y, val)
            c.line(line_sx, curr_y-2*mm, line_ex, curr_y-2*mm)
            curr_y -= gap

        x_co = box_left + box_width - 90*mm
        y_co = box_bottom + 10*mm
        c.setFont(FONT_NAME, 13); c.drawString(x_co, y_co + 15*mm, params['company_name'])
        c.setFont(FONT_NAME, 11); c.drawString(x_co, y_co + 10*mm, f"代表取締役   {params['ceo']}")
        c.setFont(FONT_NAME, 10); c.drawString(x_co, y_co + 5*mm, f"〒 {params['address']}")
        c.drawString(x_co, y_co, f"TEL {params['phone']}  FAX {params['fax']}")

        wareki = to_wareki(params['date'])
        c.setFont(FONT_NAME, 12); c.drawString(width - 80*mm, box_top + 5*mm, wareki)
        c.showPage()

    # 3. 総括表
    def draw_page3_total_summary(p_num):
        draw_page_header_common(p_num, "見 積 総 括 表")
        y = y_start
        
        l1_summary = df.groupby('大項目', sort=False)['(自)金額'].apply(lambda x: x.apply(parse_amount).sum()).reset_index()
        def sort_key(row):
            val = row['大項目']
            return list(SORT_ORDER.keys()).index(val) if val in SORT_ORDER else 999
        l1_summary['sort_idx'] = l1_summary.apply(sort_key, axis=1)
        l1_summary = l1_summary.sort_values('sort_idx').drop('sort_idx', axis=1)

        for idx, row in l1_summary.iterrows():
            l1_name = row['大項目']; amount = row['(自)金額']
            if not l1_name: continue
            draw_bold_string(col_x['name'] + INDENT_L1, y-5*mm, f"■ {l1_name}", 10, COLOR_L1)
            c.setFont(FONT_NAME, 10); c.setFillColor(COLOR_L1) 
            c.drawRightString(col_x['amt'] + col_widths['amt'] - 2*mm, y-5*mm, f"{int(amount):,}")
            draw_grid_line(y - row_height); y -= row_height
        
        footer_rows = 3
        footer_start_y = bottom_margin + (footer_rows * row_height)
        while y > footer_start_y + 0.1: 
            draw_grid_line(y - row_height); y -= row_height
            
        y = footer_start_y
        labels = [("小計", total_grand), ("消費税", tax_amount), ("総合計", final_total)]
        for lbl, val in labels:
            c.setFillColor(colors.black)
            draw_bold_string(col_x['name'] + 20*mm, y-5*mm, f"【 {lbl} 】", 11, COLOR_TOTAL)
            c.setFont(FONT_NAME, 11); c.setFillColor(COLOR_TOTAL)
            c.drawRightString(col_x['amt'] + col_widths['amt'] - 2*mm, y-5*mm, f"{int(val):,}")
            draw_grid_line(y - row_height); y -= row_height
            
        draw_vertical_lines(y_start, y); c.showPage(); return p_num + 1

    # 4. 内訳書
    def draw_page4_breakdown(p_num):
        raw_rows = df.to_dict('records')
        breakdown_data = {} 
        for row in raw_rows:
            l1 = str(row.get('大項目', '')).strip(); l2 = str(row.get('中項目', '')).strip()
            amt = parse_amount(row.get('(自)金額', 0))
            if not l1: continue
            if l1 not in breakdown_data: breakdown_data[l1] = {'items': {}, 'total': 0}
            if l2:
                if l2 not in breakdown_data[l1]['items']: breakdown_data[l1]['items'][l2] = 0
                breakdown_data[l1]['items'][l2] += amt
            breakdown_data[l1]['total'] += amt

        sorted_l1_keys = sorted(breakdown_data.keys(), key=lambda k: list(SORT_ORDER.keys()).index(k) if k in SORT_ORDER else 999)

        draw_page_header_common(p_num, "内 訳 明 細 書 (集計)")
        y = y_start
        is_first_block = True
        
        for l1_name in sorted_l1_keys:
            data = breakdown_data[l1_name]
            l2_items = data['items']
            l1_total = data['total']
            
            l2_order = SORT_ORDER.get(l1_name, [])
            sorted_l2_keys = sorted(l2_items.keys(), key=lambda k: l2_order.index(k) if k in l2_order else 999)

            spacer = 1 if not is_first_block else 0
            rows_needed = spacer + 1 + len(sorted_l2_keys) + 1 
            rows_remaining = int((y - bottom_margin) / row_height)
            
            if rows_needed > rows_remaining:
                while y > bottom_margin + 0.1: draw_grid_line(y - row_height); y -= row_height
                draw_vertical_lines(y_start, y); c.showPage()
                p_num += 1; draw_page_header_common(p_num, "内 訳 明 細 書 (集計)")
                y = y_start; is_first_block = True; spacer = 0

            if spacer: draw_grid_line(y - row_height); y -= row_height
            
            draw_bold_string(col_x['name'] + INDENT_L1, y-5*mm, f"■ {l1_name}", 10, COLOR_L1)
            draw_grid_line(y - row_height); y -= row_height
            
            for l2_name in sorted_l2_keys:
                l2_amt = l2_items[l2_name]
                draw_bold_string(col_x['name'] + INDENT_L2, y-5*mm, f"● {l2_name}", 10, COLOR_L2)
                c.setFont(FONT_NAME, 10); c.setFillColor(COLOR_L2)
                c.drawRightString(col_x['amt'] + col_widths['amt'] - 2*mm, y-5*mm, f"{int(l2_amt):,}")
                draw_grid_line(y - row_height); y -= row_height
            
            draw_bold_string(col_x['name'] + INDENT_L1, y-5*mm, f"【{l1_name} 計】", 10, COLOR_L1)
            c.setFont(FONT_NAME, 10); c.setFillColor(COLOR_L1)
            c.drawRightString(col_x['amt'] + col_widths['amt'] - 2*mm, y-5*mm, f"{int(l1_total):,}")
            draw_grid_line(y - row_height); y -= row_height
            is_first_block = False

        while y > bottom_margin + 0.1: draw_grid_line(y - row_height); y -= row_height
        draw_vertical_lines(y_start, y); c.showPage(); return p_num + 1

    # 5. 明細書
    def draw_details(start_p_num):
        p_num = start_p_num
        data_tree = {}
        for row in df.to_dict('records'):
            l1 = str(row.get('大項目', '')).strip(); l2 = str(row.get('中項目', '')).strip()
            l3 = str(row.get('小項目', '')).strip(); l4 = str(row.get('部分項目', '')).strip()
            if not l1: continue
            if l1 not in data_tree: data_tree[l1] = {}
            if l2 not in data_tree[l1]: data_tree[l1][l2] = []
            item = row.copy()
            item.update({'amt_val': parse_amount(row.get('(自)金額', 0)), 
                         'qty_val': parse_amount(row.get('数量', 0)), 
                         'price_val': parse_amount(row.get('(自)単価', 0)),
                         'l3': l3, 'l4': l4})
            if item.get('名称'): data_tree[l1][l2].append(item)

        sorted_l1 = sorted(data_tree.keys(), key=lambda k: list(SORT_ORDER.keys()).index(k) if k in SORT_ORDER else 999)

        draw_page_header_common(p_num, "内 訳 明 細 書 (詳細)"); y = y_start
        is_first_l1 = True

        for l1 in sorted_l1:
            l2_dict = data_tree[l1]
            l1_total = sum([sum([i['amt_val'] for i in items]) for items in l2_dict.values()])
            
            l2_order = SORT_ORDER.get(l1, [])
            sorted_l2 = sorted(l2_dict.keys(), key=lambda k: l2_order.index(k) if k in l2_order else 999)

            if not is_first_l1:
                if y <= bottom_margin + row_height * 2:
                    while y > bottom_margin + 0.1: draw_grid_line(y - row_height); y -= row_height
                    draw_vertical_lines(y_start, bottom_margin)
                    c.showPage()
                    p_num += 1; draw_page_header_common(p_num, "内 訳 明 細 書 (詳細)"); y = y_start
                else:
                    draw_grid_line(y - row_height); y -= row_height

            # 大項目ヘッダー
            if y <= bottom_margin + row_height:
                while y > bottom_margin + 0.1: draw_grid_line(y - row_height); y -= row_height
                draw_vertical_lines(y_start, bottom_margin)
                c.showPage()
                p_num += 1; draw_page_header_common(p_num, "内 訳 明 細 書 (詳細)"); y = y_start
            
            draw_bold_string(col_x['name']+INDENT_L1, y-5*mm, f"■ {l1}", 10, COLOR_L1)
            draw_grid_line(y - row_height); y -= row_height
            is_first_l1 = False
            
            for i_l2, l2 in enumerate(sorted_l2):
                items = l2_dict[l2]
                l2_total = sum([i['amt_val'] for i in items])
                
                block_items = []
                block_items.append({'type': 'header_l2', 'label': f"● {l2}"})
                
                curr_l3 = ""; curr_l4 = ""; sub_l3 = 0; sub_l4 = 0
                temp_rows = []
                
                for itm in items:
                    l3 = itm['l3']; l4 = itm['l4']; amt = itm['amt_val']
                    l3_chg = (l3 and l3 != curr_l3); l4_chg = (l4 and l4 != curr_l4)
                    
                    if curr_l4 and (l4_chg or l3_chg):
                        temp_rows.append({'type': 'footer_l4', 'label': f"【{curr_l4}】 小計", 'amt': sub_l4})
                        if l4 or l3_chg: temp_rows.append({'type': 'empty_row'})
                        curr_l4 = ""; sub_l4 = 0
                    if curr_l3 and l3_chg:
                        temp_rows.append({'type': 'footer_l3', 'label': f"【{curr_l3} 小計】", 'amt': sub_l3})
                        if l3: temp_rows.append({'type': 'empty_row'})
                        curr_l3 = ""; sub_l3 = 0
                    
                    if l3_chg: temp_rows.append({'type': 'header_l3', 'label': f"・ {l3}"}); curr_l3 = l3
                    if l4_chg: temp_rows.append({'type': 'header_l4', 'label': f"【{l4}】"}); curr_l4 = l4
                    
                    sub_l3 += amt; sub_l4 += amt
                    temp_rows.append({'type': 'item', 'data': itm})
                
                if curr_l4: temp_rows.append({'type': 'footer_l4', 'label': f"【{curr_l4}】 小計", 'amt': sub_l4})
                if curr_l3: temp_rows.append({'type': 'footer_l3', 'label': f"【{curr_l3} 小計】", 'amt': sub_l3})
                
                block_items.extend(temp_rows)
                block_items.append({'type': 'footer_l2', 'label': f"【{l2} 計】", 'amt': l2_total})
                
                is_last_l2 = (i_l2 == len(sorted_l2) - 1)
                
                if is_last_l2:
                     block_items.append({'type': 'footer_l1', 'label': f"【{l1} 計】", 'amt': l1_total})
                else:
                    block_items.append({'type': 'empty_row'}); block_items.append({'type': 'empty_row'})
                
                while block_items and block_items[-1]['type'] == 'empty_row': block_items.pop()

                active_l3_label = None
                active_l4_label = None
                l2_has_started = False 

                # 描画ループ
                for b in block_items:
                    itype = b['type']

                    # 改ページ判定
                    force_stay = (itype == 'footer_l1')
                    
                    if y - row_height < bottom_margin - 0.1 and not force_stay:
                        temp_y = y
                        while temp_y > bottom_margin + 0.1:
                            draw_grid_line(temp_y - row_height)
                            temp_y -= row_height

                        draw_vertical_lines(y_start, bottom_margin) 
                        
                        c.showPage()
                        p_num += 1; draw_page_header_common(p_num, "内 訳 明 細 書 (詳細)"); y = y_start
                        
                        draw_bold_string(col_x['name']+INDENT_L1, y-5*mm, f"■ {l1} (続き)", 10, COLOR_L1)
                        draw_grid_line(y - row_height); y -= row_height
                        
                        if l2_has_started and itype != 'footer_l1':
                            draw_bold_string(col_x['name']+INDENT_L2, y-5*mm, f"● {l2} (続き)", 10, COLOR_L2)
                            draw_grid_line(y - row_height); y -= row_height

                        if active_l3_label:
                            draw_bold_string(col_x['name']+INDENT_L3, y-5*mm, f"{active_l3_label} (続き)", 10, COLOR_L3)
                            draw_grid_line(y - row_height); y -= row_height
                        
                        if active_l4_label:
                            draw_bold_string(col_x['name']+INDENT_ITEM, y-5*mm, f"{active_l4_label} (続き)", 9, colors.black)
                            draw_grid_line(y - row_height); y -= row_height

                    # 底打ちロジック (footerのみ)
                    if itype in ['footer_l2', 'footer_l1']:
                        target_row_from_bottom = 0
                        if itype == 'footer_l2' and is_last_l2: target_row_from_bottom = 1
                        
                        target_y = bottom_margin + (target_row_from_bottom * row_height)
                        if y > target_y + 0.1:
                            while y > target_y + 0.1: draw_grid_line(y - row_height); y -= row_height

                    # --- 描画処理 ---
                    if itype == 'header_l2':
                        draw_bold_string(col_x['name']+INDENT_L2, y-5*mm, b['label'], 10, COLOR_L2)
                    elif itype == 'header_l3':
                        draw_bold_string(col_x['name']+INDENT_L3, y-5*mm, b['label'], 10, COLOR_L3)
                    elif itype == 'header_l4':
                        draw_bold_string(col_x['name']+INDENT_ITEM, y-5*mm, b['label'], 9, colors.black)
                    elif itype == 'item':
                        d = b['data']; c.setFont(FONT_NAME, 9); c.setFillColor(colors.black)
                        c.drawString(col_x['name']+INDENT_ITEM, y-5*mm, d.get('名称',''))
                        c.setFont(FONT_NAME, 8); c.drawString(col_x['spec']+1*mm, y-5*mm, d.get('規格',''))
                        c.setFont(FONT_NAME, 9)
                        if d['qty_val']: c.drawRightString(col_x['qty']+col_widths['qty']-2*mm, y-5*mm, f"{d['qty_val']:,.2f}")
                        c.drawCentredString(col_x['unit']+col_widths['unit']/2, y-5*mm, d.get('単位',''))
                        if d['price_val']: c.drawRightString(col_x['price']+col_widths['price']-2*mm, y-5*mm, f"{int(d['price_val']):,}")
                        if d['amt_val']: c.drawRightString(col_x['amt']+col_widths['amt']-2*mm, y-5*mm, f"{int(d['amt_val']):,}")
                        c.setFont(FONT_NAME, 8); c.drawString(col_x['rem']+1*mm, y-5*mm, d.get('備考',''))
                    elif itype == 'footer_l4':
                        draw_bold_string(col_x['name']+INDENT_ITEM, y-5*mm, b['label'], 9, colors.black)
                        c.setFont(FONT_NAME, 9); c.drawRightString(col_x['amt']+col_widths['amt']-2*mm, y-5*mm, f"{int(b['amt']):,}")
                    
                    elif itype == 'footer_l3':
                        draw_bold_string(col_x['name']+INDENT_L3, y-5*mm, b['label'], 9, COLOR_L3)
                        c.setFont(FONT_NAME, 9); c.setFillColor(COLOR_L3) 
                        c.drawRightString(col_x['amt']+col_widths['amt']-2*mm, y-5*mm, f"{int(b['amt']):,}")
                    elif itype == 'footer_l2':
                        draw_bold_string(col_x['name']+INDENT_L2, y-5*mm, b['label'], 10, COLOR_L2)
                        c.setFont(FONT_NAME, 10); c.setFillColor(COLOR_L2)
                        c.drawRightString(col_x['amt']+col_widths['amt']-2*mm, y-5*mm, f"{int(b['amt']):,}")
                        c.setLineWidth(1); c.setStrokeColor(COLOR_L2); c.line(x_base, y, right_edge, y)
                    elif itype == 'footer_l1':
                        draw_bold_string(col_x['name']+INDENT_L1, y-5*mm, b['label'], 10, COLOR_L1)
                        c.setFont(FONT_NAME, 10); c.setFillColor(COLOR_L1)
                        c.drawRightString(col_x['amt']+col_widths['amt']-2*mm, y-5*mm, f"{int(b['amt']):,}")
                        c.setLineWidth(1); c.setStrokeColor(COLOR_L1); c.line(x_base, y, right_edge, y)
                    elif itype == 'empty_row': pass

                    draw_grid_line(y - row_height); y -= row_height

                    if itype == 'header_l2': l2_has_started = True
                    elif itype == 'header_l3': active_l3_label = b['label']
                    elif itype == 'footer_l3': active_l3_label = None
                    elif itype == 'header_l4': active_l4_label = b['label']
                    elif itype == 'footer_l4': active_l4_label = None

        while y > bottom_margin + 0.1: draw_grid_line(y - row_height); y -= row_height
        draw_vertical_lines(y_start, bottom_margin)
        c.showPage(); p_num += 1
        return p_num

    # --- 実行 ---
    draw_page1()
    draw_page2()
    p_next = draw_page3_total_summary(1)
    p_next = draw_page4_breakdown(p_next)
    draw_details(p_next)

    c.save()
    buffer.seek(0)
    return buffer

# ---------------------------------------------------------
# 3. UI（セキュリティ＆現場情報自動取得対応）
# ---------------------------------------------------------
st.set_page_config(layout="wide")
st.title("📄 自動見積書作成システム")

# セッション状態の管理（URL破棄用）
if 'pdf_ready' not in st.session_state:
    st.session_state.pdf_ready = False
if 'pdf_data' not in st.session_state:
    st.session_state.pdf_data = None
if 'filename' not in st.session_state:
    st.session_state.filename = ""

if not st.session_state.pdf_ready:
    with st.sidebar:
        st.header("🔑 セキュリティ入力")
        # 伏せ字でURLを入力
        input_url = st.text_input("スプレッドシートURL", type="password", placeholder="https://docs.google.com/...")
    
    if st.button("作成開始", type="primary"):
        if not input_url:
            st.error("URLを入力してください。")
        else:
            with st.spinner('データを読み込み中...'):
                df, info_dict = get_all_data_from_url(input_url)
                if df is not None and info_dict is not None:
                    # 現場情報シートからパラメータを整理
                    # PDF生成エンジンが期待するキー形式に変換
                    params = {
                        'client_name': info_dict.get('施主名', ''),
                        'project_name': info_dict.get('工事名', ''),
                        'location': info_dict.get('工事場所', ''),
                        'term': info_dict.get('工期', ''),
                        'expiry': info_dict.get('見積もり書有効期限', ''),
                        'date': info_dict.get('発行日', datetime.today().strftime('%Y/%m/%d')),
                        'company_name': info_dict.get('会社名', ''),
                        'ceo': info_dict.get('代表取締役', ''),
                        'address': info_dict.get('住所', ''),
                        'phone': info_dict.get('電話番号', ''),
                        'fax': info_dict.get('FAX番号', '')
                    }
                    
                    # PDF生成
                    pdf_bytes = create_estimate_pdf(df, params)
                    
                    # ファイル名の生成: 発行日_施主名_工事名_見積もり仕様.pdf
                    date_val = params['date'].replace('/', '').replace('-', '').replace('年', '').replace('月', '').replace('日', '')
                    spec = info_dict.get('見積もり仕様', '見積')
                    filename = f"{date_val}_{params['client_name']}_{params['project_name']}_{spec}.pdf"
                    
                    st.session_state.pdf_data = pdf_bytes
                    st.session_state.filename = filename
                    st.session_state.pdf_ready = True
                    st.rerun()

else:
    st.success("✅ PDF生成が完了しました。URL情報は破棄されました。")
    st.info(f"ファイル名: {st.session_state.filename}")
    
    col1, col2 = st.columns(2)
    with col1:
        st.download_button(
            "📥 ダウンロード", 
            st.session_state.pdf_data, 
            file_name=st.session_state.filename, 
            mime="application/pdf"
        )
    with col2:
        if st.button("別のシートを作成する"):
            st.session_state.pdf_ready = False
            st.session_state.pdf_data = None
            st.rerun()

