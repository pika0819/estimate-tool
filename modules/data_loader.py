import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import streamlit as st

# --- 共通: 認証クライアントの取得 ---
def get_gspread_client(secrets):
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    creds = ServiceAccountCredentials.from_json_keyfile_dict(secrets, scope)
    return gspread.authorize(creds)

# --- 1. マスタDB（基本情報）の読み込み ---
def load_master_db(secrets):
    """
    secrets.toml の master_sheet_url から
    「項目表」と「定価表」を読み込む
    """
    try:
        master_url = secrets["app_config"]["master_sheet_url"]
        client = get_gspread_client(secrets["gcp_service_account"])
        wb = client.open_by_url(master_url)
        
        # A. 項目表 (階層定義)
        sheet_def = wb.worksheet("項目表")
        data_def = sheet_def.get_all_values()
        # 1行目をヘッダーとしてDataFrame化
        df_items = pd.DataFrame(data_def[1:], columns=data_def[0])
        
        # B. 定価表 (単価マスタ)
        sheet_price = wb.worksheet("定価表")
        data_price = sheet_price.get_all_values()
        df_prices = pd.DataFrame(data_price[1:], columns=data_price[0])
        
        return df_items, df_prices

    except Exception as e:
        st.error(f"マスタDB接続エラー: {e}")
        return None, None

# --- 2. 案件DB（見積もり集計表）の読み込み ---
def load_project_db(secrets, project_url=None):
    """
    指定されたURLの案件シートを読み込む
    """
    try:
        # URLが指定されていなければSecretsのデフォルトを使う
        target_url = project_url if project_url else secrets["app_config"]["default_project_url"]
        
        client = get_gspread_client(secrets["gcp_service_account"])
        wb = client.open_by_url(target_url)
        
        # A. 見積り集計表
        sheet_est = wb.worksheet("見積り集計表")
        data_est = sheet_est.get_all_values()
        df_est = pd.DataFrame(data_est[1:], columns=data_est[0])
        
        # B. 現場情報
        sheet_info = wb.worksheet("現場情報")
        data_info = sheet_info.get_all_values()
        # 辞書形式に変換 {項目名: 内容}
        info_dict = {str(row[0]).strip(): str(row[1]).strip() for row in data_info if len(row) >= 2}
        
        # Boolean変換 ('TRUE'文字列をPythonのTrueに)
        if '確認' in df_est.columns:
            df_est['確認'] = df_est['確認'].apply(lambda x: True if str(x).upper() == 'TRUE' else False)
            
        return df_est, info_dict, target_url

    except Exception as e:
        st.error(f"案件DB接続エラー: {e}")
        return None, None, None

# --- 3. 案件DBへの保存 ---
def save_project_data(secrets, project_url, df):
    """
    案件DBの「見積り集計表」を上書き保存する
    """
    try:
        client = get_gspread_client(secrets["gcp_service_account"])
        wb = client.open_by_url(project_url)
        sheet = wb.worksheet("見積り集計表")
        
        save_df = df.copy()
        
        # Booleanを文字列に戻す
        if '確認' in save_df.columns:
            save_df['確認'] = save_df['確認'].apply(lambda x: 'TRUE' if x else 'FALSE')
        
        # ヘッダー込みで書き込み (clearしてからupdate)
        data_to_write = [save_df.columns.values.tolist()] + save_df.values.tolist()
        sheet.clear()
        sheet.update(range_name='A1', values=data_to_write)
        return True
    except Exception as e:
        st.error(f"保存エラー: {e}")
        return False

# --- 4. 定価表マスタへの追加 ---
def add_master_price_item(secrets, item_data):
    """
    基本情報の「定価表」シートに行を追加する
    item_data = [検索名称, 名称, 規格, 単位, 定価]
    """
    try:
        master_url = secrets["app_config"]["master_sheet_url"]
        client = get_gspread_client(secrets["gcp_service_account"])
        wb = client.open_by_url(master_url)
        sheet = wb.worksheet("定価表")
        
        # 末尾に追加
        sheet.append_row(item_data)
        return True
    except Exception as e:
        st.error(f"マスタ登録エラー: {e}")
        return False
