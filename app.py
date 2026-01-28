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
        
        # DataFrame化 (全ての列を文字列として読み込む)
        df = pd.DataFrame(data[1:], columns=data[0])
        return df
    except Exception as e:
        st.error(f"読み込みエラー: {e}")
        return None

# ---------------------------------------------------------
# 2. PDF生成エンジン (横長・グリッド・小計対応)
# ---------------------------------------------------------
def create_estimate_pdf(df):
    buffer = io.BytesIO()
    # A4横向きに設定
    c = canvas.Canvas(buffer, pagesize=landscape(A4))
    width, height = landscape(A4)
    
    try:
        pdfmetrics.registerFont(TTFont(FONT_NAME, FONT_FILE))
    except:
        st.warning(f"フォントファイル({FONT_FILE})が見つかりません。")
        return None

    # --- レイアウト設定 (横長用) ---
    # 左余白
    x_base = 15 * mm
    # 各列の幅定義 [名称, 規格, 数量, 単位, 単価, 金額, 備考]
    # 合計幅が約270mmになるように調整
    col_widths = {
        'name': 85 * mm,
        'spec': 60 * mm,
        'qty':  20 * mm,
        'unit': 15 * mm,
        'price': 30 * mm,
        'amt':   35 * mm,
        'rem':   25 * mm
    }
    
    # 各列の開始X座標を計算
    col_x = {}
    current_x = x_base
    col_x['name'] = current_x; current_x += col_widths['name']
    col_x['spec'] = current_x; current_x += col_widths['spec']
    col_x['qty']  = current_x; current_x += col_widths['qty']
    col_x['unit'] = current_x; current_x += col_widths['unit']
    col_x['price'] = current_x; current_x += col_widths['price']
    col_x['amt']   = current_x; current_x += col_widths['amt']
    col_x['rem']   = current_x; current_x += col_widths['rem']
    
    right_edge = current_x # 表の右端

    # 行の高さ
    header_height = 8 * mm
    row_height = 7 * mm
    
    # 描画開始位置
    y_start = height - 50 * mm
    y = y_start
    page_num = 1

    # --- 数値変換ヘルパー ---
    def parse_amount(val):
        try:
            return float(str(val).replace('¥', '').replace(',', ''))
        except:
            return 0.0

    # 全体の合計金額計算
    total_grand = df['(自)金額'].apply(parse_amount).sum()

    # --- 描画ヘルパー関数 ---
    
    # グリッドの横線を描く
    def draw_grid_line(y_pos):
        c.setLineWidth(0.5)
        c.setStrokeColor(colors.black)
        c.line(x_base, y_pos, right_edge, y_pos)

    # グリッドの縦線を描く（行の高さ分だけ）
    def draw_vertical_lines(y_top, y_bottom):
        c.setLineWidth(0.5)
        c.setStrokeColor(colors.grey)
        for key in col_x:
            c.line(col_x[key], y_top, col_x[key], y_bottom)
        c.line(right_edge, y_top, right_edge, y_bottom) # 右端

    # 改ページ処理
    def check_page_break(current_y):
        if current_y < 20 * mm:
            c.setFont(FONT_NAME, 9)
            c.drawCentredString(width/2, 10*mm, f"- {page_num} -")
            c.showPage()
            return True
        return False

    # ヘッダー描画
    def draw_header(p_num):
        nonlocal y
        y = height - 40 * mm
        
        # タイトル
        c.setFont(FONT_NAME, 20)
        c.drawCentredString(width/2, height - 20*mm, "御 見 積 書")
        
        # 宛名・日付
        c.setFont(FONT_NAME, 12)
        c.drawString(x_base, height - 30*mm, "〇〇 様")
        c.drawRightString(right_edge, height - 20*mm, "No. 00001") # 仮
        c.drawRightString(right_edge, height - 25*mm, "2026年 1月 28日") # 仮

        # 合計金額（でかく）
        c.setFont(FONT_NAME, 14)
        c.drawString(x_base, height - 42*mm, f"御見積合計金額： ￥{int(total_grand):,}- (税込)")
        
        # 自社情報
        c.setFont(FONT_NAME, 10)
        c.drawString(width - 80*mm, height - 35*mm, "株式会社 〇〇工務店")
        
        # 表ヘッダー
        y -= 5 * mm
        c.setFillColor(colors.Color(0.9, 0.9, 0.9)) # 薄いグレー背景
        c.rect(x_base, y - header_height, right_edge - x_base, header_height, fill=1, stroke=0)
        c.setFillColor(colors.black)
        
        c.setFont(FONT_NAME, 10)
        # 文字位置調整 (中央寄せ)
        offset_y = y - header_height + 2.5*mm
        c.drawCentredString(col_x['name'] + col_widths['name']/2, offset_y, "名　称")
        c.drawCentredString(col_x['spec'] + col_widths['spec']/2, offset_y, "規　格")
        c.drawCentredString(col_x['qty']  + col_widths['qty']/2,  offset_y, "数 量")
        c.drawCentredString(col_x['unit'] + col_widths['unit']/2, offset_y, "単位")
        c.drawCentredString(col_x['price'] + col_widths['price']/2, offset_y, "単 価")
        c.drawCentredString(col_x['amt']   + col_widths['amt']/2,   offset_y, "金 額")
        c.drawCentredString(col_x['rem']   + col_widths['rem']/2,   offset_y, "備 考")
        
        c.setStrokeColor(colors.black)
        c.setLineWidth(1)
        c.rect(x_base, y - header_height, right_edge - x_base, header_height, stroke=1, fill=0)
        # 縦線
        draw_vertical_lines(y, y - header_height)
        
        y -= header_height

    # 初回ヘッダー
    draw_header(page_num)

    # --- ループ処理用の準備 ---
    # データリストに変換（インデックスアクセスするため）
    rows = df.to_dict('records')
    n = len(rows)
    
    # 小計計算用の変数
    subtotal_l1 = 0
    subtotal_l2 = 0
    subtotal_l3 = 0
    
    current_l1 = ""
    current_l2 = ""
    current_l3 = ""

    # メインループ
    for i in range(n):
        row = rows[i]
        
        # 各種値の取得
        l1 = str(row.get('大項目', '')).strip()
        l2 = str(row.get('中項目', '')).strip()
        l3 = str(row.get('小項目', '')).strip()
        name = str(row.get('名称', ''))
        spec = str(row.get('規格', ''))
        unit = str(row.get('単位', ''))
        rem  = str(row.get('備考', ''))
        
        qty_val = parse_amount(row.get('数量', 0))
        price_val = parse_amount(row.get('(自)単価', 0))
        amt_val = parse_amount(row.get('(自)金額', 0))

        # 改ページ判定
        if check_page_break(y):
            page_num += 1
            draw_header(page_num)

        # -------------------------------------------------
        # 1. 見出し行の描画 (変化があった場合)
        # -------------------------------------------------
        
        # 大項目見出し
        if l1 != "" and l1 != current_l1:
            c.setFont(FONT_NAME, 11)
            c.drawString(col_x['name'] + 2*mm, y - 5*mm, f"■ {l1}")
            draw_grid_line(y - row_height)
            draw_vertical_lines(y, y - row_height)
            y -= row_height
            current_l1 = l1
            subtotal_l1 = 0 # リセット
            current_l2 = ""; current_l3 = "" # 下位もリセット

        # 中項目見出し
        if l2 != "" and l2 != current_l2:
            c.setFont(FONT_NAME, 10)
            c.drawString(col_x['name'] + 6*mm, y - 5*mm, f"● {l2}")
            draw_grid_line(y - row_height)
            draw_vertical_lines(y, y - row_height)
            y -= row_height
            current_l2 = l2
            subtotal_l2 = 0
            current_l3 = ""

        # 小項目見出し
        if l3 != "" and l3 != current_l3:
            c.setFont(FONT_NAME, 10)
            c.drawString(col_x['name'] + 10*mm, y - 5*mm, f"・ {l3}")
            draw_grid_line(y - row_height)
            draw_vertical_lines(y, y - row_height)
            y -= row_height
            current_l3 = l3
            subtotal_l3 = 0

        # -------------------------------------------------
        # 2. 明細行の描画
        # -------------------------------------------------
        if name != "":
            # 加算
            subtotal_l3 += amt_val
            subtotal_l2 += amt_val
            subtotal_l1 += amt_val

            c.setFont(FONT_NAME, 9)
            # 名称 (インデント)
            c.drawString(col_x['name'] + 12*mm, y - 5*mm, name)
            # 規格
            c.setFont(FONT_NAME, 8) # 少し小さく
            c.drawString(col_x['spec'] + 1*mm, y - 5*mm, spec)
            
            c.setFont(FONT_NAME, 9)
            # 数量
            if qty_val != 0:
                c.drawRightString(col_x['qty'] + col_widths['qty'] - 2*mm, y - 5*mm, f"{qty_val:,.2f}")
            # 単位
            c.drawCentredString(col_x['unit'] + col_widths['unit']/2, y - 5*mm, unit)
            # 単価
            if price_val != 0:
                c.drawRightString(col_x['price'] + col_widths['price'] - 2*mm, y - 5*mm, f"{int(price_val):,}")
            # 金額
            if amt_val != 0:
                c.drawRightString(col_x['amt'] + col_widths['amt'] - 2*mm, y - 5*mm, f"{int(amt_val):,}")
            # 備考
            c.setFont(FONT_NAME, 8)
            c.drawString(col_x['rem'] + 1*mm, y - 5*mm, rem)

            # 罫線
            draw_grid_line(y - row_height)
            draw_vertical_lines(y, y - row_height)
            y -= row_height

        # -------------------------------------------------
        # 3. 小計行の判定と描画 (先読み)
        # -------------------------------------------------
        
        # 次の行を取得（なければNone）
        next_row = rows[i+1] if i+1 < n else None
        
        # 次の行の階層情報を取得
        next_l1 = str(next_row.get('大項目', '')).strip() if next_row else ""
        next_l2 = str(next_row.get('中項目', '')).strip() if next_row else ""
        next_l3 = str(next_row.get('小項目', '')).strip() if next_row else ""

        # --- 小項目小計 ---
        # 次の行で小項目が変わる、または中・大が変わる、またはデータ終了の場合
        if current_l3 != "" and (next_l3 != current_l3 or next_l2 != current_l2 or next_l1 != current_l1 or next_row is None):
            if subtotal_l3 > 0: # 0円なら表示しない
                c.setFont(FONT_NAME, 9)
                c.setFillColor(colors.Color(0, 0.4, 0)) # 深緑
                c.drawString(col_x['name'] + 10*mm, y - 5*mm, f"【{current_l3} 小計】")
                c.drawRightString(col_x['amt'] + col_widths['amt'] - 2*mm, y - 5*mm, f"{int(subtotal_l3):,}")
                c.setFillColor(colors.black)
                draw_grid_line(y - row_height)
                draw_vertical_lines(y, y - row_height)
                y -= row_height

        # --- 中項目小計 ---
        if current_l2 != "" and (next_l2 != current_l2 or next_l1 != current_l1 or next_row is None):
            if subtotal_l2 > 0:
                c.setFont(FONT_NAME, 9)
                c.setFillColor(colors.Color(0, 0.4, 0)) 
                c.drawString(col_x['name'] + 6*mm, y - 5*mm, f"【{current_l2} 計】")
                c.drawRightString(col_x['amt'] + col_widths['amt'] - 2*mm, y - 5*mm, f"{int(subtotal_l2):,}")
                c.setFillColor(colors.black)
                # 線を少し太く
                c.setLineWidth(1)
                c.line(x_base, y - row_height, right_edge, y - row_height)
                draw_vertical_lines(y, y - row_height)
                y -= row_height

        # --- 大項目小計 ---
        if current_l1 != "" and (next_l1 != current_l1 or next_row is None):
            if subtotal_l1 > 0:
                c.setFont(FONT_NAME, 10)
                c.setFillColor(colors.black) 
                c.drawString(col_x['name'] + 2*mm, y - 5*mm, f"■ {current_l1} 合計")
                c.drawRightString(col_x['amt'] + col_widths['amt'] - 2*mm, y - 5*mm, f"{int(subtotal_l1):,}")
                c.setLineWidth(1)
                c.line(x_base, y - row_height, right_edge, y - row_height)
                draw_vertical_lines(y, y - row_height)
                y -= row_height
                # 区切りの空行を入れる
                y -= 3*mm

    c.drawCentredString(width/2, 10*mm, f"- {page_num} -")
    c.save()
    buffer.seek(0)
    return buffer

# ---------------------------------------------------------
# 3. Streamlit UI
# ---------------------------------------------------------
st.title("📄 自動見積書作成システム (横長版)")

st.markdown("""
### 手順
1. 見積入力済みの **スプレッドシートのURL** をコピーしてください。
2. 下の欄に貼り付けて「読み込む」ボタンを押してください。
""")

sheet_url = st.text_input("スプレッドシートのURL", placeholder="https://docs.google.com/spreadsheets/d/...")

if st.button("スプレッドシートを読み込む"):
    if not sheet_url:
        st.warning("URLを入力してください。")
    else:
        with st.spinner('データを取得中...'):
            df = get_data_from_url(sheet_url)
            
            if df is not None:
                st.success("✅ 読み込み成功！")
                st.dataframe(df.head())

                pdf_bytes = create_estimate_pdf(df)
                if pdf_bytes:
                    st.download_button(
                        label="📥 見積書PDFをダウンロード",
                        data=pdf_bytes,
                        file_name="見積書_横.pdf",
                        mime="application/pdf"
                    )
