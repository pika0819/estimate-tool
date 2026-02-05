import io
import pandas as pd
from typing import Dict, Any
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib import colors
from data_utils import parse_amount

# --- Configuration ---
FONT_FILE = "NotoSerifJP-Regular.ttf"
FONT_NAME = "NotoSerifJP"
FONT_NAME_FALLBACK = "Helvetica"

class Style:
    COLOR_L1 = colors.HexColor('#0D5940')
    COLOR_L2 = colors.HexColor('#1A2673')
    COLOR_L3 = colors.HexColor('#994D1A')
    COLOR_TEXT = colors.HexColor('#000000')
    COLOR_TOTAL = colors.HexColor('#B31A26')
    COLOR_ACCENT_BLUE = colors.HexColor('#26408C')
    
    MARGIN_TOP = 35 * mm
    MARGIN_BOTTOM = 21 * mm
    ROW_HEIGHT = 7 * mm
    HEADER_HEIGHT = 9 * mm
    X_BASE = 15 * mm
    
    INDENT_L1 = 1.0 * mm
    INDENT_L2 = 4.0 * mm
    INDENT_L3 = 7.0 * mm
    INDENT_ITEM = 10.0 * mm

def to_wareki(date_str: str) -> str:
    try:
        if '年' in str(date_str): return str(date_str)
        dt_obj = pd.to_datetime(date_str)
        y, m, d = dt_obj.year, dt_obj.month, dt_obj.day
        if y >= 2019:
            r_y = y - 2018
            era = "令和"
            year_str = f"{r_y}年" if r_y != 1 else "元年"
        else:
            return dt_obj.strftime("%Y年 %m月 %d日")
        return f"{era} {year_str} {m}月 {d}日"
    except Exception:
        return str(date_str)

