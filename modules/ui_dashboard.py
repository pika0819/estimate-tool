import streamlit as st
import pandas as pd

def render_folder_tree(df):
    """
    サイドバーに表示する階層選択ツリー（Googleドライブ風）
    戻り値: (選択された大項目, 選択された中項目, 選択された小項目)
    """
    st.sidebar.markdown("### 📂 フォルダ (階層)")
    
    # 1. 大項目
    # データが存在しない場合のエラー回避のため、リスト作成時は注意
    if df is None or df.empty:
        return "(すべて)", "(すべて)", "(すべて)"

    large_opts = ["(すべて)"] + sorted(list(df[df['大項目'].astype(str) != '']['大項目'].unique()))
    sel_large = st.sidebar.selectbox("1. 大項目", large_opts)
    
    # 2. 中項目
    if sel_large != "(すべて)":
        # 選ばれた大項目に含まれる中項目だけを抽出
        filtered_mid = df[df['大項目'] == sel_large]
        mid_opts = ["(すべて)"] + sorted(list(filtered_mid[filtered_mid['中項目'].astype(str) != '']['中項目'].unique()))
    else:
        mid_opts = ["(すべて)"]
    sel_mid = st.sidebar.selectbox("2. 中項目", mid_opts)
    
    # 3. 小項目
    if sel_mid != "(すべて)":
        # 選ばれた大・中項目に含まれる小項目だけを抽出
        filtered_small = df[(df['大項目'] == sel_large) & (df['中項目'] == sel_mid)]
        small_opts = ["(すべて)"] + sorted(list(filtered_small[filtered_small['小項目'].astype(str) != '']['小項目'].unique()))
    else:
        small_opts = ["(すべて)"]
    sel_small = st.sidebar.selectbox("3. 小項目", small_opts)

    return sel_large, sel_mid, sel_small

def render_playlist_editor(filtered_df):
    """
    メイン画面に表示する明細リスト（LINE MUSIC風プレイリスト）
    """
    # エディタの表示設定
    column_config = {
        "確認": st.column_config.CheckboxColumn("済", width="small"),
        
        "名称": st.column_config.TextColumn("名称", width="large", required=True),
        "規格": st.column_config.TextColumn("規格", width="medium"),
        
        "数量": st.column_config.NumberColumn("数量", step=0.1, format="%.2f", width="small"),
        "単位": st.column_config.TextColumn("単位", width="small"),
        
        "NET": st.column_config.NumberColumn("NET", format="¥%d", help="仕入値"),
        "原単価": st.column_config.NumberColumn("原単価", format="¥%d", step=100),
        "掛率": st.column_config.NumberColumn("掛率", step=0.01, format="%.2f", width="small"),
        
        # 自動計算される列は編集不可(disabled)にする
        "売単価": st.column_config.NumberColumn("売単価", format="¥%d", disabled=True),
        "見積金額": st.column_config.NumberColumn("見積金額", format="¥%d", disabled=True),
        "荒利率": st.column_config.NumberColumn("率", format="%.1f%%", disabled=True),
        
        # 管理用列（必要に応じて表示/非表示を調整）
        # ▼▼ 修正後: disabled=False (入力可能にする) ▼▼
        "sort_key": st.column_config.NumberColumn("SortID", disabled=False, format="%d", help="並び順を変えるにはここを書き換えて保存してください"),
        "部分項目": st.column_config.TextColumn("部分項目")
    }
    
    # 表示する列の順序
    display_cols = [
        '確認', '名称', '規格', '数量', '単位',
        'NET', '原単価', '掛率', '売単価', '見積金額', '荒利率', 
        '備考', '部分項目', 'sort_key'
    ]

    # データエディタの表示
    edited_df = st.data_editor(
        filtered_df[display_cols],
        column_config=column_config,
        use_container_width=True,
        height=600,
        num_rows="dynamic", # 行の追加・削除を許可
        key="playlist_editor"
    )
    
    return edited_df
