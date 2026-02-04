import streamlit as st
import pandas as pd

def get_label_with_amount(name, df_subset):
    """
    項目名と、そのデータの合計金額を組み合わせて表示用のラベルを作る
    例: "仮設工事 (¥1,500,000)"
    """
    if name == "(すべて)":
        return name
    
    total = df_subset['見積金額'].sum()
    return f"{name} (¥{total:,.0f})"

def render_folder_tree(df):
    """
    サイドバーに表示する階層選択ツリー（4階層・金額表示付き）
    """
    st.sidebar.markdown("### 📂 フォルダ (階層)")
    
    # --- 1. 大項目 ---
    if df is None or df.empty:
        return "(すべて)", "(すべて)", "(すべて)", "(すべて)"

    # 大項目ごとの合計を計算してラベル化
    large_opts = ["(すべて)"]
    unique_large = sorted(list(df[df['大項目'].astype(str) != '']['大項目'].unique()))
    
    # 選択肢辞書を作る {表示名: 実データ名}
    large_labels = {}
    large_labels["(すべて)"] = "(すべて)"
    for item in unique_large:
        # その大項目のデータだけ抽出して計算
        sub = df[df['大項目'] == item]
        label = get_label_with_amount(item, sub)
        large_labels[label] = item
        large_opts.append(label)

    sel_large_label = st.sidebar.selectbox("1. 大項目", large_opts)
    sel_large = large_labels[sel_large_label]
    
    # --- 2. 中項目 ---
    mid_opts = ["(すべて)"]
    mid_labels = {"(すべて)": "(すべて)"}
    
    if sel_large != "(すべて)":
        filtered_mid = df[df['大項目'] == sel_large]
        unique_mid = sorted(list(filtered_mid[filtered_mid['中項目'].astype(str) != '']['中項目'].unique()))
        
        for item in unique_mid:
            sub = filtered_mid[filtered_mid['中項目'] == item]
            label = get_label_with_amount(item, sub)
            mid_labels[label] = item
            mid_opts.append(label)
            
    sel_mid_label = st.sidebar.selectbox("2. 中項目", mid_opts)
    sel_mid = mid_labels[sel_mid_label]
    
    # --- 3. 小項目 ---
    small_opts = ["(すべて)"]
    small_labels = {"(すべて)": "(すべて)"}
    
    if sel_mid != "(すべて)":
        filtered_small = df[(df['大項目'] == sel_large) & (df['中項目'] == sel_mid)]
        unique_small = sorted(list(filtered_small[filtered_small['小項目'].astype(str) != '']['小項目'].unique()))
        
        for item in unique_small:
            sub = filtered_small[filtered_small['小項目'] == item]
            label = get_label_with_amount(item, sub)
            small_labels[label] = item
            small_opts.append(label)
            
    sel_small_label = st.sidebar.selectbox("3. 小項目", small_opts)
    sel_small = small_labels[sel_small_label]

    # --- 4. 部分項目 (New!) ---
    part_opts = ["(すべて)"]
    part_labels = {"(すべて)": "(すべて)"}
    
    if sel_small != "(すべて)":
        filtered_part = df[(df['大項目'] == sel_large) & (df['中項目'] == sel_mid) & (df['小項目'] == sel_small)]
        unique_part = sorted(list(filtered_part[filtered_part['部分項目'].astype(str) != '']['部分項目'].unique()))
        
        for item in unique_part:
            sub = filtered_part[filtered_part['部分項目'] == item]
            label = get_label_with_amount(item, sub)
            part_labels[label] = item
            part_opts.append(label)
    
    sel_part_label = st.sidebar.selectbox("4. 部分項目", part_opts)
    sel_part = part_labels[sel_part_label]

    return sel_large, sel_mid, sel_small, sel_part

def render_playlist_editor(filtered_df):
    """
    メイン画面に表示する明細リスト
    """
    column_config = {
        "確認": st.column_config.CheckboxColumn("済", width="small"),
        
        "名称": st.column_config.TextColumn("名称", width="large", required=True),
        "規格": st.column_config.TextColumn("規格", width="medium"),
        
        "数量": st.column_config.NumberColumn("数量", step=0.1, format="%.2f", width="small"),
        "単位": st.column_config.TextColumn("単位", width="small"),
        
        # カンマ区切り (format="¥%d") を適用
        "NET": st.column_config.NumberColumn("NET", format="¥%d", step=100),
        "原単価": st.column_config.NumberColumn("原単価", format="¥%d", step=100),
        "掛率": st.column_config.NumberColumn("掛率", step=0.01, format="%.2f", width="small"),
        
        "売単価": st.column_config.NumberColumn("売単価", format="¥%d", disabled=True),
        "見積金額": st.column_config.NumberColumn("見積金額", format="¥%d", disabled=True),
        "荒利率": st.column_config.NumberColumn("率", format="%.1f%%", disabled=True),
        
        # ソートキーは編集可能に
        "sort_key": st.column_config.NumberColumn("SortID", disabled=False, format="%d"),
        
        # 部分項目はサイドバーで選ぶので、表からは隠す (非表示にはしないが、Config定義を外すかhiddenにする)
        "部分項目": st.column_config.TextColumn("部分項目", disabled=True) 
    }
    
    # 部分項目を列から外す（サイドバーで絞り込んでいる前提）
    display_cols = [
        '確認', '名称', '規格', '数量', '単位',
        'NET', '原単価', '掛率', '売単価', '見積金額', '荒利率', 
        '備考', 'sort_key'
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
