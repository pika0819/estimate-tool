import pandas as pd
import numpy as np
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from typing import Optional, Tuple, Dict, Any

# シート名などの定数設定
SHEET_NAME = "見積り集計表"
INFO_SHEET_NAME = "現場情報"

def parse_amount(val: Any) -> float:
    """金額文字列を数値に変換"""
    try:
        if pd.isna(val) or val == '': return 0.0
        return float(str(val).replace('¥', '').replace(',', ''))
    except (ValueError, TypeError):
        return 0.0

def calculate_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """データフレームの数値計算（単価×数量＝金額など）を一括で行う"""
    # 数値変換（エラー回避）
    num_cols = ['数量', '原単価', '掛率', 'NET']
    for col in num_cols:
        if col in df.columns:
            df[col] = df[col].apply(parse_amount)
    
    # 計算ロジック
    # 売単価 = 原単価 * 掛率 (整数丸め)
    df['売単価'] = (df['原単価'] * df['掛率']).astype(int)
    
    # 見積金額 = 数量 * 売単価
    df['見積金額'] = (df['数量'] * df['売単価']).astype(int)
    
    # 実行金額 = 数量 * 原単価
    df['実行金額'] = (df['数量'] * df['原単価']).astype(int)
    
    # 荒利金額 = 見積金額 - 実行金額
    df['荒利金額'] = df['見積金額'] - df['実行金額']
    
    # 荒利率 (0除算回避)
    df['(自)荒利率'] = df.apply(
        lambda x: x['荒利金額'] / x['見積金額'] if x['見積金額'] != 0 else 0, axis=1
    )
    
    return df

def get_gspread_client(secrets: Dict):
    """Google Sheets APIクライアントの取得"""
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    creds = ServiceAccountCredentials.from_json_keyfile_dict(secrets, scope)
    return gspread.authorize(creds)

def load_data(sheet_url: str, secrets: Dict) -> Tuple[Optional[pd.DataFrame], Optional[Dict]]:
    """データの読み込み（キャッシュせず、最新を取得）"""
    try:
        client = get_gspread_client(secrets)
        wb = client.open_by_url(sheet_url)
        
        # Main Sheet
        sheet = wb.worksheet(SHEET_NAME)
        data = sheet.get_all_values()
        # データが空の場合のハンドリング
        if len(data) < 2:
            return None, None

        df = pd.DataFrame(data[1:], columns=data[0])
        
        # Info Sheet
        info_sheet = wb.worksheet(INFO_SHEET_NAME)
        info_data = info_sheet.get_all_values()
        info_dict = {str(row[0]).strip(): str(row[1]).strip() for row in info_data if len(row) >= 2}
        
        # Boolean変換
        if '確認' in df.columns:
            df['確認'] = df['確認'].apply(lambda x: True if str(x).upper() == 'TRUE' else False)

        return df, info_dict
    except Exception as e:
        print(f"Error loading data: {e}") # ログ用
        return None, None

def save_data(sheet_url: str, secrets: Dict, df: pd.DataFrame) -> bool:
    """データの保存（全行書き換え）"""
    try:
        client = get_gspread_client(secrets)
        wb = client.open_by_url(sheet_url)
        sheet = wb.worksheet(SHEET_NAME)
        
        # 保存用にコピーを作成
        save_df = df.copy()
        
        # Booleanを文字列に戻す
        if '確認' in save_df.columns:
            save_df['確認'] = save_df['確認'].apply(lambda x: 'TRUE' if x else 'FALSE')
        
        # ヘッダーを含めて書き込み
        data_to_write = [save_df.columns.values.tolist()] + save_df.values.tolist()
        sheet.clear()
        sheet.update(range_name='A1', values=data_to_write)
        return True
    except Exception as e:
        print(f"Error saving data: {e}")
        return False
