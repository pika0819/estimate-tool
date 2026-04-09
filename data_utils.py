# data_utils.py (修正版)

def load_data(sheet_url: str, secrets: Dict) -> Tuple[Optional[pd.DataFrame], Optional[Dict]]:
    try:
        # Step 1: スプレッドシートへ直接アクセス（BigQuery不要）
        client = get_gspread_client(secrets)
        wb = client.open_by_url(sheet_url)
        
        # 見積明細の読み込み
        sheet = wb.worksheet(SHEET_NAME)
        data = sheet.get_all_values()
        
        # データが4行目（ヘッダー1行+空2行+データ開始）に満たない場合
        if len(data) < 4:
            df = pd.DataFrame(columns=data[0] if len(data) > 0 else [])
        else:
            df = pd.DataFrame(data[3:], columns=data[0])

        # Step 2: 物理的制約（型不整合）の強制排除
        # 読込直後にすべてのテキストカラムを str 型に固定
        text_cols = ['大項目', '中項目', '名称', '規格', '単位', '備考', 'sort_key']
        for col in text_cols:
            if col in df.columns:
                df[col] = df[col].fillna('').astype(str)

        # Step 3: 現場情報の読み込み
        info_sheet = wb.worksheet(INFO_SHEET_NAME)
        info_data = info_sheet.get_all_values()
        info_dict = {str(row[0]).strip(): str(row[1]).strip() for row in info_data if len(row) >= 2}

        return df, info_dict

    except Exception as e:
        # エラー時は結論のみを表示し、余計なスタックトレースを隠す
        print(f"接続エラー（シート直接参照）: {e}")
        return None, None