class EstimatePDFGenerator:
    def __init__(self, df: pd.DataFrame, params: Dict[str, str]):
        self.buffer = io.BytesIO()
        self.c = canvas.Canvas(self.buffer, pagesize=landscape(A4))
        self.width, self.height = landscape(A4)
        self.df = df
        self.params = params
        
        try:
            pdfmetrics.registerFont(TTFont(FONT_NAME, FONT_FILE))
            self.font = FONT_NAME
        except:
            self.font = FONT_NAME_FALLBACK

        self.content_width = self.width - 30 * mm
        self._setup_columns()
        self.total_estimated = df['見積金額'].apply(parse_amount).sum()
        self.tax_amount = int(self.total_estimated * 0.1)
        self.final_total = self.total_estimated + self.tax_amount
        
        self.y_start = self.height - Style.MARGIN_TOP
        self.current_y = self.y_start
        self.current_page = 1

    def _setup_columns(self):
        widths = {'name': 75*mm, 'spec': 67.5*mm, 'qty': 19*mm, 'unit': 12*mm, 'price': 27*mm, 'amt': 29*mm, 'rem': 0*mm}
        widths['rem'] = self.content_width - sum(widths.values())
        self.col_x = {}
        curr_x = Style.X_BASE
        for k, w in widths.items():
            self.col_x[k] = curr_x
            curr_x += w
        self.col_widths = widths
        self.right_edge = curr_x

    # --- Low-Level Drawing Helpers (座標管理・描画のみ) ---
    def _check_space(self, rows_needed: int, page_title: str):
        if self.current_y - (rows_needed * Style.ROW_HEIGHT) < Style.MARGIN_BOTTOM:
            self.c.showPage()
            self.current_page += 1
            self._draw_page_header(self.current_page, page_title)
            self._draw_grid_frame()
            self.current_y = self.y_start
            return True
        return False

    def _draw_text_row(self, x_offset, text, size=9, color=colors.black, bold=False):
        """汎用テキスト描画"""
        if bold:
            self._draw_bold_string(self.col_x['name'] + x_offset, self.current_y - 5*mm, text, size, color)
        else:
            self.c.setFont(self.font, size)
            self.c.setFillColor(color)
            self.c.drawString(self.col_x['name'] + x_offset, self.current_y - 5*mm, str(text))

    def _draw_amount_row(self, amount, size=9, color=colors.black):
        """金額右寄せ描画"""
        self.c.setFont(self.font, size)
        self.c.setFillColor(color)
        self.c.drawRightString(self.col_x['amt'] + self.col_widths['amt'] - 2*mm, self.current_y - 5*mm, f"{int(amount):,}")

    def _draw_line(self, color=colors.grey, width=0.5):
        """横線描画"""
        self.c.setLineWidth(width)
        self.c.setStrokeColor(color)
        self.c.line(Style.X_BASE, self.current_y - Style.ROW_HEIGHT, self.right_edge, self.current_y - Style.ROW_HEIGHT)

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
        self.c.setStrokeColor(colors.grey)
        for k in self.col_x:
            self.c.line(self.col_x[k], grid_y + Style.HEADER_HEIGHT, self.col_x[k], grid_y)
        self.c.line(self.right_edge, grid_y + Style.HEADER_HEIGHT, self.right_edge, grid_y)

    def _draw_grid_frame(self):
        y_bottom = Style.MARGIN_BOTTOM
        self.c.saveState()
        self.c.setLineWidth(0.5)
        self.c.setStrokeColor(colors.grey)
        for k in self.col_x:
            self.c.line(self.col_x[k], self.y_start, self.col_x[k], y_bottom)
        self.c.line(self.right_edge, self.y_start, self.right_edge, y_bottom)
        self.c.setStrokeColor(colors.black)
        self.c.line(Style.X_BASE, y_bottom, self.right_edge, y_bottom)
        self.c.restoreState()

    def _draw_total_block(self, page_title):
        self._check_space(4, page_title)
        y = self.current_y
        labels = [("見積総額 (税抜)", self.total_estimated), ("消費税 (10%)", self.tax_amount), ("総合計 (税込)", self.final_total)]
        for lbl, val in labels:
            self._draw_bold_string(self.col_x['name'] + 20*mm, y-5*mm, f"【 {lbl} 】", 11, Style.COLOR_TOTAL)
            self.c.setFont(self.font, 11)
            self.c.setFillColor(Style.COLOR_TOTAL)
            self.c.drawRightString(self.col_x['amt'] + self.col_widths['amt'] - 2*mm, y-5*mm, f"{int(val):,}")
            y -= Style.ROW_HEIGHT
        self.current_y = y

    # --- Page Content Generators ---
    def draw_cover(self):
        # 表紙
        title_text = "御    見    積    書"
        lw = 180*mm
        lx = (self.width - lw)/2
        ly = self.height - 57*mm 
        self.c.saveState()
        self.c.setFillAlpha(0.2); self.c.setStrokeColor(colors.HexColor('#c2c9de')); self.c.setLineWidth(14)
        self.c.line(lx, ly, lx+lw, ly)
        self.c.restoreState()
        self.c.saveState()
        t = self.c.beginText(); t.setFont(self.font, 45); t.setFillColor(Style.COLOR_ACCENT_BLUE); t.setCharSpace(10)
        tw = self.c.stringWidth(title_text, self.font, 45) + (len(title_text)-1) * 10
        t.setTextOrigin(self.width/2 - tw/2, self.height - 55*mm); t.textOut(title_text); self.c.drawText(t)
        self.c.restoreState()
        self._draw_centered_bold(self.width/2, self.height - 110*mm, f"{self.params['client_name']}", 32)
        self.c.setLineWidth(1); self.c.line(self.width/2 - 60*mm, self.height - 112*mm, self.width/2 + 60*mm, self.height - 112*mm)
        self._draw_centered_bold(self.width/2, self.height - 140*mm, f"{self.params['project_name']}", 24)
        self.c.setLineWidth(0.5); self.c.line(self.width/2 - 50*mm, self.height - 142*mm, self.width/2 + 50*mm, self.height - 142*mm)
        self.c.setFont(self.font, 14); self.c.drawString(40*mm, 50*mm, to_wareki(self.params['date']))
        x_co = self.width - 100*mm; y_co = 50*mm
        self._draw_bold_string(x_co, y_co, self.params['company_name'], 18)
        self.c.setFont(self.font, 13); self.c.drawString(x_co, y_co - 10*mm, f"代表取締役   {self.params['ceo']}")
        self.c.setFont(self.font, 11); self.c.drawString(x_co, y_co - 20*mm, f"〒 {self.params['address']}")
        self.c.drawString(x_co, y_co - 26*mm, f"TEL: {self.params['phone']}")
        if self.params['fax']: self.c.drawString(x_co + 40*mm, y_co - 26*mm, f"FAX: {self.params['fax']}")
        self.c.showPage()

    def draw_summary(self):
        # 鑑
        self._draw_centered_bold(self.width/2, self.height - 30*mm, "御    見    積    書", 32)
        self.c.setLineWidth(1); self.c.line(self.width/2 - 60*mm, self.height - 32*mm, self.width/2 + 60*mm, self.height - 32*mm)
        self.c.setLineWidth(0.5); self.c.line(self.width/2 - 60*mm, self.height - 33*mm, self.width/2 + 60*mm, self.height - 33*mm)
        self.c.setFont(self.font, 20); self.c.drawString(40*mm, self.height - 50*mm, f"{self.params['client_name']}  様")
        self.c.setFont(self.font, 12); self.c.drawString(40*mm, self.height - 60*mm, "下記のとおり御見積申し上げます")
        box_top = self.height - 65*mm; box_left = 30*mm; box_width = self.width - 60*mm; box_height = 120*mm; box_btm = box_top - box_height
        self.c.setLineWidth(1.5); self.c.rect(box_left, box_btm, box_width, box_height)
        self.c.setLineWidth(0.5); self.c.rect(box_left+1.5*mm, box_btm+1.5*mm, box_width-3*mm, box_height-3*mm)
        line_sx = box_left + 10*mm; label_end_x = line_sx + 28*mm; colon_x = label_end_x + 1*mm
        val_start_x = colon_x + 5*mm; line_ex = box_left + box_width - 10*mm
        curr_y = box_top - 15*mm; gap = 12*mm
        self.c.setFont(self.font, 14); self.c.drawRightString(label_end_x, curr_y, "見積金額")
        self._draw_bold_string(colon_x, curr_y, "：", 14)
        amt_s = f"¥ {int(self.final_total):,}-"; self._draw_bold_string(val_start_x, curr_y, amt_s, 18)
        tax_s = f"(内 消費税  ¥ {int(self.tax_amount):,})"; self.c.setFont(self.font, 12)
        self.c.drawString(val_start_x + self.c.stringWidth(amt_s, self.font, 18) + 5*mm, curr_y, tax_s)
        self.c.setLineWidth(0.5); self.c.line(line_sx, curr_y-2*mm, line_ex, curr_y-2*mm)
        curr_y -= gap * 1.5
        items = [("工 事 名", self.params['project_name']), ("工事場所", self.params['location']),
                 ("工    期", self.params['term']), ("そ の 他", "別紙内訳書による"), ("見積有効期限", self.params['expiry'])]
        for label, val in items:
            self.c.setFont(self.font, 12); self.c.drawRightString(label_end_x, curr_y, label)
            self.c.drawString(colon_x, curr_y, "：")
            self.c.setFont(self.font, 13); self.c.drawString(val_start_x, curr_y, val)
            self.c.line(line_sx, curr_y-2*mm, line_ex, curr_y-2*mm)
            curr_y -= gap
        x_co = box_left + box_width - 90*mm; y_co = box_btm + 10*mm
        self.c.setFont(self.font, 13); self.c.drawString(x_co, y_co + 15*mm, self.params['company_name'])
        self.c.setFont(self.font, 11); self.c.drawString(x_co, y_co + 10*mm, f"代表取締役   {self.params['ceo']}")
        self.c.setFont(self.font, 10); self.c.drawString(x_co, y_co + 5*mm, f"〒 {self.params['address']}")
        self.c.drawString(x_co, y_co, f"TEL {self.params['phone']}  FAX {self.params['fax']}")
        self.c.setFont(self.font, 12); self.c.drawString(self.width - 80*mm, box_top + 5*mm, to_wareki(self.params['date']))
        self.c.showPage()
        self.current_page = 2

    def draw_grand_summary_table(self):
        # 総括表
        TITLE = "見 積 総 括 表"
        self.current_page += 1
        self._draw_page_header(self.current_page, TITLE)
        self.current_y = self.y_start
        
        l1_summary = self.df.groupby('大項目', sort=False)['見積金額'].apply(lambda x: x.apply(parse_amount).sum()).reset_index()
        for _, row in l1_summary.iterrows():
            l1 = row['大項目']
            if not l1: continue
            self._draw_text_row(Style.INDENT_L1, f"■ {l1}", 10, Style.COLOR_L1, bold=True)
            self._draw_amount_row(row['見積金額'], 10, Style.COLOR_L1)
            self._draw_line(colors.black)
            self.current_y -= Style.ROW_HEIGHT
        
        self._draw_total_block(TITLE)
        self._draw_grid_frame()
        self.c.showPage()

    def draw_breakdown_table(self):
        # 内訳集計
        TITLE = "内 訳 明 細 書 (集計)"
        self.current_page += 1
        self._draw_page_header(self.current_page, TITLE)
        self.current_y = self.y_start

        # 集計
        data_struct = {}
        for _, row in self.df.iterrows():
            l1, l2 = str(row['大項目']).strip(), str(row['中項目']).strip()
            if not l1: continue
            if l1 not in data_struct: data_struct[l1] = {}
            if l2 not in data_struct[l1]: data_struct[l1][l2] = 0
            data_struct[l1][l2] += parse_amount(row['見積金額'])

        for l1, l2_dict in data_struct.items():
            l1_total = sum(l2_dict.values())
            valid_l2 = [l2 for l2 in l2_dict if l2] # 空じゃない中項目
            
            # 改ページ判定
            rows_needed = 1 + len(valid_l2) + 1
            self._check_space(rows_needed, TITLE)
            
            # L1 Header
            self._draw_text_row(Style.INDENT_L1, f"■ {l1}", 10, Style.COLOR_L1, bold=True)
            self._draw_line(colors.grey)
            self.current_y -= Style.ROW_HEIGHT
            
            # L2 Rows
            for l2 in valid_l2:
                self._check_space(2, TITLE) # 念のため
                self._draw_text_row(Style.INDENT_L2, f"● {l2}", 10, Style.COLOR_L2, bold=True)
                self._draw_amount_row(l2_dict[l2], 10, Style.COLOR_L2)
                self._draw_line(colors.grey)
                self.current_y -= Style.ROW_HEIGHT
            
            # L1 Footer
            self._check_space(1, TITLE)
            self._draw_text_row(Style.INDENT_L1, f"【{l1} 計】", 10, Style.COLOR_L1, bold=True)
            self._draw_amount_row(l1_total, 10, Style.COLOR_L1)
            self._draw_line(Style.COLOR_L1, 1.0)
            self.current_y -= (Style.ROW_HEIGHT + 2*mm)

        self._draw_total_block(TITLE)
        self._draw_grid_frame()
        self.c.showPage()

    def draw_detail_pages(self):
        TITLE = "内 訳 明 細 書 (詳細)"
        self.current_page += 1
        self._draw_page_header(self.current_page, TITLE)
        self.current_y = self.y_start

        # データ構築
        data_tree = {}
        seen_l1 = []
        for row in self.df.to_dict('records'):
            l1 = str(row.get('大項目', '')).strip(); l2 = str(row.get('中項目', '')).strip()
            if not l1: continue
            if l1 not in seen_l1: seen_l1.append(l1); data_tree[l1] = {}
            if l2 not in data_tree[l1]: data_tree[l1][l2] = []
            
            item = row.copy()
            item.update({
                'amt_val': parse_amount(row.get('見積金額', 0)),
                'qty_val': parse_amount(row.get('数量', 0)),
                'price_val': parse_amount(row.get('売単価', 0)),
                'l3': str(row.get('小項目', '')).strip(), 
                'l4': str(row.get('部分項目', '')).strip()
            })
            if item.get('名称'): data_tree[l1][l2].append(item)

        total_drawn = False

        for l1 in seen_l1:
            # ★諸経費の場合の特別処理★
            if l1 == "諸経費":
                # 必ず改ページして新規ページへ
                self.c.showPage()
                self.current_page += 1
                self._draw_page_header(self.current_page, TITLE)
                self.current_y = self.y_start
                
                # Header
                self._draw_text_row(Style.INDENT_L1, f"■ {l1}", 10, Style.COLOR_L1, bold=True)
                self._draw_line(colors.grey)
                self.current_y -= Style.ROW_HEIGHT
                
                # Item (中項目なし前提)
                l1_total = 0
                for l2, items in data_tree[l1].items():
                    for item in items:
                        l1_total += item['amt_val']
                        # Item Row Draw
                        self.c.setFont(self.font, 9); self.c.setFillColor(colors.black)
                        self.c.drawString(self.col_x['name']+Style.INDENT_ITEM, self.current_y-5*mm, item.get('名称',''))
                        self.c.setFont(self.font, 8); self.c.drawString(self.col_x['spec']+1*mm, self.current_y-5*mm, item.get('規格',''))
                        self.c.setFont(self.font, 9)
                        if item['qty_val']: self.c.drawRightString(self.col_x['qty']+self.col_widths['qty']-2*mm, self.current_y-5*mm, f"{item['qty_val']:,.2f}")
                        self.c.drawCentredString(self.col_x['unit']+self.col_widths['unit']/2, self.current_y-5*mm, item.get('単位',''))
                        if item['price_val']: self.c.drawRightString(self.col_x['price']+self.col_widths['price']-2*mm, self.current_y-5*mm, f"{int(item['price_val']):,}")
                        if item['amt_val']: self.c.drawRightString(self.col_x['amt']+self.col_widths['amt']-2*mm, self.current_y-5*mm, f"{int(item['amt_val']):,}")
                        self._draw_line(colors.grey)
                        self.current_y -= Style.ROW_HEIGHT

                # 10行目へジャンプ (header下から10行分)
                target_sub_y = self.y_start - (10 * Style.ROW_HEIGHT)
                if self.current_y > target_sub_y: self.current_y = target_sub_y
                
                # 諸経費 小計
                self._draw_text_row(Style.INDENT_L1, f"【{l1} 計】", 10, Style.COLOR_L1, bold=True)
                self._draw_amount_row(l1_total, 10, Style.COLOR_L1)
                self._draw_line(Style.COLOR_L1, 1.0)
                self.current_y -= Style.ROW_HEIGHT

                # ページ下部へジャンプ (Footer 3行分確保)
                target_bottom_y = Style.MARGIN_BOTTOM + (3 * Style.ROW_HEIGHT)
                if self.current_y > target_bottom_y: self.current_y = target_bottom_y
                
                # Grand Total
                labels = [("見積総額 (税抜)", self.total_estimated), ("消費税 (10%)", self.tax_amount), ("総合計 (税込)", self.final_total)]
                for lbl, val in labels:
                    self._draw_text_row(20*mm, f"【 {lbl} 】", 11, Style.COLOR_TOTAL, bold=True)
                    self._draw_amount_row(val, 11, Style.COLOR_TOTAL)
                    self.current_y -= Style.ROW_HEIGHT
                
                total_drawn = True
                self._draw_grid_frame() # 枠線を引いてページ終了
                continue # 次のL1へ（あれば）

            # --- 通常のL1処理 ---
            self._check_space(2, TITLE)
            self._draw_text_row(Style.INDENT_L1, f"■ {l1}", 10, Style.COLOR_L1, bold=True)
            self._draw_line(colors.grey)
            self.current_y -= Style.ROW_HEIGHT
            
            l1_total = 0
            
            for l2, items in data_tree[l1].items():
                l2_total = sum(i['amt_val'] for i in items)
                l1_total += l2_total
                
                if l2:
                    self._check_space(2, TITLE)
                    self._draw_text_row(Style.INDENT_L2, f"● {l2}", 10, Style.COLOR_L2, bold=True)
                    self._draw_line(colors.grey)
                    self.current_y -= Style.ROW_HEIGHT
                
                current_l3, current_l4 = "", ""
                sub_l3, sub_l4 = 0, 0
                
                for item in items:
                    l3, l4, amt = item['l3'], item['l4'], item['amt_val']
                    
                    # Control Breaks
                    if current_l4 and (l4 != current_l4 or l3 != current_l3):
                        self._check_space(1, TITLE)
                        self._draw_text_row(Style.INDENT_ITEM, f"【{current_l4}】 小計", 9, colors.black, bold=True)
                        self._draw_amount_row(sub_l4, 9)
                        self._draw_line(colors.grey)
                        self.current_y -= Style.ROW_HEIGHT
                        sub_l4 = 0; current_l4 = ""
                    
                    if current_l3 and l3 != current_l3:
                        self._check_space(1, TITLE)
                        self._draw_text_row(Style.INDENT_L3, f"【{current_l3} 小計】", 9, Style.COLOR_L3, bold=True)
                        self._draw_amount_row(sub_l3, 9, Style.COLOR_L3)
                        self._draw_line(colors.grey)
                        self.current_y -= Style.ROW_HEIGHT
                        sub_l3 = 0; current_l3 = ""
                    
                    # Headers
                    if l3 and l3 != current_l3:
                        self._check_space(2, TITLE)
                        self._draw_text_row(Style.INDENT_L3, f"・ {l3}", 10, Style.COLOR_L3, bold=True)
                        self._draw_line(colors.grey)
                        self.current_y -= Style.ROW_HEIGHT
                        current_l3 = l3
                    
                    if l4 and l4 != current_l4:
                        self._check_space(2, TITLE)
                        self._draw_text_row(Style.INDENT_ITEM, f"【{l4}】", 9, colors.black, bold=True)
                        self._draw_line(colors.grey)
                        self.current_y -= Style.ROW_HEIGHT
                        current_l4 = l4
                    
                    # Draw Item
                    self._check_space(1, TITLE)
                    self.c.setFont(self.font, 9); self.c.setFillColor(colors.black)
                    self.c.drawString(self.col_x['name']+Style.INDENT_ITEM, self.current_y-5*mm, item.get('名称',''))
                    self.c.setFont(self.font, 8); self.c.drawString(self.col_x['spec']+1*mm, self.current_y-5*mm, item.get('規格',''))
                    self.c.setFont(self.font, 9)
                    if item['qty_val']: self.c.drawRightString(self.col_x['qty']+self.col_widths['qty']-2*mm, self.current_y-5*mm, f"{item['qty_val']:,.2f}")
                    self.c.drawCentredString(self.col_x['unit']+self.col_widths['unit']/2, self.current_y-5*mm, item.get('単位',''))
                    if item['price_val']: self.c.drawRightString(self.col_x['price']+self.col_widths['price']-2*mm, self.current_y-5*mm, f"{int(item['price_val']):,}")
                    if item['amt_val']: self.c.drawRightString(self.col_x['amt']+self.col_widths['amt']-2*mm, self.current_y-5*mm, f"{int(item['amt_val']):,}")
                    self.c.setFont(self.font, 8); self.c.drawString(self.col_x['rem']+1*mm, self.current_y-5*mm, item.get('備考',''))
                    self._draw_line(colors.grey)
                    self.current_y -= Style.ROW_HEIGHT
                    
                    sub_l3 += amt; sub_l4 += amt
                
                # Flush Footers
                if current_l4:
                    self._check_space(1, TITLE)
                    self._draw_text_row(Style.INDENT_ITEM, f"【{current_l4}】 小計", 9, colors.black, bold=True)
                    self._draw_amount_row(sub_l4, 9)
                    self._draw_line(colors.grey)
                    self.current_y -= Style.ROW_HEIGHT
                
                if current_l3:
                    self._check_space(1, TITLE)
                    self._draw_text_row(Style.INDENT_L3, f"【{current_l3} 小計】", 9, Style.COLOR_L3, bold=True)
                    self._draw_amount_row(sub_l3, 9, Style.COLOR_L3)
                    self._draw_line(colors.grey)
                    self.current_y -= Style.ROW_HEIGHT
                
                if l2:
                    self._check_space(1, TITLE)
                    self._draw_text_row(Style.INDENT_L2, f"【{l2} 計】", 10, Style.COLOR_L2, bold=True)
                    self._draw_amount_row(l2_total, 10, Style.COLOR_L2)
                    self._draw_line(Style.COLOR_L2, 1.0)
                    self.current_y -= Style.ROW_HEIGHT

            # L1 Footer
            self._check_space(1, TITLE)
            self._draw_text_row(Style.INDENT_L1, f"【{l1} 計】", 10, Style.COLOR_L1, bold=True)
            self._draw_amount_row(l1_total, 10, Style.COLOR_L1)
            self._draw_line(Style.COLOR_L1, 1.0)
            self.current_y -= (Style.ROW_HEIGHT + 2*mm)

        if not total_drawn:
            self._draw_total_block(TITLE)
        
        self._draw_grid_frame()
        self.c.showPage()

    def generate(self) -> io.BytesIO:
        self.draw_cover()
        self.draw_summary()
        self.draw_grand_summary_table()
        self.draw_breakdown_table()
        self.draw_detail_pages()
        self.c.save()
        self.buffer.seek(0)
        return self.buffer
