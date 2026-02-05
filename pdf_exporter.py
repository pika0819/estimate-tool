import io
import pandas as pd
from typing import Dict, Any, List
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib import colors
from data_utils import parse_amount

# ---------------------------------------------------------
# Configuration & Styles
# ---------------------------------------------------------
FONT_FILE = "NotoSerifJP-Regular.ttf"
FONT_NAME = "NotoSerifJP"
FONT_NAME_FALLBACK = "Helvetica"

class Style:
    COLOR_L1 = colors.HexColor('#0D5940')  # 大項目カラー
    COLOR_L2 = colors.HexColor('#1A2673')  # 中項目カラー
    COLOR_L3 = colors.HexColor('#994D1A')  # 小項目カラー
    COLOR_TEXT = colors.HexColor('#000000')
    COLOR_TOTAL = colors.HexColor('#B31A26') # 合計系カラー
    COLOR_ACCENT_BLUE = colors.HexColor('#26408C')
    
    # レイアウト定数
    MARGIN_TOP = 35 * mm
    MARGIN_BOTTOM = 25 * mm # 下部余白を少し広めに確保
    ROW_HEIGHT = 7 * mm
    HEADER_HEIGHT = 9 * mm
    X_BASE = 15 * mm
    
    # インデント設定
    INDENT_L1 = 1.0 * mm
    INDENT_L2 = 4.0 * mm
    INDENT_L3 = 7.0 * mm
    INDENT_ITEM = 10.0 * mm

def to_wareki(date_str: str) -> str:
    """西暦和暦変換"""
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

