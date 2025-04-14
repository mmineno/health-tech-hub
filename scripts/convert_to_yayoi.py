import csv
import re
import jaconv

def convert_bank_statement_to_yayoi(input_file, output_file):
    """
    通帳データから弥生会計形式へ変換する関数
    
    Args:
        input_file (str): 通帳データCSVファイルのパス
        output_file (str): 出力する弥生会計形式CSVファイルのパス
    """
    # 出力ヘッダー
    headers = [
        "識別フラグ", "伝票No", "決算", "取引日付", "借方勘定科目", "借方補助科目", "借方部門", 
        "借方税区分", "借方金額", "借方税金額", "貸方勘定科目", "貸方補助科目", "貸方部門", 
        "貸方税区分", "貸方金額", "貸方税金額", "摘要", "番号", "期日", "タイプ", "生成元", 
        "仕訳メモ", "付箋1", "付箋2", "調整", "借方取引先名", "貸方取引先名"
    ]
    
    # 空白のレコードを初期化
    default_record = {header: "" for header in headers}
    default_record["識別フラグ"] = "2000"
    default_record["借方税金額"] = ""
    default_record["貸方税金額"] = ""
    
    # 特定の取引先名の変換ルール
    company_name_mapping = {
        "ゲノメデイア(カ": "genomedia株式会社",
        "株式会社ミユ-プ": "株式会社 miup",
        "株式会社ミユープ": "株式会社 miup"
    }
    
    # 取引データを格納するリスト
    output_records = []
    
    # 通帳データを読み込む
    with open(input_file, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            # ヘッダー行またはデータがない行をスキップ
            if not row.get('年月日') or row['年月日'] == '年月日':
                continue
            
            # 新しいレコードを作成
            record = default_record.copy()
            
            # 基本情報を設定
            record["取引日付"] = row['年月日']  # スラッシュをそのまま保持
            
            # 取引内容から取引先名を抽出・整形
            取引先 = row.get('お取り扱い内容', '')
            # 半角カナを全角に変換
            取引先 = jaconv.h2z(取引先, kana=True, digit=False, ascii=False)
            # 半角ハイフン(-) を全角長音記号(ー)に変換
            取引先 = 取引先.replace('-', 'ー')
            # ｶ) を株式会社に変換
            取引先 = re.sub(r'カ\)', '株式会社', 取引先)
            
            # 「カード　セブンBK0RNP」のような文字列を「カード」だけに簡素化
            取引先 = re.sub(r'カード\s+.*', 'カード', 取引先)
            
            # 特定の会社名の変換
            for old_name, new_name in company_name_mapping.items():
                if old_name in 取引先:
                    取引先 = 取引先.replace(old_name, new_name)
            
            # 摘要を設定
            record["摘要"] = 取引先
            
            # 金額の処理（カンマを削除）
            出金額 = row.get('お引出し', '').replace(',', '') or '0'
            入金額 = row.get('お預入れ', '').replace(',', '') or '0'
            
            # 出金の場合（借方に設定）
            if 出金額 != '0':
                record["借方勘定科目"] = row.get('ラベル', '')
                record["借方金額"] = 出金額
                record["貸方勘定科目"] = "普通預金"
                record["貸方金額"] = 出金額
                
                # 売掛金の場合の特別処理
                if record["借方勘定科目"] == "売掛金":
                    record["借方取引先名"] = ""
                    # 取引先名の設定
                    取引先名 = ""
                    if "genomedia株式会社" in 取引先:
                        取引先名 = "genomedia株式会社"
                    elif "株式会社miup" in 取引先:
                        取引先名 = "株式会社miup"
                    else:
                        取引先名 = 取引先
                    
                    record["貸方取引先名"] = 取引先名
                    record["貸方補助科目"] = 取引先名
                else:
                    record["借方取引先名"] = 取引先
                    record["貸方取引先名"] = 取引先
            
            # 入金の場合（貸方に設定）
            else:
                record["貸方勘定科目"] = row.get('ラベル', '')
                record["貸方金額"] = 入金額
                record["借方勘定科目"] = "普通預金"
                record["借方金額"] = 入金額
                
                # 売掛金の場合の特別処理
                if record["貸方勘定科目"] == "売掛金":
                    record["借方取引先名"] = ""
                    # 取引先名の設定
                    取引先名 = ""
                    if "genomedia株式会社" in 取引先:
                        取引先名 = "genomedia株式会社"
                    elif "株式会社miup" in 取引先:
                        取引先名 = "株式会社miup"
                    else:
                        取引先名 = 取引先
                    
                    record["貸方取引先名"] = 取引先名
                    record["貸方補助科目"] = 取引先名
                else:
                    record["借方取引先名"] = 取引先
                    record["貸方取引先名"] = 取引先
            
            # 処理済みのレコードをリストに追加
            output_records.append(record)
    
    # 弥生会計形式でCSVファイルを書き出す
    with open(output_file, 'w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=headers, quoting=csv.QUOTE_ALL)
        writer.writeheader()
        writer.writerows(output_records)
    
    print(f"{len(output_records)}件の取引を{output_file}に変換しました。")

# 実行例
if __name__ == "__main__":
    convert_bank_statement_to_yayoi("2024-tsucho.csv", "yayoi_output_converted.csv") 