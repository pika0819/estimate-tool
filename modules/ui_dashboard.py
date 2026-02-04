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
    
    # ツリーのノードリストを作成
    tree_items = []
    
    # 1. 大項目ループ
    for large in sorted(df_tree['大項目'].unique()):
        if not large: continue
        
        # 大項目の金額計算
        df_l = df_tree[df_tree['大項目'] == large]
        l_total = df_l['見積金額'].sum()
        
        mid_nodes = []
        
        # 2. 中項目ループ
        for mid in sorted(df_l['中項目'].unique()):
            if not mid: continue
            
            # 中項目の金額計算
            df_m = df_l[df_l['中項目'] == mid]
            m_total = df_m['見積金額'].sum()
            
            small_nodes = []
            
            # 3. 小項目ループ
            for small in sorted(df_m['小項目'].unique()):
                # 小項目ごとのデータを抽出
                df_s = df_m[df_m['小項目'] == small]
                
                # --- 小項目が「空」の場合（＝部分項目が中項目に直結する場合） ---
                if not small:
                    # 部分項目を直接 中項目の子供 として追加
                    for part in sorted(df_s['部分項目'].unique()):
                        if not part: continue
                        p_total = df_s[df_s['部分項目'] == part]['見積金額'].sum()
                        
                        # IDキー: "大::中::小::部分"
                        key = f"{large}::{mid}::::{part}"
                        small_nodes.append(sac.TreeItem(
                            get_label(part, p_total), 
                            icon='file-text', 
                            key=key
                        ))
                
                # --- 小項目がある場合 ---
                else:
                    s_total = df_s['見積金額'].sum()
                    part_nodes = []
                    
                    # 4. 部分項目ループ
                    for part in sorted(df_s['部分項目'].unique()):
                        if not part: continue
                        p_total = df_s[df_s['部分項目'] == part]['見積金額'].sum()
                        
                        key = f"{large}::{mid}::{small}::{part}"
                        part_nodes.append(sac.TreeItem(
                            get_label(part, p_total), 
                            icon='file-text', 
                            key=key
                        ))
                    
                    # 小項目ノード作成（子供がいればフォルダ、いなければファイル扱い）
                    key = f"{large}::{mid}::{small}::"
                    icon = 'folder' if part_nodes else 'file-text'
                    small_nodes.append(sac.TreeItem(
                        get_label(small, s_total), 
                        icon=icon, 
                        children=part_nodes, 
                        key=key
                    ))

            # 中項目ノード作成
            key = f"{large}::{mid}::::"
            mid_nodes.append(sac.TreeItem(
                get_label(mid, m_total), 
                icon='folder', 
                children=small_nodes, 
                key=key
            ))
            
        # 大項目ノード作成
        key = f"{large}::::::"
        tree_items.append(sac.TreeItem(
            get_label(large, l_total), 
            icon='folder', 
            children=mid_nodes, 
            key=key
        ))

    # --- ツリー表示 ---
    # return_index=Falseにすると、key（大::中::小::部分）が返ってくる
    selected_key = sac.tree(
        items=tree_items,
        label="",
        index=0,
        align='left',
        size='sm',
        icon='folder',
        open_all=False,
        return_index=False
    )
    
    # 選択されたキーを分解して返す
    if selected_key:
        try:
            l, m, s, p = selected_key.split("::")
            # 空文字ならNoneに戻す（フィルタリング用）
            return (l or None, m or None, s or None, p or None)
        except:
            return None, None, None, None
            
    return None, None, None, None


def render_playlist_editor(filtered_df):
    """
    メイン画面に表示する明細リスト（変更なし、前回と同じ）
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
