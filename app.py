# 5. 明細書（バグ修正版：ヘッダー制御＆合計行の吸着強化）
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
                # 前のL1との間に空行を入れるか判断
                if y <= bottom_margin + row_height * 2:
                    while y > bottom_margin + 0.1: draw_grid_line(y - row_height); y -= row_height
                    draw_vertical_lines(y_start, y) # 修正: 実際のyまで引く
                    c.showPage()
                    p_num += 1; draw_page_header_common(p_num, "内 訳 明 細 書 (詳細)"); y = y_start
                else:
                    draw_grid_line(y - row_height); y -= row_height

            # 大項目ヘッダー
            if y <= bottom_margin + row_height:
                while y > bottom_margin + 0.1: draw_grid_line(y - row_height); y -= row_height
                draw_vertical_lines(y_start, y)
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
                
                # 最後の中項目なら、このブロックに大項目の合計も追加
                if is_last_l2:
                     block_items.append({'type': 'footer_l1', 'label': f"【{l1} 計】", 'amt': l1_total})
                else:
                    block_items.append({'type': 'empty_row'}); block_items.append({'type': 'empty_row'})
                
                while block_items and block_items[-1]['type'] == 'empty_row': block_items.pop()

                # ★状態管理フラグ
                active_l3_label = None
                active_l4_label = None
                l2_has_started = False # このページでL2ヘッダーを書き始めたか？

                # 描画ループ
                for b in block_items:
                    itype = b['type']
                    
                    # 状態更新
                    if itype == 'header_l2': l2_has_started = True
                    elif itype == 'header_l3': active_l3_label = b['label']
                    elif itype == 'footer_l3': active_l3_label = None
                    elif itype == 'header_l4': active_l4_label = b['label']
                    elif itype == 'footer_l4': active_l4_label = None

                    # --- 改ページ判定 ---
                    # ★修正: 大項目計(footer_l1)の場合は、絶対に改ページさせない（余白に食い込んでも書く）
                    force_stay = (itype == 'footer_l1')

                    if y <= bottom_margin and not force_stay:
                        # ページ末端処理
                        draw_vertical_lines(y_start, y) # 実際のyまで引く
                        c.showPage()
                        p_num += 1; draw_page_header_common(p_num, "内 訳 明 細 書 (詳細)"); y = y_start
                        
                        # ★続きヘッダーの描画
                        draw_bold_string(col_x['name']+INDENT_L1, y-5*mm, f"■ {l1} (続き)", 10, COLOR_L1)
                        draw_grid_line(y - row_height); y -= row_height
                        
                        # ★修正: 中項目(続き)は、「すでに中項目が始まっている」かつ「これから書くのが大項目計ではない」場合のみ表示
                        # これにより、フライング表示や、大項目計だけのページでの不要なヘッダーを防ぐ
                        if l2_has_started and itype != 'footer_l1':
                            draw_bold_string(col_x['name']+INDENT_L2, y-5*mm, f"● {l2} (続き)", 10, COLOR_L2)
                            draw_grid_line(y - row_height); y -= row_height

                        if active_l3_label:
                            draw_bold_string(col_x['name']+INDENT_L3, y-5*mm, f"{active_l3_label} (続き)", 10, COLOR_L3)
                            draw_grid_line(y - row_height); y -= row_height
                        
                        if active_l4_label:
                            draw_bold_string(col_x['name']+INDENT_ITEM, y-5*mm, f"{active_l4_label} (続き)", 9, colors.black)
                            draw_grid_line(y - row_height); y -= row_height

                    # 底打ちロジック (伝統的な下揃え)
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

        # 最後のページの残りを埋める
        while y > bottom_margin + 0.1: draw_grid_line(y - row_height); y -= row_height
        
        # ★修正: 最後の縦線は、現在のy位置とbottom_marginのうち、より下にある(値が小さい)方に合わせる
        # これにより、大項目計が枠外にはみ出しても、縦線がそこまで伸びるようになる
        final_line_y = min(y, bottom_margin)
        draw_vertical_lines(y_start, final_line_y)
        
        c.showPage(); p_num += 1
        return p_num
