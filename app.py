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
import math

# ---------------------------------------------------------
# ■ 設定エリア
# ---------------------------------------------------------
SHEET_NAME = "T_見積入力" 
FONT_FILE = "ipaexg.ttf" # 中身は明朝(ipaexm.ttf)想定
FONT_NAME = "IPAexMincho"

# ★ 色の定義
COLOR_L1 = colors.Color(0, 0.5, 0)      # 緑 (大項目)
COLOR_L2 = colors.Color(0, 0, 1)        # 青 (中項目)
COLOR_L3 = colors.Color(0.9, 0.4, 0)    # オレンジ (小項目)
COLOR_TEXT = colors.black               # 通常文字

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

    # --- ヘルパー ---
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

    # 太字描画 (色指定対応)
    def draw_bold_string(x, y, text, size, color=colors.black):
        c.setLineWidth(size * 0.03)
        text_obj = c.beginText(x, y)
        text_obj.setFont(FONT_NAME, size)
        text_obj.setFillColor(color)
        text_obj.setStrokeColor(color)
        text_obj.setTextRenderMode(2)
        text_obj.textOut(text)
        c.drawText(text_obj)
        c.setLineWidth(1)
        c.setFillColor(colors.black)
        c.setStrokeColor(colors.black)

    def draw_bold_centered_string(x, y, text, size, color=colors.black):
        text_w = c.stringWidth(text, FONT_NAME, size)
        draw_bold_string(x - text_w/2, y, text, size, color)

    total_grand = df['(自)金額'].apply(parse_amount).sum()
    tax_amount = total_grand * 0.1

    # ==========================================
    # 1ページ目：表紙
    # ==========================================
    def draw_page1_cover():
        draw_bold_centered_string(width/2, height - 60*mm, "御   見   積   書", 50, colors.darkblue)
        lw = 140*mm; lx = (width - lw)/2; ly = height - 65*mm
        c.setStrokeColor(colors.darkblue)
        c.setLineWidth(2); c.line(lx, ly, lx+lw, ly)
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

    draw_page1_cover()

    # ==========================================
    # 2ページ目：見積概要
    # ==========================================
    def draw_page2_summary():
        draw_bold_centered_string(width/2, height - 30*mm, "御   見   積   書", 32)
        c.setLineWidth(1); c.line(width/2 - 60*mm, height - 32*mm, width/2 + 60*mm, height - 32*mm)
        c.setLineWidth(0.5); c.line(width/2 - 60*mm, height - 33*mm, width/2 + 60*mm, height - 33*mm)

        c.setFont(FONT_NAME, 20); c.drawString(40*mm, height - 50*mm, f"{params['client_name']}  様")
        c.setFont(FONT_NAME, 12); c.drawString(40*mm, height - 60*mm, "下記のとおり御見積申し上げます")

        box_top = height - 70*mm; box_left = 40*mm; box_width = width - 80*mm; box_height = 110*mm
        c.setLineWidth(1.5); c.rect(box_left, box_top - box_height, box_width, box_height)
        c.setLineWidth(0.5); c.rect(box_left+1*mm, box_top - box_height+1*mm, box_width-2*mm, box_height-2*mm)

        line_sx = box_left + 10*mm; content_sx = line_sx + 30*mm; line_ex = box_left + box_width - 10*mm
        curr_y = box_top - 15*mm; gap = 12*mm

        draw_bold_string(line_sx, curr_y, "見積金額：", 14)
        amt_s = f"¥ {int(total_grand):,}-"
        draw_bold_string(content_sx, curr_y, amt_s, 18)
        tax_s = f"(別途消費税  ¥ {int(tax_amount):,})"
        c.setFont(FONT_NAME, 12); c.drawString(content_sx + c.stringWidth(amt_s, FONT_NAME, 18) + 5*mm, curr_y, tax_s)
        c.line(line_sx, curr_y-2*mm, line_ex, curr_y-2*mm)
        curr_y -= gap * 1.5

        items = [("工 事 名 ：", params['project_name']), ("工事場所 ：", params['location']),
                 ("工    期 ：", params['term']), ("そ の 他 ：", "別紙内訳書による"), ("見積有効期限：", params['expiry'])]
        for label, val in items:
            c.setFont(FONT_NAME, 12); c.drawString(line_sx, curr_y, label)
            c.setFont(FONT_NAME, 13); c.drawString(content_sx, curr_y, val)
            c.line(line_sx, curr_y-2*mm, line_ex, curr_y-2*mm)
            curr_y -= gap

        x_co = width - 100*mm; y_co = box_top - box_height - 20*mm
        wareki = to_wareki(datetime.strptime(params['date'], '%Y年 %m月 %d日'))
        c.setFont(FONT_NAME, 12); c.drawString(width - 80*mm, box_top + 5*mm, wareki)
        c.setFont(FONT_NAME, 13); c.drawString(x_co, y_co, params['company_name'])
        c.setFont(FONT_NAME, 11); c.drawString(x_co, y_co - 7*mm, f"代表取締役   {params['ceo']}")
        c.setFont(FONT_NAME, 10); c.drawString(x_co, y_co - 14*mm, f"〒 {params['address']}")
        c.drawString(x_co, y_co - 19*mm, f"TEL {params['phone']}  FAX {params['fax']}")
        c.showPage()

    draw_page2_summary()

    # ==========================================
    # 3ページ目以降：内訳明細書 (Grid Layout)
    # ==========================================
    
    # --- レイアウト定義 ---
    x_base = 15 * mm 
    content_width = width - 30 * mm
    
    # ★ 列幅調整 (備考を広く、他を少しタイトに)
    col_widths = {
        'name': 80 * mm, 'spec': 50 * mm, 'qty': 18 * mm, 
        'unit': 12 * mm, 'price': 25 * mm, 'amt': 30 * mm, 'rem': 0 * mm
    }
    col_widths['rem'] = content_width - sum(col_widths.values())

    col_x = {}
    curr_x = x_base
    for k in col_widths.keys():
        col_x[k] = curr_x
        curr_x += col_widths[k]
    right_edge = curr_x
    
    header_height = 9 * mm
    row_height = 7 * mm     # ★行間を7mmに縮小 (行数を増やす)
    
    # 上下の余白
    top_margin = 35 * mm
    bottom_margin = 20 * mm
    y_start = height - top_margin
    
    # 1ページあたりの行数を計算
    rows_per_page = int((height - top_margin - bottom_margin) / row_height)

    # 罫線描画関数
    def draw_grid_line(y_pos, color=colors.black, width=0.5):
        c.setLineWidth(width); c.setStrokeColor(color)
        c.line(x_base, y_pos, right_edge, y_pos)

    def draw_vertical_lines(y_top, y_btm):
        c.setLineWidth(0.5); c.setStrokeColor(colors.grey)
        for k in col_x: c.line(col_x[k], y_top, col_x[k], y_btm)
        c.line(right_edge, y_top, right_edge, y_btm)

    def draw_header_detail(p_num):
        # ページ上部情報
        header_y = height - 20 * mm
        c.setFillColor(colors.black)
        
        # 内訳明細書 (中央・下線)
        c.setFont(FONT_NAME, 16)
        title = "内 訳 明 細 書"
        title_w = c.stringWidth(title, FONT_NAME, 16)
        c.drawCentredString(width/2, header_y, title)
        c.setLineWidth(0.5); c.line(width/2 - title_w/2 - 5*mm, header_y - 2*mm, width/2 + title_w/2 + 5*mm, header_y - 2*mm)

        # 会社名 (右上)
        c.setFont(FONT_NAME, 10)
        c.drawRightString(right_edge, header_y, params['company_name'])
        
        # ページ番号
        c.drawRightString(right_edge, 10*mm, f"- {p_num} -")

        # 表ヘッダー
        hy = y_start
        c.setFillColor(colors.Color(0.95, 0.95, 0.95))
        c.rect(x_base, hy, right_edge - x_base, header_height, fill=1, stroke=0)
        c.setFillColor(colors.black)
        
        c.setFont(FONT_NAME, 10)
        txt_y = hy + 2.5*mm
        labels = {'name':"名 称", 'spec':"規 格", 'qty':"数 量", 'unit':"単位", 'price':"単 価", 'amt':"金 額", 'rem':"備 考"}
        for k, txt in labels.items():
            c.drawCentredString(col_x[k] + col_widths[k]/2, txt_y, txt)
        
        c.setStrokeColor(colors.black); c.setLineWidth(0.5)
        c.rect(x_base, hy, right_edge - x_base, header_height, stroke=1, fill=0)
        draw_vertical_lines(hy + header_height, hy)

    # --- データ準備 ---
    rows = df.to_dict('records')
    
    # 処理変数の初期化
    current_row_idx = 0
    page_num = 1
    
    # 集計用
    subtotal_l1 = 0; subtotal_l2 = 0; subtotal_l3 = 0
    curr_l1 = ""; curr_l2 = ""; curr_l3 = ""

    # 全データを処理するまでループ
    while current_row_idx < len(rows):
        draw_header_detail(page_num)
        y = y_start
        
        # 1ページ分の行ループ
        for _ in range(rows_per_page):
            # データがまだある場合
            if current_row_idx < len(rows):
                row = rows[current_row_idx]
                
                l1 = str(row.get('大項目', '')).strip(); l2 = str(row.get('中項目', '')).strip()
                l3 = str(row.get('小項目', '')).strip(); l4 = str(row.get('部分項目', '')).strip()
                name = str(row.get('名称', '')); spec = str(row.get('規格', ''))
                unit = str(row.get('単位', '')); rem = str(row.get('備考', ''))
                qty = parse_amount(row.get('数量', 0)); price = parse_amount(row.get('(自)単価', 0))
                amt = parse_amount(row.get('(自)金額', 0))

                # 改ページ判定 (大項目・中項目の変わり目)
                is_l1_change = (l1 and l1 != curr_l1)
                is_l2_change = (l2 and l2 != curr_l2)
                
                # ページの先頭でなく、かつ区切りが来た場合はループを抜けて改ページ
                if y != y_start and (is_l1_change or is_l2_change):
                    break # 現在のページの残り行は空行で埋められる

                # --- 描画処理 ---
                target_color = COLOR_TEXT
                is_bold_row = False
                row_text_size = 9 # 標準サイズ

                # 見出し行 (金額なし)
                if l1 and l1 != curr_l1:
                    draw_bold_string(col_x['name'] + 2*mm, y - 5*mm, f"■ {l1}", 10, COLOR_L1)
                    curr_l1 = l1; subtotal_l1 = 0; curr_l2=""; curr_l3=""
                    is_bold_row = True
                
                elif l2 and l2 != curr_l2:
                    draw_bold_string(col_x['name'] + 6*mm, y - 5*mm, f"● {l2}", 10, COLOR_L2)
                    curr_l2 = l2; subtotal_l2 = 0; curr_l3=""
                    is_bold_row = True
                
                elif l3 and l3 != curr_l3:
                    draw_bold_string(col_x['name'] + 10*mm, y - 5*mm, f"・ {l3}", 10, COLOR_L3)
                    curr_l3 = l3; subtotal_l3 = 0
                    is_bold_row = True

                elif name:
                    # 通常明細
                    subtotal_l3 += amt; subtotal_l2 += amt; subtotal_l1 += amt
                    
                    c.setFont(FONT_NAME, row_text_size); c.setFillColor(colors.black)
                    c.drawString(col_x['name'] + 12*mm, y - 5*mm, name)
                    c.setFont(FONT_NAME, 8)
                    c.drawString(col_x['spec'] + 1*mm, y - 5*mm, spec)
                    
                    # 部分項目なら 【 】
                    if l4:
                        c.setFont(FONT_NAME, row_text_size)
                        c.drawString(col_x['name'] + 15*mm, y - 5*mm, f"【{l4}】")

                    c.setFont(FONT_NAME, row_text_size)
                    if qty: c.drawRightString(col_x['qty'] + col_widths['qty'] - 2*mm, y - 5*mm, f"{qty:,.2f}")
                    c.drawCentredString(col_x['unit'] + col_widths['unit']/2, y - 5*mm, unit)
                    if price: c.drawRightString(col_x['price'] + col_widths['price'] - 2*mm, y - 5*mm, f"{int(price):,}")
                    if amt: c.drawRightString(col_x['amt'] + col_widths['amt'] - 2*mm, y - 5*mm, f"{int(amt):,}")
                    c.setFont(FONT_NAME, 8)
                    c.drawString(col_x['rem'] + 1*mm, y - 5*mm, rem)

                # 小計処理 (先読みして現在の行の直後に挿入すべきか判定したいが、
                # ここでは「データ行」として処理せず、次の行の処理前に割り込ませる必要がある。
                # 簡易的に「次の行」を見て、区切りなら現在の行として小計を出力するロジックにする)
                
                # ...しかし構造上、1行消費してしまうので、
                # ここではシンプルに「データ行を描画した」として進める。
                # 小計行は「データ行」とは別の行として扱う必要があるため、
                # 実は rows リスト自体に小計行を差し込んでおくのがベストだが、
                # 今回はロジックで対応する。
                
                current_row_idx += 1
                
                # グリッド線
                draw_grid_line(y - row_height)
                y -= row_height

                # --- 小計行の挿入チェック ---
                # 次の行の情報取得
                next_row = rows[current_row_idx] if current_row_idx < len(rows) else None
                n_l1 = str(next_row.get('大項目', '')).strip() if next_row else ""
                n_l2 = str(next_row.get('中項目', '')).strip() if next_row else ""
                n_l3 = str(next_row.get('小項目', '')).strip() if next_row else ""

                # 小項目計 (オレンジ)
                if curr_l3 and (n_l3 != curr_l3 or n_l2 != curr_l2 or n_l1 != curr_l1 or not next_row):
                    if subtotal_l3 > 0 and y > (y_start - rows_per_page * row_height):
                        draw_bold_string(col_x['name'] + 10*mm, y - 5*mm, f"【{curr_l3} 小計】", 9, COLOR_L3)
                        draw_bold_string(col_x['amt'] + col_widths['amt'] - 2*mm - 30*mm, y - 5*mm, f"{int(subtotal_l3):,}", 9, COLOR_L3) 
                        # 金額位置調整 (右寄せがdraw_boldにないので左寄せで調整... 簡易的にRightString使う)
                        c.setFont(FONT_NAME, 9); c.setFillColor(COLOR_L3)
                        c.drawRightString(col_x['amt'] + col_widths['amt'] - 2*mm, y - 5*mm, f"{int(subtotal_l3):,}")
                        
                        draw_grid_line(y - row_height)
                        y -= row_height
                
                # 中項目計 (青)
                if curr_l2 and (n_l2 != curr_l2 or n_l1 != curr_l1 or not next_row):
                    if subtotal_l2 > 0 and y > (y_start - rows_per_page * row_height):
                        draw_bold_string(col_x['name'] + 6*mm, y - 5*mm, f"【{curr_l2} 計】", 10, COLOR_L2)
                        c.setFont(FONT_NAME, 10); c.setFillColor(COLOR_L2)
                        c.drawRightString(col_x['amt'] + col_widths['amt'] - 2*mm, y - 5*mm, f"{int(subtotal_l2):,}")
                        
                        c.setLineWidth(1); c.setStrokeColor(COLOR_L2) # 青い太線
                        c.line(x_base, y, right_edge, y)
                        draw_grid_line(y - row_height)
                        y -= row_height
                
                # 大項目計 (緑)
                if curr_l1 and (n_l1 != curr_l1 or not next_row):
                    if subtotal_l1 > 0 and y > (y_start - rows_per_page * row_height):
                        draw_bold_string(col_x['name'] + 2*mm, y - 5*mm, f"■ {curr_l1} 合計", 10, COLOR_L1)
                        c.setFont(FONT_NAME, 10); c.setFillColor(COLOR_L1)
                        c.drawRightString(col_x['amt'] + col_widths['amt'] - 2*mm, y - 5*mm, f"{int(subtotal_l1):,}")
                        
                        c.setLineWidth(1); c.setStrokeColor(COLOR_L1) # 緑の太線
                        c.line(x_base, y, right_edge, y)
                        draw_grid_line(y - row_height)
                        y -= row_height
                        # 区切り行は入れず、次の見出しへ
                        
            else:
                # データ終了後の空行埋め
                draw_grid_line(y - row_height)
                y -= row_height
        
        # ページ終了時処理
        draw_vertical_lines(y_start, y) # 縦線を描画（上から下まで一気に）
        c.showPage()
        page_num += 1

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

if st.button("見積書を作成する", type="primary"):
    if not sheet_url or not client_name:
        st.error("URLと施主名は必須です。")
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
                    st.download_button("📥 PDFをダウンロード", pdf_bytes, f"見積書_{client_name}様.pdf", "application/pdf")
