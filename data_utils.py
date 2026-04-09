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

# --- load_data 関数の修正部分 ---
def load_data(sheet_url: str, secrets: Dict) -> Tuple[Optional[pd.DataFrame], Optional[Dict]]:
    try:
        client = get_gspread_client(secrets)
        wb = client.open_by_url(sheet_url)
        sheet = wb.worksheet(SHEET_NAME)
        data = sheet.get_all_values()
        
        # Step 1: データ存在チェック（4行目以降のデータがない場合のエッジケース対応）
        if len(data) < 4: 
            return pd.DataFrame(columns=data[0]) if len(data) > 0 else None, None
            
        # Step 2: 読込範囲の変更（1行目をカラム名、4行目以降をデータとする）
        df = pd.DataFrame(data[3:], columns=data[0])

        # df = pd.DataFrame(data[3:], columns=data[0])
        # ↑既存のこの行の直下に、以下を追加します

        # Step 1: 文字列カラムのNaN排除と型固定 #
        text_cols = ['大項目', '中項目', '名称', '規格', '単位', '備考', 'sort_key']
        for col in text_cols:
            if col in df.columns:
                df[col] = df[col].fillna('').astype(str)
        
        info_sheet = wb.worksheet(INFO_SHEET_NAME)
        info_data = info_sheet.get_all_values()
        info_dict = {str(row[0]).strip(): str(row[1]).strip() for row in info_data if len(row) >= 2}
        if '確認' in df.columns:
            df['確認'] = df['確認'].apply(lambda x: True if str(x).upper() == 'TRUE' else False)
        return df, info_dict
    except Exception as e:
        print(f"Error: {e}")
        return None, None


# --- save_data 関数の修正部分 ---
def save_data(sheet_url: str, secrets: Dict, df: pd.DataFrame) -> bool:
    try:
        client = get_gspread_client(secrets)
        wb = client.open_by_url(sheet_url)
        sheet = wb.worksheet(SHEET_NAME)
        
        save_df = df.copy().fillna('')
        
        if '確認' in save_df.columns:
            save_df['確認'] = save_df['確認'].apply(lambda x: 'TRUE' if x is True else 'FALSE')
        
        cols = save_df.columns.tolist()
        col_map = {name: _col_index_to_letter(i) for i, name in enumerate(cols)}
        
        req_cols = ['数量', '原単価', '掛率', '売単価', '見積金額', '実行金額', '荒利金額', '荒利率']
        if all(c in col_map for c in req_cols):
            for idx in range(len(save_df)):
                # Step 3: 行番号のオフセットを修正（4行目から開始）
                row_num = idx + 4 
                
                c_qty = col_map['数量']
                c_cost = col_map['原単価']
                c_rate = col_map['掛率']
                c_sell = col_map['売単価']
                c_est_amt = col_map['見積金額']
                c_exec_amt = col_map['実行金額']
                c_profit_amt = col_map['荒利金額']
                
                save_df.at[idx, '売単価'] = f'=INT({c_cost}{row_num} * {c_rate}{row_num})'
                save_df.at[idx, '実行金額'] = f'=INT({c_qty}{row_num} * {c_cost}{row_num})'
                save_df.at[idx, '見積金額'] = f'=INT({c_qty}{row_num} * {c_sell}{row_num})'
                save_df.at[idx, '荒利金額'] = f'={c_est_amt}{row_num} - {c_exec_amt}{row_num}'
                save_df.at[idx, '荒利率'] = f'=IFERROR({c_profit_amt}{row_num} / {c_est_amt}{row_num}, 0)'

        # 注意: ここではヘッダー行を含めず、データ値のみをリスト化する
        data_to_write = save_df.values.tolist()
        
        # Step 4: 2,3行目の関数を保護するため、シート全体クリアを廃止。4行目以降のみをクリア
        sheet.batch_clear(['A4:ZZ']) 
        
        # Step 5: A4セルを起点にデータを上書き
        if data_to_write:
            sheet.update(
                range_name='A4', 
                values=data_to_write, 
                value_input_option='USER_ENTERED'
            )
        
        return True
    except Exception as e:
        print(f"Save Error: {e}")
        return False