# ---------------------------------------------------------
# PDF Generator Logic
# ---------------------------------------------------------
class EstimatePDFGenerator:
    def __init__(self, df: pd.DataFrame, params: Dict[str, str]):
        self.buffer = io.BytesIO()
        self.c = canvas.Canvas(self.buffer, pagesize=landscape(A4))
        self.width, self.height = landscape(A4)
        self.df = df
        self.params = params
        
        # フォント設定
        try:
            pdfmetrics.registerFont(TTFont(FONT_NAME, FONT_FILE))
            self.font = FONT_NAME
        except:
            self.font = FONT_NAME_FALLBACK

        # 基本計算
        self.total_kouji = df['見積金額'].apply(parse_amount).sum() # 工事価格
        self.overhead_rate = 0.15 # 諸経費率 15%
        self.overhead_amount = int(self.total_kouji * self.overhead_rate)
        self.total_estimated = self.total_kouji + self.overhead_amount # 見積総額(税抜)
        self.tax_amount = int(self.total_estimated * 0.1) # 消費税
        self.final_total = self.total_estimated + self.tax_amount # 税込合計

        # レイアウト初期化
        self.content_width = self.width - 30 * mm
        self._setup_columns()
        self.y_start = self.height - Style.MARGIN_TOP
        self.current_y = self.y_start
        self.current_page = 1

    def _setup_columns(self):
        # 列幅定義
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

    # --- Drawing Helpers ---
    def _check_space(self, rows_needed: int, page_title: str):
        """
        指定した行数が現在のページに入るか確認し、入らなければ改ページする。
        """
        height_needed = rows_needed * Style.ROW_HEIGHT
        if self.current_y - height_needed < Style.MARGIN_BOTTOM:
            self.c.showPage()
            self.current_page += 1
            self._draw_page_header(self.current_page, page_title)
            self._draw_grid_frame() # 枠だけ描画（中身は後続処理で）
            self.current_y = self.y_start
            return True # 改ページした
        return False # 改ページしなかった

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
        
        # タイトル
        tw = self.c.stringWidth(title, self.font, 16)
        self.c.drawCentredString(self.width/2, hy, title)
        self.c.setLineWidth(0.5)
        self.c.line(self.width/2 - tw/2 - 5*mm, hy - 2*mm, self.width/2 + tw/2 + 5*mm, hy - 2*mm)
        
        # 会社名・ページ番号
        self.c.setFont(self.font, 10)
        self.c.drawRightString(self.right_edge, hy, self.params['company_name'])
        self.c.drawCentredString(self.width/2, 10*mm, f"- {p_num} -")
        
        # ヘッダー行の描画
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
        
        # 縦線（ヘッダー部分のみ）
        self.c.setLineWidth(0.5)
        self.c.setStrokeColor(colors.grey)
        for k in self.col_x:
            self.c.line(self.col_x[k], grid_y + Style.HEADER_HEIGHT, self.col_x[k], grid_y)
        self.c.line(self.right_edge, grid_y + Style.HEADER_HEIGHT, self.right_edge, grid_y)

    def _draw_grid_frame(self):
        """現在のページの下まで縦線を描画する（改ページ直後や最後に呼ぶ）"""
        # 注意: 厳密にはコンテンツを描画した後に呼ぶのが綺麗だが、
        # ここでは簡易的にページ下部まで線を引く
        y_bottom = Style.MARGIN_BOTTOM
        self.c.saveState()
        self.c.setLineWidth(0.5)
        self.c.setStrokeColor(colors.grey)
        for k in self.col_x:
            self.c.line(self.col_x[k], self.y_start, self.col_x[k], y_bottom)
        self.c.line(self.right_edge, self.y_start, self.right_edge, y_bottom)
        
        # 一番下の横線
        self.c.setStrokeColor(colors.black)
        self.c.line(Style.X_BASE, y_bottom, self.right_edge, y_bottom)
        self.c.restoreState()

    def _draw_total_block(self, page_title):
        """諸経費、消費税、合計のブロックを描画する（共通部品）"""
        # 必要な行数: 4行 (諸経費, 小計, 消費税, 総合計)
        self._check_space(5, page_title) 
        
        y = self.current_y
        
        # 1. 諸経費
        self._draw_bold_string(self.col_x['name'] + 20*mm, y-5*mm, "【 諸経費 (15%) 】", 10, colors.black)
        self.c.setFont(self.font, 10)
        self.c.drawRightString(self.col_x['amt'] + self.col_widths['amt'] - 2*mm, y-5*mm, f"{self.overhead_amount:,}")
        y -= Style.ROW_HEIGHT

        # 2. 見積総額 (税抜)
        self._draw_bold_string(self.col_x['name'] + 20*mm, y-5*mm, "【 見積総額 (税抜) 】", 11, Style.COLOR_TOTAL)
        self.c.setFont(self.font, 11)
        self.c.setFillColor(Style.COLOR_TOTAL)
        self.c.drawRightString(self.col_x['amt'] + self.col_widths['amt'] - 2*mm, y-5*mm, f"{self.total_estimated:,}")
        y -= Style.ROW_HEIGHT

        # 3. 消費税
        self._draw_bold_string(self.col_x['name'] + 20*mm, y-5*mm, "【 消 費 税 (10%) 】", 10, colors.black)
        self.c.setFont(self.font, 10)
        self.c.setFillColor(colors.black)
        self.c.drawRightString(self.col_x['amt'] + self.col_widths['amt'] - 2*mm, y-5*mm, f"{self.tax_amount:,}")
        y -= Style.ROW_HEIGHT

        # 4. 総合計
        self._draw_bold_string(self.col_x['name'] + 20*mm, y-5*mm, "【 総 合 計 (税込) 】", 12, Style.COLOR_TOTAL)
        self.c.setFont(self.font, 12)
        self.c.setFillColor(Style.COLOR_TOTAL)
        self.c.drawRightString(self.col_x['amt'] + self.col_widths['amt'] - 2*mm, y-5*mm, f"{self.final_total:,}")
        y -= Style.ROW_HEIGHT
        
        self.current_y = y

    # --- Main Content Methods ---

    def draw_cover(self):
        # 表紙 (変更なし)
        title_text = "御    見    積    書"
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
        self._draw_centered_bold(self.width/2, self.height - 110*mm, f"{self.params['client_name']}", 32)
        self.c.setLineWidth(1)
        self.c.line(self.width/2 - 60*mm, self.height - 112*mm, self.width/2 + 60*mm, self.height - 112*mm)
        self._draw_centered_bold(self.width/2, self.height - 140*mm, f"{self.params['project_name']}", 24)
        self.c.setLineWidth(0.5)
        self.c.line(self.width/2 - 50*mm, self.height - 142*mm, self.width/2 + 50*mm, self.height - 142*mm)
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
        # 鑑 (変更なし)
        self._draw_centered_bold(self.width/2, self.height - 30*mm, "御    見    積    書", 32)
        self.c.setLineWidth(1); self.c.line(self.width/2 - 60*mm, self.height - 32*mm, self.width/2 + 60*mm, self.height - 32*mm)
        self.c.setLineWidth(0.5); self.c.line(self.width/2 - 60*mm, self.height - 33*mm, self.width/2 + 60*mm, self.height - 33*mm)
        self.c.setFont(self.font, 20)
        self.c.drawString(40*mm, self.height - 50*mm, f"{self.params['client_name']}  様")
        self.c.setFont(self.font, 12)
        self.c.drawString(40*mm, self.height - 60*mm, "下記のとおり御見積申し上げます")
        box_top = self.height - 65*mm
        box_left = 30*mm
        box_width = self.width - 60*mm
        box_height = 120*mm
        box_btm = box_top - box_height
        self.c.setLineWidth(1.5); self.c.rect(box_left, box_btm, box_width, box_height)
        self.c.setLineWidth(0.5); self.c.rect(box_left+1.5*mm, box_btm+1.5*mm, box_width-3*mm, box_height-3*mm)
        line_sx = box_left + 10*mm; label_end_x = line_sx + 28*mm; colon_x = label_end_x + 1*mm
        val_start_x = colon_x + 5*mm; line_ex = box_left + box_width - 10*mm
        curr_y = box_top - 15*mm; gap = 12*mm
        self.c.setFont(self.font, 14); self.c.drawRightString(label_end_x, curr_y, "見積金額")
        self._draw_bold_string(colon_x, curr_y, "：", 14)
        amt_s = f"¥ {int(self.final_total):,}-" # ここは税込合計を表示
        self._draw_bold_string(val_start_x, curr_y, amt_s, 18)
        
        # 内訳表示
        tax_s = f"(内 消費税  ¥ {int(self.tax_amount):,})"
        self.c.setFont(self.font, 12)
        self.c.drawString(val_start_x + self.c.stringWidth(amt_s, self.font, 18) + 5*mm, curr_y, tax_s)
        
        self.c.setLineWidth(0.5)
        self.c.line(line_sx, curr_y-2*mm, line_ex, curr_y-2*mm)
        curr_y -= gap * 1.5
        items = [("工 事 名", self.params['project_name']), ("工事場所", self.params['location']),
                 ("工    期", self.params['term']), ("そ の 他", "別紙内訳書による"), ("見積有効期限", self.params['expiry'])]
        for label, val in items:
            self.c.setFont(self.font, 12); self.c.drawRightString(label_end_x, curr_y, label)
            self.c.drawString(colon_x, curr_y, "：")
            self.c.setFont(self.font, 13); self.c.drawString(val_start_x, curr_y, val)
            self.c.line(line_sx, curr_y-2*mm, line_ex, curr_y-2*mm)
            curr_y -= gap
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
        
        # ページ番号リセット(p3から開始するため)
        self.current_page = 2 

    def draw_grand_summary_table(self):
        # p3: 見積総括表 (改ページなし前提)
        self.current_page += 1
        TITLE = "見 積 総 括 表"
        self._draw_page_header(self.current_page, TITLE)
        self.current_y = self.y_start
        
        l1_summary = self.df.groupby('大項目', sort=False)['見積金額'].apply(lambda x: x.apply(parse_amount).sum()).reset_index()
        
        for _, row in l1_summary.iterrows():
            l1_name = row['大項目']
            amount = row['見積金額']
            if not l1_name: continue
            
            # 行描画
            self._draw_bold_string(self.col_x['name'] + Style.INDENT_L1, self.current_y-5*mm, f"■ {l1_name}", 10, Style.COLOR_L1)
            self.c.setFont(self.font, 10)
            self.c.setFillColor(Style.COLOR_L1)
            self.c.drawRightString(self.col_x['amt'] + self.col_widths['amt'] - 2*mm, self.current_y-5*mm, f"{int(amount):,}")
            self.c.setLineWidth(0.5); self.c.setStrokeColor(colors.black); self.c.line(Style.X_BASE, self.current_y-Style.ROW_HEIGHT, self.right_edge, self.current_y-Style.ROW_HEIGHT)
            
            self.current_y -= Style.ROW_HEIGHT

        # 諸経費・総計ブロック
        self._draw_total_block(TITLE)
        self._draw_grid_frame()
        self.c.showPage()

    def draw_breakdown_table(self):
        # p4-: 内訳集計表（L1 > L2 のリスト）
        TITLE = "内 訳 明 細 書 (集計)"
        self.current_page += 1
        self._draw_page_header(self.current_page, TITLE)
        self.current_y = self.y_start

        # データ構造化: L1 -> list of (L2, amt)
        data_struct = {}
        for idx, row in self.df.iterrows():
            l1 = str(row['大項目']).strip()
            l2 = str(row['中項目']).strip()
            if not l1: continue
            if l1 not in data_struct: data_struct[l1] = {}
            if l2 not in data_struct[l1]: data_struct[l1][l2] = 0
            data_struct[l1][l2] += parse_amount(row['見積金額'])

        # 描画ループ
        for l1, l2_dict in data_struct.items():
            l1_total = sum(l2_dict.values())
            rows_needed = 1 + len(l2_dict) + 1 # L1 Header + L2 items + L1 Footer
            
            # --- [改ページ判定] L1ブロックごと ---
            # 基本は分割しないが、1ページより長い場合は分割する
            if self._check_space(rows_needed, TITLE):
                # 改ページした場合
                pass
            
            # L1 Header
            self._draw_bold_string(self.col_x['name'] + Style.INDENT_L1, self.current_y-5*mm, f"■ {l1}", 10, Style.COLOR_L1)
            self.c.setLineWidth(0.5); self.c.setStrokeColor(colors.grey); self.c.line(Style.X_BASE, self.current_y-Style.ROW_HEIGHT, self.right_edge, self.current_y-Style.ROW_HEIGHT)
            self.current_y -= Style.ROW_HEIGHT
            
            # L2 Items (ここでの改ページは、L1が巨大な場合のみ発生する)
            for l2, amt in l2_dict.items():
                if self._check_space(2, TITLE): # 残りわずかなら改ページ
                    self._draw_bold_string(self.col_x['name'] + Style.INDENT_L1, self.current_y-5*mm, f"■ {l1} (続き)", 10, Style.COLOR_L1)
                    self.current_y -= Style.ROW_HEIGHT

                self._draw_bold_string(self.col_x['name'] + Style.INDENT_L2, self.current_y-5*mm, f"● {l2}", 10, Style.COLOR_L2)
                self.c.setFont(self.font, 10); self.c.setFillColor(Style.COLOR_L2)
                self.c.drawRightString(self.col_x['amt'] + self.col_widths['amt'] - 2*mm, self.current_y-5*mm, f"{int(amt):,}")
                self.c.setLineWidth(0.5); self.c.setStrokeColor(colors.grey); self.c.line(Style.X_BASE, self.current_y-Style.ROW_HEIGHT, self.right_edge, self.current_y-Style.ROW_HEIGHT)
                self.current_y -= Style.ROW_HEIGHT
            
            # L1 Footer
            if self._check_space(1, TITLE):
                pass
            self._draw_bold_string(self.col_x['name'] + Style.INDENT_L1, self.current_y-5*mm, f"【{l1} 計】", 10, Style.COLOR_L1)
            self.c.setFont(self.font, 10); self.c.setFillColor(Style.COLOR_L1)
            self.c.drawRightString(self.col_x['amt'] + self.col_widths['amt'] - 2*mm, self.current_y-5*mm, f"{int(l1_total):,}")
            self.c.setLineWidth(1.0); self.c.setStrokeColor(Style.COLOR_L1); self.c.line(Style.X_BASE, self.current_y-Style.ROW_HEIGHT, self.right_edge, self.current_y-Style.ROW_HEIGHT)
            self.current_y -= Style.ROW_HEIGHT
            
            # スペーサー
            self.current_y -= 2*mm

        # 最後に諸経費ブロック
        self._draw_total_block(TITLE)
        self._draw_grid_frame()
        self.c.showPage()

    def draw_detail_table(self):
        # 詳細ページ (詳細ロジック)
        TITLE = "内 訳 明 細 書 (詳細)"
        self.current_page += 1
        self._draw_page_header(self.current_page, TITLE)
        self.current_y = self.y_start

        # データ構造化: L1 > L2 > List of Items
        # (L3, L4はItemsの中で変化を検知してヘッダーを挿入する)
        tree = {}
        for row in self.df.to_dict('records'):
            l1 = str(row.get('大項目','')).strip()
            l2 = str(row.get('中項目','')).strip()
            if not l1: continue
            if l1 not in tree: tree[l1] = {}
            if l2 not in tree[l1]: tree[l1][l2] = []
            
            item = row.copy()
            item['amt_val'] = parse_amount(row.get('見積金額',0))
            item['qty_val'] = parse_amount(row.get('数量',0))
            item['price_val'] = parse_amount(row.get('売単価',0))
            item['l3'] = str(row.get('小項目','')).strip()
            item['l4'] = str(row.get('部分項目','')).strip()
            if item.get('名称'): tree[l1][l2].append(item)

        for l1, l2_dict in tree.items():
            # L1 Header
            if self._check_space(2, TITLE): pass
            self._draw_bold_string(self.col_x['name']+Style.INDENT_L1, self.current_y-5*mm, f"■ {l1}", 10, Style.COLOR_L1)
            self.c.setLineWidth(0.5); self.c.setStrokeColor(colors.grey); self.c.line(Style.X_BASE, self.current_y-Style.ROW_HEIGHT, self.right_edge, self.current_y-Style.ROW_HEIGHT)
            self.current_y -= Style.ROW_HEIGHT

            l1_total = 0

            for l2, items in l2_dict.items():
                l2_total = sum(i['amt_val'] for i in items)
                l1_total += l2_total
                
                # L2 Header
                if self._check_space(2, TITLE):
                     self._draw_bold_string(self.col_x['name']+Style.INDENT_L1, self.current_y-5*mm, f"■ {l1} (続き)", 10, Style.COLOR_L1)
                     self.current_y -= Style.ROW_HEIGHT

                self._draw_bold_string(self.col_x['name']+Style.INDENT_L2, self.current_y-5*mm, f"● {l2}", 10, Style.COLOR_L2)
                self.c.setLineWidth(0.5); self.c.setStrokeColor(colors.grey); self.c.line(Style.X_BASE, self.current_y-Style.ROW_HEIGHT, self.right_edge, self.current_y-Style.ROW_HEIGHT)
                self.current_y -= Style.ROW_HEIGHT

                # --- アイテム描画ループ (L3, L4の塊を意識) ---
                # データを "Block" に分割する
                # Block = [Header(opt), Item, ..., Footer(opt)]
                # L3が変わる or L4が変わるタイミングでブロックを切る
                
                current_l3 = ""
                current_l4 = ""
                sub_l3 = 0
                sub_l4 = 0
                
                # 処理しやすいようにグループ化
                # ここでは簡易的に1行ずつ処理しつつ、ヘッダー/フッター挿入時に改ページチェックを行う
                
                for idx, item in enumerate(items):
                    l3 = item['l3']
                    l4 = item['l4']
                    amt = item['amt_val']
                    
                    is_l3_change = (l3 != current_l3)
                    is_l4_change = (l4 != current_l4)
                    
                    # 1. 前のブロックのフッター処理
                    # L4 Footer
                    if current_l4 and (is_l4_change or is_l3_change):
                         if self._check_space(1, TITLE): pass # Footerだけ次に行くのは避けたいが…
                         self._draw_bold_string(self.col_x['name']+Style.INDENT_ITEM, self.current_y-5*mm, f"【{current_l4}】 小計", 9, colors.black)
                         self.c.setFont(self.font, 9); self.c.drawRightString(self.col_x['amt']+self.col_widths['amt']-2*mm, self.current_y-5*mm, f"{int(sub_l4):,}")
                         self.c.setLineWidth(0.5); self.c.setStrokeColor(colors.grey); self.c.line(Style.X_BASE, self.current_y-Style.ROW_HEIGHT, self.right_edge, self.current_y-Style.ROW_HEIGHT)
                         self.current_y -= Style.ROW_HEIGHT
                         sub_l4 = 0
                         current_l4 = "" # Reset
                    
                    # L3 Footer
                    if current_l3 and is_l3_change:
                         if self._check_space(1, TITLE): pass
                         self._draw_bold_string(self.col_x['name']+Style.INDENT_L3, self.current_y-5*mm, f"【{current_l3} 小計】", 9, Style.COLOR_L3)
                         self.c.setFont(self.font, 9); self.c.setFillColor(Style.COLOR_L3)
                         self.c.drawRightString(self.col_x['amt']+self.col_widths['amt']-2*mm, self.current_y-5*mm, f"{int(sub_l3):,}")
                         self.c.setLineWidth(0.5); self.c.setStrokeColor(colors.grey); self.c.line(Style.X_BASE, self.current_y-Style.ROW_HEIGHT, self.right_edge, self.current_y-Style.ROW_HEIGHT)
                         self.current_y -= Style.ROW_HEIGHT
                         sub_l3 = 0
                         current_l3 = ""

                    # 2. 新しいブロックのヘッダー処理
                    # ここで「Header + 少なくとも1行」が入るかチェックすると綺麗
                    rows_needed_for_start = 0
                    if is_l3_change and l3: rows_needed_for_start += 1
                    if is_l4_change and l4: rows_needed_for_start += 1
                    rows_needed_for_start += 1 # Item itself
                    
                    if self._check_space(rows_needed_for_start, TITLE):
                        # 改ページ時の見出し復帰
                        self._draw_bold_string(self.col_x['name']+Style.INDENT_L1, self.current_y-5*mm, f"■ {l1} (続き)", 10, Style.COLOR_L1)
                        self.current_y -= Style.ROW_HEIGHT
                        self._draw_bold_string(self.col_x['name']+Style.INDENT_L2, self.current_y-5*mm, f"● {l2} (続き)", 10, Style.COLOR_L2)
                        self.current_y -= Style.ROW_HEIGHT
                        if not is_l3_change and current_l3:
                             self._draw_bold_string(self.col_x['name']+Style.INDENT_L3, self.current_y-5*mm, f"・ {current_l3} (続き)", 10, Style.COLOR_L3)
                             self.current_y -= Style.ROW_HEIGHT

                    if is_l3_change and l3:
                        self._draw_bold_string(self.col_x['name']+Style.INDENT_L3, self.current_y-5*mm, f"・ {l3}", 10, Style.COLOR_L3)
                        self.c.setLineWidth(0.5); self.c.setStrokeColor(colors.grey); self.c.line(Style.X_BASE, self.current_y-Style.ROW_HEIGHT, self.right_edge, self.current_y-Style.ROW_HEIGHT)
                        self.current_y -= Style.ROW_HEIGHT
                        current_l3 = l3
                    
                    if is_l4_change and l4:
                        self._draw_bold_string(self.col_x['name']+Style.INDENT_ITEM, self.current_y-5*mm, f"【{l4}】", 9, colors.black)
                        self.c.setLineWidth(0.5); self.c.setStrokeColor(colors.grey); self.c.line(Style.X_BASE, self.current_y-Style.ROW_HEIGHT, self.right_edge, self.current_y-Style.ROW_HEIGHT)
                        self.current_y -= Style.ROW_HEIGHT
                        current_l4 = l4

                    # 3. アイテム描画
                    self.c.setFont(self.font, 9); self.c.setFillColor(colors.black)
                    self.c.drawString(self.col_x['name']+Style.INDENT_ITEM, self.current_y-5*mm, item.get('名称',''))
                    self.c.setFont(self.font, 8)
                    self.c.drawString(self.col_x['spec']+1*mm, self.current_y-5*mm, item.get('規格',''))
                    
                    self.c.setFont(self.font, 9)
                    if item['qty_val']: self.c.drawRightString(self.col_x['qty']+self.col_widths['qty']-2*mm, self.current_y-5*mm, f"{item['qty_val']:,.2f}")
                    self.c.drawCentredString(self.col_x['unit']+self.col_widths['unit']/2, self.current_y-5*mm, item.get('単位',''))
                    if item['price_val']: self.c.drawRightString(self.col_x['price']+self.col_widths['price']-2*mm, self.current_y-5*mm, f"{int(item['price_val']):,}")
                    if item['amt_val']: self.c.drawRightString(self.col_x['amt']+self.col_widths['amt']-2*mm, self.current_y-5*mm, f"{int(item['amt_val']):,}")
                    
                    self.c.setFont(self.font, 8)
                    self.c.drawString(self.col_x['rem']+1*mm, self.current_y-5*mm, item.get('備考',''))
                    
                    self.c.setLineWidth(0.5); self.c.setStrokeColor(colors.grey); self.c.line(Style.X_BASE, self.current_y-Style.ROW_HEIGHT, self.right_edge, self.current_y-Style.ROW_HEIGHT)
                    self.current_y -= Style.ROW_HEIGHT
                    
                    sub_l3 += amt
                    sub_l4 += amt

                # ループ終了後の残存フッター処理
                if current_l4:
                    if self._check_space(1, TITLE): pass
                    self._draw_bold_string(self.col_x['name']+Style.INDENT_ITEM, self.current_y-5*mm, f"【{current_l4}】 小計", 9, colors.black)
                    self.c.setFont(self.font, 9); self.c.drawRightString(self.col_x['amt']+self.col_widths['amt']-2*mm, self.current_y-5*mm, f"{int(sub_l4):,}")
                    self.c.setLineWidth(0.5); self.c.setStrokeColor(colors.grey); self.c.line(Style.X_BASE, self.current_y-Style.ROW_HEIGHT, self.right_edge, self.current_y-Style.ROW_HEIGHT)
                    self.current_y -= Style.ROW_HEIGHT
                
                if current_l3:
                    if self._check_space(1, TITLE): pass
                    self._draw_bold_string(self.col_x['name']+Style.INDENT_L3, self.current_y-5*mm, f"【{current_l3} 小計】", 9, Style.COLOR_L3)
                    self.c.setFont(self.font, 9); self.c.setFillColor(Style.COLOR_L3)
                    self.c.drawRightString(self.col_x['amt']+self.col_widths['amt']-2*mm, self.current_y-5*mm, f"{int(sub_l3):,}")
                    self.c.setLineWidth(0.5); self.c.setStrokeColor(colors.grey); self.c.line(Style.X_BASE, self.current_y-Style.ROW_HEIGHT, self.right_edge, self.current_y-Style.ROW_HEIGHT)
                    self.current_y -= Style.ROW_HEIGHT

                # L2 Footer
                if self._check_space(1, TITLE): pass
                self._draw_bold_string(self.col_x['name']+Style.INDENT_L2, self.current_y-5*mm, f"【{l2} 計】", 10, Style.COLOR_L2)
                self.c.setFont(self.font, 10); self.c.setFillColor(Style.COLOR_L2)
                self.c.drawRightString(self.col_x['amt']+self.col_widths['amt']-2*mm, self.current_y-5*mm, f"{int(l2_total):,}")
                self.c.setLineWidth(1.0); self.c.setStrokeColor(Style.COLOR_L2); self.c.line(Style.X_BASE, self.current_y-Style.ROW_HEIGHT, self.right_edge, self.current_y-Style.ROW_HEIGHT)
                self.current_y -= Style.ROW_HEIGHT

            # L1 Footer
            if self._check_space(1, TITLE): pass
            self._draw_bold_string(self.col_x['name']+Style.INDENT_L1, self.current_y-5*mm, f"【{l1} 計】", 10, Style.COLOR_L1)
            self.c.setFont(self.font, 10); self.c.setFillColor(Style.COLOR_L1)
            self.c.drawRightString(self.col_x['amt']+self.col_widths['amt']-2*mm, self.current_y-5*mm, f"{int(l1_total):,}")
            self.c.setLineWidth(1.0); self.c.setStrokeColor(Style.COLOR_L1); self.c.line(Style.X_BASE, self.current_y-Style.ROW_HEIGHT, self.right_edge, self.current_y-Style.ROW_HEIGHT)
            self.current_y -= Style.ROW_HEIGHT
            
            self.current_y -= 2*mm # Spacer

        # 最後に諸経費ブロック
        self._draw_total_block(TITLE)
        self._draw_grid_frame()
        self.c.showPage()

    def generate(self) -> io.BytesIO:
        self.draw_cover()
        self.draw_summary()
        self.draw_grand_summary_table()
        self.draw_breakdown_table()
        self.draw_detail_table()
        
        self.c.save()
        self.buffer.seek(0)
        return self.buffer
