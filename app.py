import io
import re
from datetime import datetime
from typing import Optional, Tuple, Dict, Any, List

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

# ---------------------------------------------------------
# ■ Configuration & Constants
# ---------------------------------------------------------
class Config:
    SHEET_NAME = "T_見積入力"
    INFO_SHEET_NAME = "現場情報"
    FONT_FILE = "NotoSerifJP-Regular.ttf"
    FONT_NAME = "NotoSerifJP"
    FONT_NAME_FALLBACK = "Helvetica"

class Style:
    # HexColor definitions
    COLOR_L1 = colors.HexColor('#0D5940')
    COLOR_L2 = colors.HexColor('#1A2673')
    COLOR_L3 = colors.HexColor('#994D1A')
    COLOR_TEXT = colors.HexColor('#000000')
    COLOR_TOTAL = colors.HexColor('#B31A26')
    COLOR_ACCENT_BLUE = colors.HexColor('#26408C')
    
    # Layout dimensions
    MARGIN_TOP = 35 * mm
    MARGIN_BOTTOM = 21 * mm
    ROW_HEIGHT = 7 * mm
    HEADER_HEIGHT = 9 * mm
    X_BASE = 15 * mm
    
    # Indentations
    INDENT_L1 = 1.0 * mm
    INDENT_L2 = 2.5 * mm
    INDENT_L3 = 4.5 * mm
    INDENT_ITEM = 6.0 * mm

# ---------------------------------------------------------
# 1. Helper Functions (Business Logic)
# ---------------------------------------------------------
def parse_amount(val: Any) -> float:
    """金額文字列を数値に変換する安全なパーサー"""
    try:
        return float(str(val).replace('¥', '').replace(',', ''))
    except (ValueError, TypeError):
        return 0.0

def to_wareki(date_str: str) -> str:
    """西暦文字列を和暦に変換"""
    try:
        if '年' in str(date_str): return str(date_str)
        dt_obj = pd.to_datetime(date_str)
        y, m, d = dt_obj.year, dt_obj.month, dt_obj.day
        
        if y >= 2019:
            r_y = y - 2018
            era = "令和"
            year_str = f"{r_y}年" if r_y != 1 else "元年"
        else:
            # 必要に応じて平成などを追加可能。現状は簡易実装
            return dt_obj.strftime("%Y年 %m月 %d日")
            
        return f"{era} {year_str} {m}月 {d}日"
    except Exception:
        return str(date_str)

# ---------------------------------------------------------
# 2. Data Access Layer
# ---------------------------------------------------------
@st.cache_data(ttl=600)  # 10分間キャッシュしてAPI制限を回避・高速化
def get_all_data_from_url(sheet_url: str, secrets: Dict) -> Tuple[Optional[pd.DataFrame], Optional[Dict]]:
    """GCP認証を行いスプレッドシートからデータを取得する"""
    try:
        match = re.search(r"/d/([a-zA-Z0-9-_]+)", sheet_url)
        if not match:
            st.error("URLの形式が正しくありません。")
            return None, None
        
        spreadsheet_key = match.group(1)
        scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
        creds = ServiceAccountCredentials.from_json_keyfile_dict(secrets, scope)
        client = gspread.authorize(creds)
        
        wb = client.open_by_key(spreadsheet_key)
        
        # Fetch Data
        sheet = wb.worksheet(Config.SHEET_NAME)
        data = sheet.get_all_values()
        df = pd.DataFrame(data[1:], columns=data[0])
        
        info_sheet = wb.worksheet(Config.INFO_SHEET_NAME)
        info_data = info_sheet.get_all_values()
        info_dict = {str(row[0]).strip(): str(row[1]).strip() for row in info_data if len(row) >= 2}
        
        return df, info_dict
    except Exception as e:
        st.error(f"データ読み込みエラー: {e}")
        return None, None

