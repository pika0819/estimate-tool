import streamlit as st
import pandas as pd
import streamlit_antd_components as sac

def get_base_label(name, amount):
    """基本の表示ラベルを作成（金額付き）"""
    return f"{name} (¥{amount:,.0f})"

def make_unique(label, existing_labels):
    """
    同じラベル（名前・金額）が既に存在する場合、
    見た目には見えない「透明な文字」を追加してユニークにする魔法
    """
    unique_label = label
    while unique_label in existing_labels:
        unique_label += "\u200b" # ゼロ幅スペース（見えない文字）を追加
    return unique_label

def render_folder_tree(df):
    """
    サイドバーにエクスプローラー風のツリーを表示する
    （エラー回避 & 重複対策済みバージョン）
    """
    st.sidebar.markdown("### 📂 フォルダ (階層)")
    
    if df is None or df.empty:
        return None, None, None, None

    df_tree = df.fillna("")
    
    tree_items = []
    label_map = {} # 表示ラベル -> データ(ID) の対応表
    
    # --- 1. 大項目 ---
    for large in sorted(df_tree['大項目'].unique()):
        if not large: continue
        
        # ラベル作成
        l_total = df_tree[df_tree['大項目'] == large]['見積金額'].sum()
        l_label_base = get_base_label(large, l_total)
        l_label = make_unique(l_label_base, label_map)
        
        # マップに登録 & ノード作成準備
        label_map[l_label] = (large, None, None, None)
        mid_nodes = []
        
        df_l = df_tree[df_tree['大項目'] == large]
        
        # --- 2. 中項目 ---
        for mid in sorted(df_l['中項目'].unique()):
            if not mid: continue
            
            m_total = df_l[df_l['中項目'] == mid]['見積金額'].sum()
            m_label_base = get_base_label(mid, m_total)
            m_label = make_unique(m_label_base, label_map)
            
            label_map[m_label] = (large, mid, None, None)
            small_nodes = []
            
            df_m = df_l[df_l['中項目'] == mid]
            
            # --- 3. 小項目 ---
            for small in sorted(df_m['小項目'].unique()):
                df_s = df_m[df_m['小項目'] == small]
                
                # A. 小項目なし（部分項目が直結）
                if not small:
                    for part in sorted(df_s['部分項目'].unique()):
                        if not part: continue
                        p_total = df_s[df_s['部分項目'] == part]['見積金額'].sum()
                        p_label_base = get_base_label(part, p_total)
                        p_label = make_unique(p_label_base, label_map)
                        
                        label_map[p_label] = (large, mid, None, part)
                        # key引数は削除！
                        small_nodes.append(sac.TreeItem(p_label, icon='file-text'))
                
                # B. 小項目あり
                else:
                    s_total = df_s['見積金額'].sum()
                    s_label_base = get_base_label(small, s_total)
                    s_label = make_unique(s_label_base, label_map)
                    
                    label_map[s_label] = (large, mid, small, None)
                    part_nodes = []
                    
                    # --- 4. 部分項目 ---
                    for part in sorted(df_s['部分項目'].unique()):
                        if not part: continue
                        p_total = df_s[df_s['部分項目'] == part]['見積金額'].sum()
                        p_label_base = get_base_label(part, p_total)
                        p_label = make_unique(p_label_base, label_map)
                        
                        label_map[p_label] = (large, mid, small, part)
                        # key引数は削除！
                        part_nodes.append(sac.TreeItem(p_label, icon='file-text'))
                    
                    icon = 'folder' if part_nodes else 'file-text'
                    # key引数は削除！
                    small_nodes.append(sac.TreeItem(s_label, icon=icon, children=part_nodes))

            # key引数は削除！
            mid_nodes.append(sac.TreeItem(m_label, icon='folder', children=small_nodes))
            
        # key引数は削除！
        tree_items.append(sac.TreeItem(l_label, icon='folder', children=mid_nodes))

    # --- ツリー表示 ---
    # return_index=False でラベル文字列（透明文字含む）を受け取る
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
    
    # マップからデータを引く
    if selected_label in label_map:
        return label_map[selected_label]
            
    return None, None, None, None

def render_playlist_editor(filtered_df):
    """
    メイン画面に表示する明細リスト
    """
    df_display = filtered_df.copy()
    
    # 数値列を文字列（カンマ区切り）に変換するロジック
    # 1000 -> "1,000"
    format_cols = ['NET', '売単価', '見積金額']
    for col in format_cols:
        if col in df_display.columns:
            df_display[col] = df_display[col].apply(
                lambda x: f"{x:,.0f}" if pd.notnull(x) and isinstance(x, (int, float)) else ""
            )

    column_config = {
        "確認": st.column_config.CheckboxColumn("確認", width="small"),
        "sort_key": st.column_config.NumberColumn(
            "SortID", disabled=False, format="%d", help="並び順"
        ),
        "名称": st.column_config.TextColumn("名称", width="large", required=True),
        "規格": st.column_config.TextColumn("規格", width="medium"),
        "数量": st.column_config.NumberColumn("数量", step=0.1, format="%.2f", width="small"),
        "単位": st.column_config.TextColumn("単位", width="small"),
        
        # 原単価は入力用なので数値のまま
        "原単価": st.column_config.NumberColumn("原単価", format="%d", step=100),
        "掛率": st.column_config.NumberColumn("掛率", step=0.01, format="%.2f", width="small"),
        
        # 表示用列（TextColumn）でカンマ付き文字列を表示
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
    
    return edited_df
