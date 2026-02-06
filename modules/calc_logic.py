import pandas as pd
import numpy as np

# --- 1. データ変換・クリーニング ---
def parse_amount(val):
    """
    '¥1,000' や '1,000' などの文字列を数値(float)に変換する。
    空欄やエラーの場合は 0.0 を返す。
    """
    try:
        if pd.isna(val) or str(val).strip() == '':
            return 0.0
        # 文字列にしてから、円マークとカンマを除去
        clean_str = str(val).replace('¥', '').replace(',', '').strip()
        return float(clean_str)
    except:
        return 0.0

# --- 2. 金額・利益の自動計算 ---
def calculate_dataframe(df):
    """
    DataFrame全体の金額計算を一括で行う。
    数量 × 単価 × 掛率 などを計算し、列を更新する。
    """
    # ★修正ポイント: sort_key を計算対象から外しました
    target_cols = ['数量', '原単価', '掛率', 'NET']
    
    for col in target_cols:
        if col in df.columns:
            df[col] = df[col].apply(parse_amount)

    # 計算ロジック (端数は切り捨てて整数にする想定)
    df['売単価'] = (df['原単価'] * df['掛率']).astype(int)
    df['見積金額'] = (df['数量'] * df['売単価']).astype(int)
    df['実行金額'] = (df['数量'] * df['原単価']).astype(int)
    df['荒利金額'] = df['見積金額'] - df['実行金額']
    
    df['荒利率'] = df.apply(
        lambda x: x['荒利金額'] / x['見積金額'] if x['見積金額'] != 0 else 0.0, 
        axis=1
    )
    
    # sort_key の数値化（エラーならNaNにする）
    if 'sort_key' in df.columns:
        df['sort_key'] = pd.to_numeric(df['sort_key'], errors='coerce')
    
    return df

# --- 3. ソートキー管理 (リナンバリング) ---
def renumber_sort_keys(df):
    """
    【保存時用】
    現在の並び順（sort_key順）でデータを整列し、
    100, 200, 300... ときれいな連番を振り直す。
    """
    if 'sort_key' in df.columns:
        df = df.sort_values(by=['sort_key'])
    
    df = df.reset_index(drop=True)
    df['sort_key'] = (df.index + 1) * 100
    return df

def get_insert_key(prev_key, next_key):
    return (prev_key + next_key) / 2
