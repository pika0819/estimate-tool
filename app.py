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

# ★ 表示順設定 (ここに書かれた順番で出力されます。リストにないものは末尾に追加されます)
ORDER_LIST = [
    "建築工事",
    "電気設備工事",
    "給排水衛生設備工事",
    "空調換気設備工事",
    "諸経費"
]

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

        line_sx = box_left + 10*mm; label_end_x = line_sx + 28*mm; colon_x = label_end_x + 1*mm
        val_start_x = colon_x + 5*mm; line_ex = box_left + box_width - 10*mm
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

        x_co = width - 100*mm; y_co = box_bottom - 20*mm
        wareki = to_wareki(datetime.strptime(params['date'], '%Y年 %m月 %d日'))
        c.setFont(FONT_NAME, 12); c.drawString(width - 80*mm, box_top + 5*mm, wareki)
        c.setFont(FONT_NAME, 13); c.drawString(x_co, y_co, params['company_name'])
        c.setFont(FONT_NAME, 11); c.drawString(x_co, y_co - 7*mm, f"代表取締役   {params['ceo']}")
        c.setFont(FONT_NAME, 10); c.drawString(x_co, y_co - 14*mm, f"〒 {params['address']}")
        c.drawString(x_co, y_co - 19*mm, f"TEL {params['phone']}  FAX {params['fax']}")
        c.showPage()

    # 3. 総括表
    def draw_page3_total_summary(p_num):
        draw_page_header_common(p_num, "見 積 総 括 表")
        y = y_start
        
        # 集計 & ソート適用
        l1_summary = df.groupby('大項目', sort=False)['(自)金額'].apply(lambda x: x.apply(parse_amount).sum()).reset_index()
        
        # ソートロジック
        def sort_key(row):
            val = row['大項目']
            if val in ORDER_LIST: return ORDER_LIST.index(val)
            return 999
        l1_summary['sort_idx'] = l1_summary.apply(sort_key, axis=1)
        l1_summary = l1_summary.sort_values('sort_idx').drop('sort_idx', axis=1)

        for idx, row in l1_summary.iterrows():
            l1_name = row['大項目']; amount = row['(自)金額']
            if not l1_name: continue
            draw_bold_string(col_x['name'] + INDENT_L1, y-5*mm, f"■ {l1_name}", 10, COLOR_L1)
            c.setFont(FONT_NAME, 10); c.setFillColor(colors.black)
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
            l1 = str(row.get('大項目', '')).strip()
            l2 = str(row.get('中項目', '')).strip()
            amt = parse_amount(row.get('(自)金額', 0))
            if not l1: continue
            if l1 not in breakdown_data: breakdown_data[l1] = {'items': {}, 'total': 0}
            if l2:
                if l2 not in breakdown_data[l1]['items']: breakdown_data[l1]['items'][l2] = 0
                breakdown_data[l1]['items'][l2] += amt
            breakdown_data[l1]['total'] += amt

        # ソート
        sorted_l1_keys = sorted(breakdown_data.keys(), key=lambda k: ORDER_LIST.index(k) if k in ORDER_LIST else 999)

        draw_page_header_common(p_num, "内 訳 明 細 書 (集計)")
        y = y_start
        is_first_block = True
        
        for l1_name in sorted_l1_keys:
            data = breakdown_data[l1_name]
            l2_items = data['items']
            l1_total = data['total']
            spacer = 1 if not is_first_block else 0
            rows_needed = spacer + 1 + len(l2_items) + 1 
            rows_remaining = int((y - bottom_margin) / row_height)
            
            # ブロック判定
            if rows_needed > rows_remaining:
                while y > bottom_margin + 0.1: draw_grid_line(y - row_height); y -= row_height
                draw_vertical_lines(y_start, y); c.showPage()
                p_num += 1; draw_page_header_common(p_num, "内 訳 明 細 書 (集計)")
                y = y_start; is_first_block = True; spacer = 0

            if spacer: draw_grid_line(y - row_height); y -= row_height
            
            draw_bold_string(col_x['name'] + INDENT_L1, y-5*mm, f"■ {l1_name}", 10, COLOR_L1)
            draw_grid_line(y - row_height); y -= row_height
            
            for l2_name, l2_amt in l2_items.items():
                draw_bold_string(col_x['name'] + INDENT_L2, y-5*mm, f"● {l2_name}", 10, COLOR_L2)
                c.setFont(FONT_NAME, 10); c.setFillColor(colors.black)
                c.drawRightString(col_x['amt'] + col_widths['amt'] - 2*mm, y-5*mm, f"{int(l2_amt):,}")
                draw_grid_line(y - row_height); y -= row_height
            
            draw_bold_string(col_x['name'] + INDENT_L1, y-5*mm, f"【{l1_name} 計】", 10, COLOR_L1)
            c.setFont(FONT_NAME, 10); c.setFillColor(COLOR_L1)
            c.drawRightString(col_x['amt'] + col_widths['amt'] - 2*mm, y-5*mm, f"{int(l1_total):,}")
            draw_grid_line(y - row_height); y -= row_height
            is_first_block = False

        while y > bottom_margin + 0.1: draw_grid_line(y - row_height); y -= row_height
        draw_vertical_lines(y_start, y); c.showPage(); return p_num + 1

    # 5. 明細書 (詳細・ブロック制御)
    def draw_details(start_p_num):
        p_num = start_p_num
        
        # まず階層構造化する (Tree構造)
        # { L1: { L2: [Items] } }
        data_tree = {}
        
        for row in df.to_dict('records'):
            l1 = str(row.get('大項目', '')).strip()
            l2 = str(row.get('中項目', '')).strip()
            if not l1: continue
            if l1 not in data_tree: data_tree[l1] = {}
            if l2 not in data_tree[l1]: data_tree[l1][l2] = []
            
            amt = parse_amount(row.get('(自)金額', 0))
            item = row.copy()
            item.update({'amt_val': amt, 'qty_val': parse_amount(row.get('数量', 0)), 'price_val': parse_amount(row.get('(自)単価', 0))})
            if item.get('名称'):
                data_tree[l1][l2].append(item)

        # ソート
        sorted_l1 = sorted(data_tree.keys(), key=lambda k: ORDER_LIST.index(k) if k in ORDER_LIST else 999)

        # 描画開始
        draw_page_header_common(p_num, "内 訳 明 細 書 (詳細)"); y = y_start
        is_first_l1 = True

        for l1 in sorted_l1:
            l2_dict = data_tree[l1]
            l1_total = sum([sum([i['amt_val'] for i in items]) for items in l2_dict.values()])
            
            # L1 Header
            # L1が変わるとき、ページ残量が極端に少なければ改ページしてもいいが、
            # 基本はL2ブロックで判定するので、ここでは Spacer だけ処理
            if not is_first_l1:
                # 前のL1との間に空行を入れる（入らなければ改ページ）
                if y <= bottom_margin + row_height:
                    draw_vertical_lines(y_start, y); c.showPage()
                    p_num += 1; draw_page_header_common(p_num, "内 訳 明 細 書 (詳細)"); y = y_start
                else:
                    draw_grid_line(y - row_height); y -= row_height

            # L1 Header Draw
            if y <= bottom_margin + row_height: # ヘッダー書く場所なければ改ページ
                draw_vertical_lines(y_start, y); c.showPage()
                p_num += 1; draw_page_header_common(p_num, "内 訳 明 細 書 (詳細)"); y = y_start
            
            draw_bold_string(col_x['name']+INDENT_L1, y-5*mm, f"■ {l1}", 10, COLOR_L1)
            draw_grid_line(y - row_height); y -= row_height
            
            is_first_l1 = False
            
            # L2 Loop
            for l2, items in l2_dict.items():
                l2_total = sum([i['amt_val'] for i in items])
                
                # ★ブロック計算
                # 必要な行数 = L2Header(1) + Items(n) + L2Footer(1) + Spacer(1 if needed)
                # ここでは Spacer は計算に入れず、Footerまで入るかを見る
                rows_needed = 1 + len(items) + 1
                rows_remaining = int((y - bottom_margin) / row_height)
                
                if rows_needed > rows_remaining:
                    # 入らない -> 埋めて改ページ
                    while y > bottom_margin + 0.1: draw_grid_line(y - row_height); y -= row_height
                    draw_vertical_lines(y_start, y); c.showPage()
                    p_num += 1; draw_page_header_common(p_num, "内 訳 明 細 書 (詳細)"); y = y_start
                    
                    # 改ページしたので、L1見出しを再掲するか？
                    # 通常はしないが、わかりやすさのためにL1見出しを再描画するのもアリ。
                    # 今回は仕様にないのでそのままL2から書く。

                # --- 描画 ---
                # L2 Header
                draw_bold_string(col_x['name']+INDENT_L2, y-5*mm, f"● {l2}", 10, COLOR_L2)
                draw_grid_line(y - row_height); y -= row_height
                
                # Items
                for d in items:
                    c.setFont(FONT_NAME, 9); c.setFillColor(colors.black)
                    c.drawString(col_x['name']+INDENT_ITEM, y-5*mm, d.get('名称',''))
                    c.setFont(FONT_NAME, 8); c.drawString(col_x['spec']+1*mm, y-5*mm, d.get('規格',''))
                    c.setFont(FONT_NAME, 9)
                    if d['qty_val']: c.drawRightString(col_x['qty']+col_widths['qty']-2*mm, y-5*mm, f"{d['qty_val']:,.2f}")
                    c.drawCentredString(col_x['unit']+col_widths['unit']/2, y-5*mm, d.get('単位',''))
                    if d['price_val']: c.drawRightString(col_x['price']+col_widths['price']-2*mm, y-5*mm, f"{int(d['price_val']):,}")
                    if d['amt_val']: c.drawRightString(col_x['amt']+col_widths['amt']-2*mm, y-5*mm, f"{int(d['amt_val']):,}")
                    c.setFont(FONT_NAME, 8); c.drawString(col_x['rem']+1*mm, y-5*mm, d.get('備考',''))
                    draw_grid_line(y - row_height); y -= row_height
                
                # L2 Footer
                draw_bold_string(col_x['name']+INDENT_L2, y-5*mm, f"【{l2} 計】", 10, COLOR_L2)
                c.setFont(FONT_NAME, 10); c.setFillColor(colors.black)
                c.drawRightString(col_x['amt']+col_widths['amt']-2*mm, y-5*mm, f"{int(l2_total):,}")
                c.setLineWidth(1); c.setStrokeColor(COLOR_L2); c.line(x_base, y, right_edge, y) # Top Line
                draw_grid_line(y - row_height); y -= row_height
                
                # L2間の空行 (次のL2があれば)
                # リストの最後でなければ空行を入れたいが、
                # L1の最後の場合はL1 Footerが来るので空けない（というより詰めて書く）
                # 今回のコード構造上、L2ループ内では空けないで、L1 Footerの前に空行を入れるか判断
                pass 

            # L2 Loop End -> L1 Footer
            # L1計は中項目計の直下に書く
            draw_bold_string(col_x['name']+INDENT_L1, y-5*mm, f"■ {l1} 合計", 10, COLOR_L1)
            c.setFont(FONT_NAME, 10); c.setFillColor(colors.black)
            c.drawRightString(col_x['amt']+col_widths['amt']-2*mm, y-5*mm, f"{int(l1_total):,}")
            c.setLineWidth(1); c.setStrokeColor(COLOR_L1); c.line(x_base, y, right_edge, y)
            draw_grid_line(y - row_height); y -= row_height

        # End of Page
        while y > bottom_margin + 0.1: draw_grid_line(y - row_height); y -= row_height
        draw_vertical_lines(y_start, y); c.showPage(); p_num += 1

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
