import pandas as pd
import numpy as np
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from typing import Optional, Tuple, Dict, Any

# シート名定数
SHEET_NAME = "見積り集計表"
INFO_SHEET_NAME = "現場情報"

def parse_amount(val: Any) -> float:
    try:
        if pd.isna(val) or val == '': return 0.0
        return float(str(val).replace('¥', '').replace(',', ''))
    except (ValueError, TypeError):
        return 0.0

# ★ここを修正しました（引数を追加）
def calculate_dataframe(df: pd.DataFrame, overhead_rates: Dict[str, float] = None) -> pd.DataFrame:
    """
    データフレームの数値計算を行う。
    overhead_rates: {sort_key: rate(%)} の辞書を受け取り、該当行の原単価を自動計算する。
    """
    if overhead_rates is None:
        overhead_rates = {}

    # 1. 数値変換
    num_cols = ['数量', '原単価', '掛率', 'NET']
    for col in num_cols:
        if col in df.columns:
            df[col] = df[col].apply(parse_amount)
    
    # 2. 「諸経費」以外の通常項目の計算
    overhead_mask = df['大項目'] == '諸経費'
    
    # 通常行の計算
    df.loc[~overhead_mask, '売単価'] = (df.loc[~overhead_mask, '原単価'] * df.loc[~overhead_mask, '掛率']).astype(int)
    df.loc[~overhead_mask, '見積金額'] = (df.loc[~overhead_mask, '数量'] * df.loc[~overhead_mask, '売単価']).astype(int)
    df.loc[~overhead_mask, '実行金額'] = (df.loc[~overhead_mask, '数量'] * df.loc[~overhead_mask, '原単価']).astype(int)

    # 3. 諸経費の対象となる「工事価格」（諸経費以外の見積金額合計）を算出
    base_total = df.loc[~overhead_mask, '見積金額'].sum()

    # 4. 諸経費行の計算
    for idx, row in df[overhead_mask].iterrows():
        key = str(row.get('sort_key', ''))
        
        # 設定されたレートがあれば計算、なければ0%
        rate = overhead_rates.get(key, 0.0)
        
        # 計算: 原単価 = 対象額 * 率
        calc_price = int(base_total * (rate / 100))
        
        # 値の更新
        df.at[idx, '数量'] = 1
        df.at[idx, '単位'] = '式'
        df.at[idx, '原単価'] = calc_price
        df.at[idx, '掛率'] = 1.0
        df.at[idx, '売単価'] = int(calc_price * 1.0)
        df.at[idx, '見積金額'] = int(1 * calc_price * 1.0)
        df.at[idx, '実行金額'] = int(1 * calc_price)

    # 5. 粗利計算
    df['荒利金額'] = df['見積金額'] - df['実行金額']
    df['(自)荒利率'] = df.apply(
        lambda x: x['荒利金額'] / x['見積金額'] if x['見積金額'] != 0 else 0, axis=1
    )
    
    return df

def get_gspread_client(secrets: Dict):
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    creds = ServiceAccountCredentials.from_json_keyfile_dict(secrets, scope)
    return gspread.authorize(creds)

def load_data(sheet_url: str, secrets: Dict) -> Tuple[Optional[pd.DataFrame], Optional[Dict]]:
    try:
        client = get_gspread_client(secrets)
        wb = client.open_by_url(sheet_url)
        sheet = wb.worksheet(SHEET_NAME)
        data = sheet.get_all_values()
        if len(data) < 2: return None, None
        df = pd.DataFrame(data[1:], columns=data[0])
        info_sheet = wb.worksheet(INFO_SHEET_NAME)
        info_data = info_sheet.get_all_values()
        info_dict = {str(row[0]).strip(): str(row[1]).strip() for row in info_data if len(row) >= 2}
        if '確認' in df.columns:
            df['確認'] = df['確認'].apply(lambda x: True if str(x).upper() == 'TRUE' else False)
        return df, info_dict
    except Exception as e:
        print(f"Error: {e}")
        return None, None

def save_data(sheet_url: str, secrets: Dict, df: pd.DataFrame) -> bool:
    try:
        client = get_gspread_client(secrets)
        wb = client.open_by_url(sheet_url)
        sheet = wb.worksheet(SHEET_NAME)
        save_df = df.copy()
        if '確認' in save_df.columns:
            save_df['確認'] = save_df['確認'].apply(lambda x: 'TRUE' if x else 'FALSE')
        data_to_write = [save_df.columns.values.tolist()] + save_df.values.tolist()
        sheet.clear()
        sheet.update(range_name='A1', values=data_to_write)
        return True
    except Exception as e:
        return False