# ---------------------------------------------------------
# 3. PDF Generator Engine
# ---------------------------------------------------------
class EstimatePDFGenerator:
    """見積書PDF生成クラス"""
    
    def __init__(self, df: pd.DataFrame, params: Dict[str, str]):
        self.buffer = io.BytesIO()
        self.c = canvas.Canvas(self.buffer, pagesize=landscape(A4))
        self.width, self.height = landscape(A4)
        self.df = df
        self.params = params
        
        # Font setup
        try:
            pdfmetrics.registerFont(TTFont(Config.FONT_NAME, Config.FONT_FILE))
            self.font = Config.FONT_NAME
        except:
            self.font = Config.FONT_NAME_FALLBACK

        # Grid setup
        self.content_width = self.width - 30 * mm
        self._setup_columns()
        
        # Calculation
        self.total_grand = df['見積金額'].apply(parse_amount).sum()
        self.tax_amount = self.total_grand * 0.1
        self.final_total = self.total_grand + self.tax_amount

    def _setup_columns(self):
        """列幅の定義"""
        widths = {
            'name': 75*mm, 'spec': 67.5*mm, 'qty': 19*mm, 
            'unit': 12*mm, 'price': 27*mm, 'amt': 29*mm, 'rem': 0*mm
        }
        widths['rem'] = self.content_width - sum(widths.values())
        
        self.col_x = {}
        curr_x = Style.X_BASE
        for k, w in widths.items():
            self.col_x[k] = curr_x
            curr_x += w
        
        self.col_widths = widths
        self.right_edge = curr_x
        self.y_start = self.height - Style.MARGIN_TOP

    def _draw_bold_string(self, x, y, text, size, color=colors.black):
        self.c.saveState()
        self.c.setLineWidth(size * 0.03)
        t_obj = self.c.beginText(x, y)
        t_obj.setFont(self.font, size)
        t_obj.setFillColor(color)
        t_obj.setStrokeColor(color)
        t_obj.setTextRenderMode(2)
        t_obj.textOut(str(text))
        self.c.drawText(t_obj)
        self.c.restoreState()

    def _draw_centered_bold(self, x, y, text, size, color=colors.black):
        tw = self.c.stringWidth(str(text), self.font, size)
        self._draw_bold_string(x - tw/2, y, text, size, color)

    def _draw_grid(self, y_top, y_bottom):
        self.c.saveState()
        self.c.setLineWidth(0.5)
        self.c.setStrokeColor(colors.grey)
        for k in self.col_x:
            self.c.line(self.col_x[k], y_top, self.col_x[k], y_bottom)
        self.c.line(self.right_edge, y_top, self.right_edge, y_bottom)
        
        curr = y_top
        while curr > y_bottom - 0.1:
            self.c.setStrokeColor(colors.black)
            self.c.line(Style.X_BASE, curr, self.right_edge, curr)
            curr -= Style.ROW_HEIGHT
        
        self.c.setStrokeColor(colors.black)
        self.c.line(Style.X_BASE, y_bottom, self.right_edge, y_bottom)
        self.c.restoreState()

    def _draw_page_header(self, p_num, title):
        hy = self.height - 20 * mm
        self.c.setFillColor(colors.black)
        self.c.setFont(self.font, 16)
        tw = self.c.stringWidth(title, self.font, 16)
        self.c.drawCentredString(self.width/2, hy, title)
        self.c.setLineWidth(0.5)
        self.c.line(self.width/2 - tw/2 - 5*mm, hy - 2*mm, self.width/2 + tw/2 + 5*mm, hy - 2*mm)
        
        self.c.setFont(self.font, 10)
        self.c.drawRightString(self.right_edge, hy, self.params['company_name'])
        self.c.drawCentredString(self.width/2, 10*mm, f"- {p_num} -")

        # Table Header
        grid_y = self.y_start
        self.c.setFillColor(colors.Color(0.95, 0.95, 0.95))
        self.c.rect(Style.X_BASE, grid_y, self.right_edge - Style.X_BASE, Style.HEADER_HEIGHT, fill=1, stroke=0)
        
        self.c.setFillColor(colors.black)
        self.c.setFont(self.font, 10)
        txt_y = grid_y + 2.5*mm
        labels = {'name':"名 称", 'spec':"規 格", 'qty':"数 量", 'unit':"単位", 'price':"単 価", 'amt':"金 額", 'rem':"備 考"}
        for k, txt in labels.items():
            self.c.drawCentredString(self.col_x[k] + self.col_widths[k]/2, txt_y, txt)
        
        self.c.setStrokeColor(colors.black)
        self.c.setLineWidth(0.5)
        self.c.rect(Style.X_BASE, grid_y, self.right_edge - Style.X_BASE, Style.HEADER_HEIGHT, stroke=1, fill=0)
        
        # Vertical lines for header
        self.c.setLineWidth(0.5)
        self.c.setStrokeColor(colors.grey)
        for k in self.col_x:
            self.c.line(self.col_x[k], grid_y + Style.HEADER_HEIGHT, self.col_x[k], grid_y)
        self.c.line(self.right_edge, grid_y + Style.HEADER_HEIGHT, self.right_edge, grid_y)

    def draw_cover(self):
        """表紙描画"""
        # Title
        title_text = "御   見   積   書"
        lw = 180*mm
        lx = (self.width - lw)/2
        ly = self.height - 57*mm 
        
        self.c.saveState()
        self.c.setFillAlpha(0.2)
        self.c.setStrokeColor(colors.HexColor('#c2c9de'))
        self.c.setLineWidth(14)
        self.c.line(lx, ly, lx+lw, ly)
        self.c.restoreState()

        self.c.saveState()
        t = self.c.beginText()
        t.setFont(self.font, 45)
        t.setFillColor(Style.COLOR_ACCENT_BLUE)
        t.setCharSpace(10)
        tw = self.c.stringWidth(title_text, self.font, 45) + (len(title_text)-1) * 10
        t.setTextOrigin(self.width/2 - tw/2, self.height - 55*mm)
        t.textOut(title_text)
        self.c.drawText(t)
        self.c.restoreState()

        # Client & Project
        self._draw_centered_bold(self.width/2, self.height - 110*mm, f"{self.params['client_name']}", 32)
        self.c.setLineWidth(1)
        self.c.line(self.width/2 - 60*mm, self.height - 112*mm, self.width/2 + 60*mm, self.height - 112*mm)

        self._draw_centered_bold(self.width/2, self.height - 140*mm, f"{self.params['project_name']}", 24)
        self.c.setLineWidth(0.5)
        self.c.line(self.width/2 - 50*mm, self.height - 142*mm, self.width/2 + 50*mm, self.height - 142*mm)

        # Company Info
        wareki = to_wareki(self.params['date'])
        self.c.setFont(self.font, 14)
        self.c.drawString(40*mm, 50*mm, wareki)
        
        x_co = self.width - 100*mm
        y_co = 50*mm
        self._draw_bold_string(x_co, y_co, self.params['company_name'], 18)
        self.c.setFont(self.font, 13)
        self.c.drawString(x_co, y_co - 10*mm, f"代表取締役   {self.params['ceo']}")
        self.c.setFont(self.font, 11)
        self.c.drawString(x_co, y_co - 20*mm, f"〒 {self.params['address']}")
        self.c.drawString(x_co, y_co - 26*mm, f"TEL: {self.params['phone']}")
        if self.params['fax']:
            self.c.drawString(x_co + 40*mm, y_co - 26*mm, f"FAX: {self.params['fax']}")
        
        self.c.showPage()

    def draw_summary(self):
        """概要ページ描画"""
        self._draw_centered_bold(self.width/2, self.height - 30*mm, "御   見   積   書", 32)
        self.c.setLineWidth(1); self.c.line(self.width/2 - 60*mm, self.height - 32*mm, self.width/2 + 60*mm, self.height - 32*mm)
        self.c.setLineWidth(0.5); self.c.line(self.width/2 - 60*mm, self.height - 33*mm, self.width/2 + 60*mm, self.height - 33*mm)
        
        self.c.setFont(self.font, 20)
        self.c.drawString(40*mm, self.height - 50*mm, f"{self.params['client_name']}  様")
        self.c.setFont(self.font, 12)
        self.c.drawString(40*mm, self.height - 60*mm, "下記のとおり御見積申し上げます")

        # Box
        box_top = self.height - 65*mm
        box_left = 30*mm
        box_width = self.width - 60*mm
        box_height = 120*mm
        box_btm = box_top - box_height
        
        self.c.setLineWidth(1.5); self.c.rect(box_left, box_btm, box_width, box_height)
        self.c.setLineWidth(0.5); self.c.rect(box_left+1.5*mm, box_btm+1.5*mm, box_width-3*mm, box_height-3*mm)

        # Content
        line_sx = box_left + 10*mm; label_end_x = line_sx + 28*mm; colon_x = label_end_x + 1*mm
        val_start_x = colon_x + 5*mm; line_ex = box_left + box_width - 10*mm
        curr_y = box_top - 15*mm; gap = 12*mm

        # Amount
        self.c.setFont(self.font, 14); self.c.drawRightString(label_end_x, curr_y, "見積金額")
        self._draw_bold_string(colon_x, curr_y, "：", 14)
        amt_s = f"¥ {int(self.total_grand):,}-"
        self._draw_bold_string(val_start_x, curr_y, amt_s, 18)
        
        tax_s = f"(別途消費税  ¥ {int(self.tax_amount):,})"
        self.c.setFont(self.font, 12)
        self.c.drawString(val_start_x + self.c.stringWidth(amt_s, self.font, 18) + 5*mm, curr_y, tax_s)
        self.c.setLineWidth(0.5)
        self.c.line(line_sx, curr_y-2*mm, line_ex, curr_y-2*mm)
        curr_y -= gap * 1.5

        # Items
        items = [("工 事 名", self.params['project_name']), ("工事場所", self.params['location']),
                 ("工   期", self.params['term']), ("そ の 他", "別紙内訳書による"), ("見積有効期限", self.params['expiry'])]
        
        for label, val in items:
            self.c.setFont(self.font, 12); self.c.drawRightString(label_end_x, curr_y, label)
            self.c.drawString(colon_x, curr_y, "：")
            self.c.setFont(self.font, 13); self.c.drawString(val_start_x, curr_y, val)
            self.c.line(line_sx, curr_y-2*mm, line_ex, curr_y-2*mm)
            curr_y -= gap

        # Footer Company Info
        x_co = box_left + box_width - 90*mm
        y_co = box_btm + 10*mm
        self.c.setFont(self.font, 13); self.c.drawString(x_co, y_co + 15*mm, self.params['company_name'])
        self.c.setFont(self.font, 11); self.c.drawString(x_co, y_co + 10*mm, f"代表取締役   {self.params['ceo']}")
        self.c.setFont(self.font, 10); self.c.drawString(x_co, y_co + 5*mm, f"〒 {self.params['address']}")
        self.c.drawString(x_co, y_co, f"TEL {self.params['phone']}  FAX {self.params['fax']}")

        wareki = to_wareki(self.params['date'])
        self.c.setFont(self.font, 12)
        self.c.drawString(self.width - 80*mm, box_top + 5*mm, wareki)
        self.c.showPage()

    def draw_total_summary(self, p_num):
        """総括表描画"""
        self._draw_page_header(p_num, "見 積 総 括 表")
        self._draw_grid(self.y_start, Style.MARGIN_BOTTOM - Style.ROW_HEIGHT)
        y = self.y_start
        
        # Data aggregation
        l1_summary = self.df.groupby('大項目', sort=False)['見積金額'].apply(lambda x: x.apply(parse_amount).sum()).reset_index()

        for _, row in l1_summary.iterrows():
            l1_name = row['大項目']
            amount = row['見積金額']
            if not l1_name: continue
            
            self._draw_bold_string(self.col_x['name'] + Style.INDENT_L1, y-5*mm, f"■ {l1_name}", 10, Style.COLOR_L1)
            self.c.setFont(self.font, 10)
            self.c.setFillColor(Style.COLOR_L1)
            self.c.drawRightString(self.col_x['amt'] + self.col_widths['amt'] - 2*mm, y-5*mm, f"{int(amount):,}")
            y -= Style.ROW_HEIGHT
        
        # Total Footer
        footer_rows = 3
        footer_start_y = Style.MARGIN_BOTTOM + (footer_rows * Style.ROW_HEIGHT)
        y = footer_start_y
        labels = [("小計", self.total_grand), ("消費税", self.tax_amount), ("総合計", self.final_total)]
        
        for lbl, val in labels:
            self.c.setFillColor(colors.black)
            self._draw_bold_string(self.col_x['name'] + 20*mm, y-5*mm, f"【 {lbl} 】", 11, Style.COLOR_TOTAL)
            self.c.setFont(self.font, 11)
            self.c.setFillColor(Style.COLOR_TOTAL)
            self.c.drawRightString(self.col_x['amt'] + self.col_widths['amt'] - 2*mm, y-5*mm, f"{int(val):,}")
            y -= Style.ROW_HEIGHT
            
        self.c.showPage()
        return p_num + 1

    def draw_breakdown_pages(self, p_num):
        """内訳書（集計）描画"""
        # Logic to aggregate L2 by L1 preserving order
        raw_rows = self.df.to_dict('records')
        breakdown = {}
        seen_l1 = []
        seen_l2_by_l1 = {}

        for row in raw_rows:
            l1 = str(row.get('大項目', '')).strip()
            l2 = str(row.get('中項目', '')).strip()
            amt = parse_amount(row.get('見積金額', 0))
            if not l1: continue
            
            if l1 not in seen_l1:
                seen_l1.append(l1)
                seen_l2_by_l1[l1] = []
            if l2 and l2 not in seen_l2_by_l1[l1]:
                seen_l2_by_l1[l1].append(l2)

            if l1 not in breakdown: breakdown[l1] = {'items': {}, 'total': 0}
            if l2:
                if l2 not in breakdown[l1]['items']: breakdown[l1]['items'][l2] = 0
                breakdown[l1]['items'][l2] += amt
            breakdown[l1]['total'] += amt

        self._draw_page_header(p_num, "内 訳 明 細 書 (集計)")
        self._draw_grid(self.y_start, Style.MARGIN_BOTTOM - Style.ROW_HEIGHT)
        y = self.y_start
        is_first = True
        
        for l1 in seen_l1:
            data = breakdown[l1]
            sorted_l2 = seen_l2_by_l1[l1]
            
            spacer = 1 if not is_first else 0
            rows_needed = spacer + 1 + len(sorted_l2) + 1
            rows_left = int((y - Style.MARGIN_BOTTOM) / Style.ROW_HEIGHT)
            
            if rows_needed > rows_left:
                self.c.showPage()
                p_num += 1
                self._draw_page_header(p_num, "内 訳 明 細 書 (集計)")
                self._draw_grid(self.y_start, Style.MARGIN_BOTTOM - Style.ROW_HEIGHT)
                y = self.y_start
                is_first = True
                spacer = 0

            if spacer: y -= Style.ROW_HEIGHT
            
            self._draw_bold_string(self.col_x['name'] + Style.INDENT_L1, y-5*mm, f"■ {l1}", 10, Style.COLOR_L1)
            y -= Style.ROW_HEIGHT
            
            for l2 in sorted_l2:
                amt = data['items'][l2]
                self._draw_bold_string(self.col_x['name'] + Style.INDENT_L2, y-5*mm, f"● {l2}", 10, Style.COLOR_L2)
                self.c.setFont(self.font, 10); self.c.setFillColor(Style.COLOR_L2)
                self.c.drawRightString(self.col_x['amt'] + self.col_widths['amt'] - 2*mm, y-5*mm, f"{int(amt):,}")
                y -= Style.ROW_HEIGHT
            
            self._draw_bold_string(self.col_x['name'] + Style.INDENT_L1, y-5*mm, f"【{l1} 計】", 10, Style.COLOR_L1)
            self.c.setFont(self.font, 10); self.c.setFillColor(Style.COLOR_L1)
            self.c.drawRightString(self.col_x['amt'] + self.col_widths['amt'] - 2*mm, y-5*mm, f"{int(data['total']):,}")
            y -= Style.ROW_HEIGHT
            is_first = False

        self.c.showPage()
        return p_num + 1

    def draw_detail_pages(self, p_num):
        """明細書（詳細）描画"""
        # Complex tree structure logic preserved for exact layout
        data_tree = {}
        seen_l1 = []
        seen_l2_by_l1 = {}

        for row in self.df.to_dict('records'):
            l1 = str(row.get('大項目', '')).strip(); l2 = str(row.get('中項目', '')).strip()
            l3 = str(row.get('小項目', '')).strip(); l4 = str(row.get('部分項目', '')).strip()
            if not l1: continue
            
            if l1 not in seen_l1:
                seen_l1.append(l1); seen_l2_by_l1[l1] = []
            if l2 and l2 not in seen_l2_by_l1[l1]: seen_l2_by_l1[l1].append(l2)

            if l1 not in data_tree: data_tree[l1] = {}
            if l2 not in data_tree[l1]: data_tree[l1][l2] = []
            
            item = row.copy()
            item.update({
                'amt_val': parse_amount(row.get('見積金額', 0)),
                'qty_val': parse_amount(row.get('数量', 0)),
                'price_val': parse_amount(row.get('売単価', 0)),
                'l3': l3, 'l4': l4
            })
            if item.get('名称'): data_tree[l1][l2].append(item)

        self._draw_page_header(p_num, "内 訳 明 細 書 (詳細)")
        self._draw_grid(self.y_start, Style.MARGIN_BOTTOM - Style.ROW_HEIGHT)
        y = self.y_start
        is_first = True

        for l1 in seen_l1:
            l2_dict = data_tree[l1]
            l1_total = sum([sum([i['amt_val'] for i in items]) for items in l2_dict.values()])
            sorted_l2 = seen_l2_by_l1[l1]

            # L1 Header Page Break Logic
            if not is_first:
                if y <= Style.MARGIN_BOTTOM + Style.ROW_HEIGHT * 2:
                    self.c.showPage(); p_num += 1
                    self._draw_page_header(p_num, "内 訳 明 細 書 (詳細)")
                    self._draw_grid(self.y_start, Style.MARGIN_BOTTOM - Style.ROW_HEIGHT)
                    y = self.y_start
                else:
                    y -= Style.ROW_HEIGHT

            if y <= Style.MARGIN_BOTTOM + Style.ROW_HEIGHT:
                self.c.showPage(); p_num += 1
                self._draw_page_header(p_num, "内 訳 明 細 書 (詳細)")
                self._draw_grid(self.y_start, Style.MARGIN_BOTTOM - Style.ROW_HEIGHT)
                y = self.y_start
            
            self._draw_bold_string(self.col_x['name']+Style.INDENT_L1, y-5*mm, f"■ {l1}", 10, Style.COLOR_L1)
            y -= Style.ROW_HEIGHT
            is_first = False
            
            # L2 Items
            for i_l2, l2 in enumerate(sorted_l2):
                items = l2_dict[l2]
                l2_total = sum([i['amt_val'] for i in items])
                
                # Build rows for this block
                rows_to_draw = []
                rows_to_draw.append({'type': 'header_l2', 'label': f"● {l2}"})
                
                curr_l3 = ""; curr_l4 = ""; sub_l3 = 0; sub_l4 = 0
                item_rows = []
                
                for itm in items:
                    l3 = itm['l3']; l4 = itm['l4']; amt = itm['amt_val']
                    l3_chg = (l3 and l3 != curr_l3); l4_chg = (l4 and l4 != curr_l4)
                    
                    if curr_l4 and (l4_chg or l3_chg):
                        item_rows.append({'type': 'footer_l4', 'label': f"【{curr_l4}】 小計", 'amt': sub_l4})
                        if l4 or l3_chg: item_rows.append({'type': 'empty'})
                        curr_l4 = ""; sub_l4 = 0
                    if curr_l3 and l3_chg:
                        item_rows.append({'type': 'footer_l3', 'label': f"【{curr_l3} 小計】", 'amt': sub_l3})
                        if l3: item_rows.append({'type': 'empty'})
                        curr_l3 = ""; sub_l3 = 0
                    
                    if l3_chg: item_rows.append({'type': 'header_l3', 'label': f"・ {l3}"}); curr_l3 = l3
                    if l4_chg: item_rows.append({'type': 'header_l4', 'label': f"【{l4}】"}); curr_l4 = l4
                    
                    sub_l3 += amt; sub_l4 += amt
                    item_rows.append({'type': 'item', 'data': itm})
                
                if curr_l4: item_rows.append({'type': 'footer_l4', 'label': f"【{curr_l4}】 小計", 'amt': sub_l4})
                if curr_l3: item_rows.append({'type': 'footer_l3', 'label': f"【{curr_l3} 小計】", 'amt': sub_l3})
                
                rows_to_draw.extend(item_rows)
                rows_to_draw.append({'type': 'footer_l2', 'label': f"【{l2} 計】", 'amt': l2_total})
                
                is_last_l2 = (i_l2 == len(sorted_l2) - 1)
                if is_last_l2:
                     rows_to_draw.append({'type': 'footer_l1', 'label': f"【{l1} 計】", 'amt': l1_total})
                else:
                    rows_to_draw.extend([{'type': 'empty'}, {'type': 'empty'}])
                
                while rows_to_draw and rows_to_draw[-1]['type'] == 'empty': rows_to_draw.pop()

                # State tracking for "Continued" headers
                l2_started = False
                cur_l3_lbl = None
                cur_l4_lbl = None

                for b in rows_to_draw:
                    itype = b['type']
                    force_stay = (itype == 'footer_l1')
                    
                    # Page break check
                    if y - Style.ROW_HEIGHT < Style.MARGIN_BOTTOM - 0.1 and not force_stay:
                        self.c.showPage(); p_num += 1
                        self._draw_page_header(p_num, "内 訳 明 細 書 (詳細)")
                        self._draw_grid(self.y_start, Style.MARGIN_BOTTOM - Style.ROW_HEIGHT)
                        y = self.y_start
                        
                        # Re-draw headers for continuity
                        self._draw_bold_string(self.col_x['name']+Style.INDENT_L1, y-5*mm, f"■ {l1} (続き)", 10, Style.COLOR_L1)
                        y -= Style.ROW_HEIGHT
                        if l2_started and itype != 'footer_l1':
                            self._draw_bold_string(self.col_x['name']+Style.INDENT_L2, y-5*mm, f"● {l2} (続き)", 10, Style.COLOR_L2)
                            y -= Style.ROW_HEIGHT
                        if cur_l3_lbl:
                            self._draw_bold_string(self.col_x['name']+Style.INDENT_L3, y-5*mm, f"{cur_l3_lbl} (続き)", 10, Style.COLOR_L3)
                            y -= Style.ROW_HEIGHT
                        if cur_l4_lbl:
                            self._draw_bold_string(self.col_x['name']+Style.INDENT_ITEM, y-5*mm, f"{cur_l4_lbl} (続き)", 9, colors.black)
                            y -= Style.ROW_HEIGHT

                    # Orphan control for footers
                    if itype in ['footer_l2', 'footer_l1']:
                        req_rows = 1 if itype == 'footer_l2' and is_last_l2 else 0
                        target_y = Style.MARGIN_BOTTOM + (req_rows * Style.ROW_HEIGHT)
                        if y > target_y + 0.1:
                            while y > target_y + 0.1: y -= Style.ROW_HEIGHT

                    # Drawing logic
                    if itype == 'header_l2':
                        self._draw_bold_string(self.col_x['name']+Style.INDENT_L2, y-5*mm, b['label'], 10, Style.COLOR_L2)
                        l2_started = True
                    elif itype == 'header_l3':
                        self._draw_bold_string(self.col_x['name']+Style.INDENT_L3, y-5*mm, b['label'], 10, Style.COLOR_L3)
                        cur_l3_lbl = b['label']
                    elif itype == 'header_l4':
                        self._draw_bold_string(self.col_x['name']+Style.INDENT_ITEM, y-5*mm, b['label'], 9, colors.black)
                        cur_l4_lbl = b['label']
                    elif itype == 'item':
                        d = b['data']; self.c.setFont(self.font, 9); self.c.setFillColor(colors.black)
                        self.c.drawString(self.col_x['name']+Style.INDENT_ITEM, y-5*mm, d.get('名称',''))
                        self.c.setFont(self.font, 8); self.c.drawString(self.col_x['spec']+1*mm, y-5*mm, d.get('規格',''))
                        self.c.setFont(self.font, 9)
                        if d['qty_val']: self.c.drawRightString(self.col_x['qty']+self.col_widths['qty']-2*mm, y-5*mm, f"{d['qty_val']:,.2f}")
                        self.c.drawCentredString(self.col_x['unit']+self.col_widths['unit']/2, y-5*mm, d.get('単位',''))
                        if d['price_val']: self.c.drawRightString(self.col_x['price']+self.col_widths['price']-2*mm, y-5*mm, f"{int(d['price_val']):,}")
                        if d['amt_val']: self.c.drawRightString(self.col_x['amt']+self.col_widths['amt']-2*mm, y-5*mm, f"{int(d['amt_val']):,}")
                        self.c.setFont(self.font, 8); self.c.drawString(self.col_x['rem']+1*mm, y-5*mm, d.get('備考',''))
                    elif itype == 'footer_l4':
                        self._draw_bold_string(self.col_x['name']+Style.INDENT_ITEM, y-5*mm, b['label'], 9, colors.black)
                        self.c.setFont(self.font, 9); self.c.drawRightString(self.col_x['amt']+self.col_widths['amt']-2*mm, y-5*mm, f"{int(b['amt']):,}")
                        cur_l4_lbl = None
                    elif itype == 'footer_l3':
                        self._draw_bold_string(self.col_x['name']+Style.INDENT_L3, y-5*mm, b['label'], 9, Style.COLOR_L3)
                        self.c.setFont(self.font, 9); self.c.setFillColor(Style.COLOR_L3)
                        self.c.drawRightString(self.col_x['amt']+self.col_widths['amt']-2*mm, y-5*mm, f"{int(b['amt']):,}")
                        cur_l3_lbl = None
                    elif itype == 'footer_l2':
                        self._draw_bold_string(self.col_x['name']+Style.INDENT_L2, y-5*mm, b['label'], 10, Style.COLOR_L2)
                        self.c.setFont(self.font, 10); self.c.setFillColor(Style.COLOR_L2)
                        self.c.drawRightString(self.col_x['amt']+self.col_widths['amt']-2*mm, y-5*mm, f"{int(b['amt']):,}")
                        self.c.setLineWidth(1); self.c.setStrokeColor(Style.COLOR_L2); self.c.line(Style.X_BASE, y, self.right_edge, y)
                    elif itype == 'footer_l1':
                        self._draw_bold_string(self.col_x['name']+Style.INDENT_L1, y-5*mm, b['label'], 10, Style.COLOR_L1)
                        self.c.setFont(self.font, 10); self.c.setFillColor(Style.COLOR_L1)
                        self.c.drawRightString(self.col_x['amt']+self.col_widths['amt']-2*mm, y-5*mm, f"{int(b['amt']):,}")
                        self.c.setLineWidth(1); self.c.setStrokeColor(Style.COLOR_L1); self.c.line(Style.X_BASE, y, self.right_edge, y)
                    
                    y -= Style.ROW_HEIGHT

        return p_num

    def generate(self) -> io.BytesIO:
        """PDF生成実行"""
        self.draw_cover()
        self.draw_summary()
        next_p = self.draw_total_summary(1)
        next_p = self.draw_breakdown_pages(next_p)
        self.draw_detail_pages(next_p)
        
        self.c.save()
        self.buffer.seek(0)
        return self.buffer

