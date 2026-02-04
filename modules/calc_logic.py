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
    # 計算に必要な列を数値型に変換
    target_cols = ['数量', '原単価', '掛率', 'NET', 'sort_key']
    for col in target_cols:
        if col in df.columns:
            df[col] = df[col].apply(parse_amount)

    # 計算ロジック (端数は切り捨てて整数にする想定)
    # 売単価 = 原単価 × 掛率
    df['売単価'] = (df['原単価'] * df['掛率']).astype(int)
    
    # 見積金額 = 数量 × 売単価
    df['見積金額'] = (df['数量'] * df['売単価']).astype(int)
    
    # 実行金額 = 数量 × 原単価
    df['実行金額'] = (df['数量'] * df['原単価']).astype(int)
    
    # 荒利金額 = 見積金額 - 実行金額
    df['荒利金額'] = df['見積金額'] - df['実行金額']
    
    # 荒利率 = 荒利金額 ÷ 見積金額 (0除算を回避)
    df['(自)荒利率'] = df.apply(
        lambda x: x['荒利金額'] / x['見積金額'] if x['見積金額'] != 0 else 0.0, 
        axis=1
    )
    
    return df

# --- 3. ソートキー管理 (リナンバリング) ---
def renumber_sort_keys(df):
    """
    【保存時用】
    現在の並び順（sort_key順）でデータを整列し、
    100, 200, 300... ときれいな連番を振り直す。
    これにより、桁あふれを防ぐ。
    """
    # まず現在のキーで確実にソート
    # (大項目などの階層も含めてソートしても良いが、今回はsort_keyを絶対視する)
    if 'sort_key' in df.columns:
        df = df.sort_values(by=['sort_key'])
    
    # インデックスをリセット
    df = df.reset_index(drop=True)
    
    # 新しいキー: 100, 200, 300...
    # (indexは0始まりなので、+1して100倍する)
    df['sort_key'] = (df.index + 1) * 100
    
    return df

def get_insert_key(prev_key, next_key):
    """
    【割り込み挿入用】
    2つのキーの間に挿入するための中間値を計算する。
    例: 100と200の間 -> 150
    """
    return (prev_key + next_key) / 2
