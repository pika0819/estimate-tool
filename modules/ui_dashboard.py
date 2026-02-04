import streamlit as st
import pandas as pd
import streamlit_antd_components as sac

def get_label(name, amount):
    """表示用ラベルを作成（金額付き）"""
    return f"{name} (¥{amount:,.0f})"

def render_folder_tree(df):
    """
    サイドバーにエクスプローラー風のツリーを表示する
    戻り値: 選択された (大項目, 中項目, 小項目, 部分項目) のタプル
    """
    st.sidebar.markdown("### 📂 フォルダ (階層)")
    
    if df is None or df.empty:
        return None, None, None, None

    # NaNを空文字に変換して扱いやすくする
    df_tree = df.fillna("")
    
    # ツリーアイテムリストと、ラベルからデータを引くための辞書を作成
    tree_items = []
    label_map = {} # { "ラベル名": (大, 中, 小, 部分) }
    
    # --- 1. 大項目 ---
    for large in sorted(df_tree['大項目'].unique()):
        if not large: continue
        
        # 大項目の金額とラベル
        l_total = df_tree[df_tree['大項目'] == large]['見積金額'].sum()
        l_label = get_label(large, l_total)
        label_map[l_label] = (large, None, None, None)
        
        mid_nodes = []
        
        # 大項目データ
        df_l = df_tree[df_tree['大項目'] == large]
        
        # --- 2. 中項目 ---
        for mid in sorted(df_l['中項目'].unique()):
            if not mid: continue
            
            m_total = df_l[df_l['中項目'] == mid]['見積金額'].sum()
            m_label = get_label(mid, m_total)
            label_map[m_label] = (large, mid, None, None)
            
            small_nodes = []
            df_m = df_l[df_l['中項目'] == mid]
            
            # --- 3. 小項目 ---
            for small in sorted(df_m['小項目'].unique()):
                df_s = df_m[df_m['小項目'] == small]
                
                # A. 小項目が「空」の場合（＝部分項目が中項目直下）
                if not small:
                    for part in sorted(df_s['部分項目'].unique()):
                        if not part: continue
                        p_total = df_s[df_s['部分項目'] == part]['見積金額'].sum()
                        p_label = get_label(part, p_total)
                        
                        # 中項目の子供として追加
                        small_nodes.append(sac.TreeItem(p_label, icon='file-text'))
                        label_map[p_label] = (large, mid, None, part)
                
                # B. 小項目がある場合
                else:
                    s_total = df_s['見積金額'].sum()
                    s_label = get_label(small, s_total)
                    label_map[s_label] = (large, mid, small, None)
                    
                    part_nodes = []
                    
                    # --- 4. 部分項目 ---
                    for part in sorted(df_s['部分項目'].unique()):
                        if not part: continue
                        p_total = df_s[df_s['部分項目'] == part]['見積金額'].sum()
                        p_label = get_label(part, p_total)
                        
                        part_nodes.append(sac.TreeItem(p_label, icon='file-text'))
                        label_map[p_label] = (large, mid, small, part)
                    
                    # 小項目ノード追加
                    icon = 'folder' if part_nodes else 'file-text'
                    small_nodes.append(sac.TreeItem(s_label, icon=icon, children=part_nodes))

            # 中項目ノード追加
            mid_nodes.append(sac.TreeItem(m_label, icon='folder', children=small_nodes))
            
        # 大項目ノード追加
        tree_items.append(sac.TreeItem(l_label, icon='folder', children=mid_nodes))

    # --- ツリー表示 ---
    # return_index=False にして「ラベル文字列」を受け取る
    selected_label = sac.tree(
        items=tree_items,
        label="",
        index=0,
        align='left',
        size='sm',
        icon='folder',
        open_all=False,
        return_index=False
    )
    
    # 選択されたラベルからデータを逆引きする
    if selected_label in label_map:
        return label_map[selected_label]
            
    return None, None, None, None

def render_playlist_editor(filtered_df):
    """
    メイン画面に表示する明細リスト
    """
    # 表示用にデータをコピーして加工する（計算用の元データは触らない）
    df_display = filtered_df.copy()
    
    # 数値列を「カンマ区切り文字列」に変換する (¥1,000形式)
    # ※編集可能な列(原単価)は数値のままにし、閲覧用の列だけ整形する
    format_cols = ['NET', '売単価', '見積金額']
    for col in format_cols:
        if col in df_display.columns:
            df_display[col] = df_display[col].apply(lambda x: f"¥{x:,.0f}")

    column_config = {
        "確認": st.column_config.CheckboxColumn("確認", width="small"),
        "sort_key": st.column_config.NumberColumn(
            "SortID", disabled=False, format="%d", help="並び順"
        ),
        "名称": st.column_config.TextColumn("名称", width="large", required=True),
        "規格": st.column_config.TextColumn("規格", width="medium"),
        "数量": st.column_config.NumberColumn("数量", step=0.1, format="%.2f", width="small"),
        "単位": st.column_config.TextColumn("単位", width="small"),
        
        # 編集可能な「原単価」は数値入力のためNumberColumnのまま (カンマ表示は難しいが入力しやすさ優先)
        "原単価": st.column_config.NumberColumn("原単価", format="%.0f", step=100),
        "掛率": st.column_config.NumberColumn("掛率", step=0.01, format="%.2f", width="small"),
        
        # 閲覧用列は TextColumn にしてカンマ付き文字列を表示
        "NET": st.column_config.TextColumn("NET", width="small"),
        "売単価": st.column_config.TextColumn("売単価", width="small"),
        "見積金額": st.column_config.TextColumn("見積金額", width="medium"),
        
        "備考": st.column_config.TextColumn("備考", width="medium"),
        "(自)荒利率": st.column_config.NumberColumn("率", format="%.1f%%", disabled=True),
        "部分項目": st.column_config.TextColumn("部分項目", disabled=True) 
    }
    
    display_cols = [
        '確認', 'sort_key', '名称', '規格', '数量', '単位', 
        '原単価', '掛率', '見積金額', '備考', 'NET'
    ]

    edited_df = st.data_editor(
        df_display[display_cols],
        column_config=column_config,
        use_container_width=True,
        height=600,
        num_rows="dynamic",
        key="playlist_editor"
    )
    
    # 編集結果を返す際は、文字列になった金額列は無視して、編集可能な列だけ返す
    # (dev_main.py側で再計算されるため、金額列の値は捨てて良い)
    return edited_df
