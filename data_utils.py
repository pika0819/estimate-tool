import pandas as pd
import numpy as np
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from typing import Optional, Tuple, Dict, Any

# --- (既存の定数や関数はそのまま) ---
# SHEET_NAME, INFO_SHEET_NAME, parse_amount, calculate_dataframe, get_gspread_client, load_data
# これらは変更不要ですが、念のため全体の流れがわかるように記述します

SHEET_NAME = "見積り集計表"
INFO_SHEET_NAME = "現場情報"

def parse_amount(val: Any) -> float:
    try:
        if pd.isna(val) or val == '': return 0.0
        return float(str(val).replace('¥', '').replace(',', ''))
    except (ValueError, TypeError):
        return 0.0

def calculate_dataframe(df: pd.DataFrame, overhead_rates: Dict[str, float] = None) -> pd.DataFrame:
    # （前回の修正版と同じコードを使用してください）
    if overhead_rates is None: overhead_rates = {}
    num_cols = ['数量', '原単価', '掛率', 'NET']
    for col in num_cols:
        if col in df.columns: df[col] = df[col].apply(parse_amount)
    
    overhead_mask = df['大項目'] == '諸経費'
    
    # 通常行計算
    df.loc[~overhead_mask, '売単価'] = (df.loc[~overhead_mask, '原単価'] * df.loc[~overhead_mask, '掛率']).astype(int)
    df.loc[~overhead_mask, '見積金額'] = (df.loc[~overhead_mask, '数量'] * df.loc[~overhead_mask, '売単価']).astype(int)
    df.loc[~overhead_mask, '実行金額'] = (df.loc[~overhead_mask, '数量'] * df.loc[~overhead_mask, '原単価']).astype(int)

    base_total = df.loc[~overhead_mask, '見積金額'].sum()

    # 諸経費行計算
    for idx, row in df[overhead_mask].iterrows():
        key = str(row.get('sort_key', ''))
        rate = overhead_rates.get(key, 0.0)
        calc_price = int(base_total * (rate / 100))
        
        df.at[idx, '数量'] = 1
        df.at[idx, '単位'] = '式'
        df.at[idx, '原単価'] = calc_price
        df.at[idx, '掛率'] = 1.0
        df.at[idx, '売単価'] = int(calc_price * 1.0)
        df.at[idx, '見積金額'] = int(1 * calc_price * 1.0)
        df.at[idx, '実行金額'] = int(1 * calc_price)

    df['荒利金額'] = df['見積金額'] - df['実行金額']
    df['(自)荒利率'] = df.apply(lambda x: x['荒利金額'] / x['見積金額'] if x['見積金額'] != 0 else 0, axis=1)
    return df

def get_gspread_client(secrets: Dict):
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    creds = ServiceAccountCredentials.from_json_keyfile_dict(secrets, scope)
    return gspread.authorize(creds)

def load_data(sheet_url: str, secrets: Dict) -> Tuple[Optional[pd.DataFrame], Optional[Dict]]:
    # (変更なし)
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

# --- ★ここからが新しいsave_data ---

def _col_index_to_letter(n: int) -> str:
    """0始まりのインデックスをA, B, C... AA形式に変換"""
    string = ""
    n += 1 
    while n > 0:
        n, remainder = divmod(n - 1, 26)
        string = chr(65 + remainder) + string
    return string

def save_data(sheet_url: str, secrets: Dict, df: pd.DataFrame) -> bool:
    """
    データを保存する際、計算列（売単価など）には値を書き込まず、
    スプレッドシート用の数式（Formula）を書き込む。
    """
    try:
        client = get_gspread_client(secrets)
        wb = client.open_by_url(sheet_url)
        sheet = wb.worksheet(SHEET_NAME)
        
        save_df = df.copy()
        
        # Boolean変換
        if '確認' in save_df.columns:
            save_df['確認'] = save_df['確認'].apply(lambda x: 'TRUE' if x else 'FALSE')
        
        # --- 数式化のロジック ---
        # 列名と列番号(A,B,C...)のマッピングを作成
        cols = save_df.columns.tolist()
        col_map = {name: _col_index_to_letter(i) for i, name in enumerate(cols)}
        
        # 必要な列が存在するかチェック
        req_cols = ['数量', '原単価', '掛率', '売単価', '見積金額', '実行金額', '荒利金額', '(自)荒利率']
        if all(c in col_map for c in req_cols):
            # 行ごとにループして数式を埋め込む（データは2行目から始まるため、行番号は idx + 2）
            for idx in range(len(save_df)):
                row_num = idx + 2
                
                # 列記号を取得
                c_qty = col_map['数量']
                c_cost = col_map['原単価']
                c_rate = col_map['掛率']
                c_sell = col_map['売単価']
                c_est_amt = col_map['見積金額']
                c_exec_amt = col_map['実行金額']
                c_profit_amt = col_map['荒利金額']
                
                # 数式をセット (INT関数で丸め処理も再現)
                # 売単価 = 原単価 * 掛率
                save_df.at[idx, '売単価'] = f'=INT({c_cost}{row_num} * {c_rate}{row_num})'
                
                # 実行金額 = 数量 * 原単価
                save_df.at[idx, '実行金額'] = f'=INT({c_qty}{row_num} * {c_cost}{row_num})'
                
                # 見積金額 = 数量 * 売単価 (※ここで先程の売単価セルを参照)
                save_df.at[idx, '見積金額'] = f'=INT({c_qty}{row_num} * {c_sell}{row_num})'
                
                # 荒利金額 = 見積金額 - 実行金額
                save_df.at[idx, '荒利金額'] = f'={c_est_amt}{row_num} - {c_exec_amt}{row_num}'
                
                # 荒利率 = IFERROR(荒利 / 見積, 0)
                save_df.at[idx, '(自)荒利率'] = f'=IFERROR({c_profit_amt}{row_num} / {c_est_amt}{row_num}, 0)'

        # 書き込み用データ作成
        data_to_write = [save_df.columns.values.tolist()] + save_df.values.tolist()
        
        sheet.clear()
        # raw=False (default) なので、'=' で始まる文字列は自動的に数式として認識される
        sheet.update(range_name='A1', values=data_to_write)
        return True
    except Exception as e:
        print(f"Save Error: {e}")
        return False
