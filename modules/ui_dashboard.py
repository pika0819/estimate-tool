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
    
    # 1. ツリー構築（表示用と、データ特定用の「影の台帳」を同時に作る）
    tree_items = []   # sac.TreeItemのリスト（画面表示用）
    shadow_data = []  # 裏でデータを保持するリスト（選択判定用）
    
    # --- 1. 大項目 ---
    for large in sorted(df_tree['大項目'].unique()):
        if not large: continue
        
        # 大項目の金額
        df_l = df_tree[df_tree['大項目'] == large]
        l_total = df_l['見積金額'].sum()
        
        mid_nodes = []
        mid_shadow = []
        
        # --- 2. 中項目 ---
        for mid in sorted(df_l['中項目'].unique()):
            if not mid: continue
            
            # 中項目の金額
            df_m = df_l[df_l['中項目'] == mid]
            m_total = df_m['見積金額'].sum()
            
            small_nodes = []
            small_shadow = []
            
            # --- 3. 小項目 ---
            for small in sorted(df_m['小項目'].unique()):
                df_s = df_m[df_m['小項目'] == small]
                
                # A. 小項目が「空」の場合（＝部分項目が中項目の直下に来る）
                if not small:
                    for part in sorted(df_s['部分項目'].unique()):
                        if not part: continue
                        p_total = df_s[df_s['部分項目'] == part]['見積金額'].sum()
                        
                        # 中項目の子供として直接追加
                        small_nodes.append(sac.TreeItem(get_label(part, p_total), icon='file-text'))
                        # 影の台帳: (大, 中, なし, 部分)
                        small_shadow.append((large, mid, None, part))
                
                # B. 小項目がある場合
                else:
                    s_total = df_s['見積金額'].sum()
                    part_nodes = []
                    part_shadow = []
                    
                    # --- 4. 部分項目 ---
                    for part in sorted(df_s['部分項目'].unique()):
                        if not part: continue
                        p_total = df_s[df_s['部分項目'] == part]['見積金額'].sum()
                        
                        part_nodes.append(sac.TreeItem(get_label(part, p_total), icon='file-text'))
                        # 影の台帳: (大, 中, 小, 部分)
                        part_shadow.append((large, mid, small, part))
                    
                    # 小項目ノード追加
                    icon = 'folder' if part_nodes else 'file-text'
                    small_nodes.append(sac.TreeItem(get_label(small, s_total), icon=icon, children=part_nodes))
                    
                    # 影の台帳: 自身のデータ + 子供たち
                    # 子供がいる場合は、自分自身が選ばれたら (大, 中, 小, None) とする
                    small_shadow_item = {
                        "value": (large, mid, small, None),
                        "children": part_shadow
                    }
                    small_shadow.append(small_shadow_item)

            # 中項目ノード追加
            mid_nodes.append(sac.TreeItem(get_label(mid, m_total), icon='folder', children=small_nodes))
            
            # 影の台帳: 中項目の定義
            mid_shadow_item = {
                "value": (large, mid, None, None),
                "children": small_shadow
            }
            mid_shadow.append(mid_shadow_item)
            
        # 大項目ノード追加
        tree_items.append(sac.TreeItem(get_label(large, l_total), icon='folder', children=mid_nodes))
        
        # 影の台帳: 大項目の定義
        large_shadow_item = {
            "value": (large, None, None, None),
            "children": mid_shadow
        }
        shadow_data.append(large_shadow_item)

    # --- ツリー表示 ---
    # return_index=True にして、[0, 1, 2] のようなインデックス配列を受け取る
    selected_indices = sac.tree(
        items=tree_items,
        label="",
        index=0,
        align='left',
        size='sm',
        icon='folder',
        open_all=False,
        return_index=True
    )
    
    # --- 選択されたインデックスからデータを復元する ---
    try:
        if selected_indices is None:
            return None, None, None, None
            
        # 影の台帳をたどる
        current_level = shadow_data
        selected_value = None
        
        # インデックスの階層を順番に降りていく
        # 例: [0, 2] なら、大項目の0番目 -> その子供(中項目)の2番目
        for idx in selected_indices:
            node = current_level[idx]
            
            # nodeが辞書なら（子供がいるフォルダ）、childrenへ潜る
            if isinstance(node, dict):
                selected_value = node["value"] # とりあえず今の階層の値を保持
                current_level = node["children"]
            # nodeがタプルなら（末端のファイル）、それが答え
            else:
                selected_value = node
                current_level = [] # もう子供はいない
        
        if selected_value:
            return selected_value
            
    except Exception as e:
        # 万が一インデックスがズレた場合などの安全策
        st.error(f"Tree Selection Error: {e}")
        return None, None, None, None
            
    return None, None, None, None

def render_playlist_editor(filtered_df):
    """
    メイン画面に表示する明細リスト
    """
    column_config = {
        "確認": st.column_config.CheckboxColumn("確認", width="small"),
        "sort_key": st.column_config.NumberColumn(
            "SortID (並び順)", disabled=False, format="%d", help="ここを書き換えて保存すると並び順が変わります"
        ),
        "名称": st.column_config.TextColumn("名称", width="large", required=True),
        "規格": st.column_config.TextColumn("規格", width="medium"),
        "数量": st.column_config.NumberColumn("数量", step=0.1, format="%.2f", width="small"),
        "単位": st.column_config.TextColumn("単位", width="small"),
        "原単価": st.column_config.NumberColumn("原単価 (¥)", format="%.0f", step=100),
        "NET": st.column_config.NumberColumn("NET (¥)", format="%.0f", step=100),
        "掛率": st.column_config.NumberColumn("掛率", step=0.01, format="%.2f", width="small"),
        "売単価": st.column_config.NumberColumn("売単価 (¥)", format="%.0f", disabled=True),
        "見積金額": st.column_config.NumberColumn("見積金額 (¥)", format="%.0f", disabled=True),
        "備考": st.column_config.TextColumn("備考", width="medium"),
        "(自)荒利率": st.column_config.NumberColumn("率", format="%.1f%%", disabled=True),
        "部分項目": st.column_config.TextColumn("部分項目", disabled=True) 
    }
    
    display_cols = [
        '確認', 'sort_key', '名称', '規格', '数量', '単位', 
        '原単価', '掛率', '見積金額', '備考', 'NET'
    ]

    edited_df = st.data_editor(
        filtered_df[display_cols],
        column_config=column_config,
        use_container_width=True,
        height=600,
        num_rows="dynamic",
        key="playlist_editor"
    )
    
    return edited_df