# ---------------------------------------------------------
# 4. Main Application UI
# ---------------------------------------------------------
def main():
    st.set_page_config(layout="wide", page_title="自動見積書作成システム")
    st.title("📄 自動見積書作成システム")

    # Session State Init
    if 'pdf_ready' not in st.session_state: st.session_state.pdf_ready = False
    if 'pdf_data' not in st.session_state: st.session_state.pdf_data = None
    if 'filename' not in st.session_state: st.session_state.filename = ""
    if 'sheet_url' not in st.session_state: st.session_state.sheet_url = ""

    # Sidebar for URL Input
    if not st.session_state.pdf_ready:
        with st.sidebar:
            st.header("🔑 設定")
            if not st.session_state.sheet_url:
                input_url = st.text_input(
                    "スプレッドシートURL", 
                    placeholder="https://docs.google.com/spreadsheets/d/...",
                    help="GoogleスプレッドシートのURLを貼り付けてください"
                )
            else:
                st.success("✓ URL設定済み")
                input_url = st.session_state.sheet_url
                if st.button("URLを変更する"):
                    st.session_state.sheet_url = ""
                    st.rerun()
        
        # Main Action Button
        if st.button("作成開始", type="primary"):
            if not input_url:
                st.error("URLを入力してください。")
            else:
                st.session_state.sheet_url = input_url
                
                with st.spinner('データを読み込み中...'):
                    # Secrets management
                    try:
                        secrets = dict(st.secrets["gcp_service_account"])
                    except FileNotFoundError:
                        st.error("Secretsが見つかりません。.streamlit/secrets.tomlを確認してください。")
                        return

                    df, info_dict = get_all_data_from_url(input_url, secrets)
                    
                    if df is not None and info_dict is not None:
                        # Extract params
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
                        
                        # Generate PDF using the Class
                        generator = EstimatePDFGenerator(df, params)
                        pdf_bytes = generator.generate()
                        
                        # Prepare download
                        date_val = params['date'].translate(str.maketrans({'/':'', '-':'', '年':'', '月':'', '日':''}))
                        spec = info_dict.get('見積もり仕様', '見積')
                        filename = f"{date_val}_{params['client_name']}_{params['project_name']}_{spec}.pdf"
                        
                        st.session_state.pdf_data = pdf_bytes
                        st.session_state.filename = filename
                        st.session_state.pdf_ready = True
                        st.rerun()

    else:
        # Success Screen
        st.success("✅ PDF生成完了")
        
        # Retrieve data from session
        pdf_raw_data = st.session_state.pdf_data.getvalue()
        
        st.info(f"📄 ファイル名: {st.session_state.filename}")
        
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            st.download_button(
                label="📥 PDFを保存する", 
                data=pdf_raw_data, 
                file_name=st.session_state.filename, 
                mime="application/pdf",
                use_container_width=True
            )
            
            if st.button("🔄 新しい見積書を作成する", use_container_width=True):
                st.session_state.pdf_ready = False
                st.session_state.pdf_data = None
                st.rerun()

if __name__ == "__main__":
    main()
