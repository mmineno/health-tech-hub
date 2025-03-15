import csv
import os
import sys
import codecs
from datetime import datetime

# 一般的な会計科目のリスト
VALID_ACCOUNTS = {
    # 資産の部
    "現金": "資産",
    "小口現金": "資産",
    "普通預金": "資産",
    "当座預金": "資産",
    "定期預金": "資産",
    "売掛金": "資産",
    "未収金": "資産",
    "有価証券": "資産",
    "商品": "資産",
    "製品": "資産",
    "原材料": "資産",
    "仕掛品": "資産",
    "貯蔵品": "資産",
    "前払費用": "資産",
    "立替金": "資産",
    "仮払金": "資産",
    "短期貸付金": "資産",
    "建物": "資産",
    "建物付属設備": "資産",
    "構築物": "資産",
    "機械装置": "資産",
    "車両運搬具": "資産",
    "工具器具備品": "資産",
    "土地": "資産",
    "電話加入権": "資産",
    "ソフトウェア": "資産",
    "長期前払費用": "資産",
    "敷金": "資産",
    "保証金": "資産",
    "繰延資産": "資産",
    "クレジットカード": "資産",
    
    # 負債の部
    "買掛金": "負債",
    "未払金": "負債",
    "短期借入金": "負債",
    "前受金": "負債",
    "預り金": "負債",
    "仮受金": "負債",
    "未払費用": "負債",
    "未払法人税等": "負債",
    "未払消費税": "負債",
    "未払事業税": "負債",
    "賞与引当金": "負債",
    "長期借入金": "負債",
    "退職給付引当金": "負債",
    
    # 純資産の部
    "資本金": "純資産",
    "元入金": "純資産",
    "資本準備金": "純資産",
    "利益準備金": "純資産",
    "繰越利益剰余金": "純資産",
    "当期純利益": "純資産",
    
    # 収益の部
    "売上高": "収益",
    "製品売上高": "収益",
    "商品売上高": "収益",
    "サービス売上高": "収益",
    "雑収入": "収益",
    "受取利息": "収益",
    "受取配当金": "収益",
    "為替差益": "収益",
    "有価証券売却益": "収益",
    "固定資産売却益": "収益",
    
    # 費用の部
    "仕入高": "費用",
    "製品仕入高": "費用",
    "商品仕入高": "費用",
    "外注費": "費用",
    "給料賃金": "費用",
    "役員報酬": "費用",
    "アルバイト給与": "費用",
    "賞与": "費用",
    "退職金": "費用",
    "法定福利費": "費用",
    "福利厚生費": "費用",
    "雑給": "費用",
    "通勤費": "費用",
    "広告宣伝費": "費用",
    "荷造運賃": "費用",
    "販売促進費": "費用",
    "旅費交通費": "費用",
    "通信費": "費用",
    "交際費": "費用",
    "会議費": "費用",
    "接待交際費": "費用",
    "事務用品費": "費用",
    "消耗品費": "費用",
    "水道光熱費": "費用",
    "新聞図書費": "費用",
    "支払手数料": "費用",
    "支払報酬": "費用",
    "支払保険料": "費用",
    "修繕費": "費用",
    "保守料": "費用",
    "リース料": "費用",
    "地代家賃": "費用",
    "家賃": "費用",
    "管理費": "費用",
    "租税公課": "費用",
    "減価償却費": "費用",
    "貸倒引当金繰入": "費用",
    "雑費": "費用",
    "支払利息": "費用",
    "為替差損": "費用",
    "有価証券売却損": "費用",
    "固定資産売却損": "費用",
    "貸倒損失": "費用",
    "雑損失": "費用",
}

def validate_date(date_str):
    """日付形式を検証"""
    try:
        date_obj = datetime.strptime(date_str, '%Y/%m/%d')
        return True, date_obj.strftime('%Y/%m/%d')  # 正規化された日付を返す
    except ValueError:
        return False, None

def validate_amount(amount_str):
    """金額が数値かどうかを検証"""
    try:
        amount = int(amount_str)
        return amount >= 0  # 負の値は無効とする
    except ValueError:
        return False

def convert_csv(input_file, output_file):
    """CSVを変換する関数"""
    try:
        # 入力CSVを読み込み
        with codecs.open(input_file, 'r', 'utf-8') as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        
        # 出力CSVのヘッダ（やよいの青色申告形式）
        header = ["識別フラグ", "伝票No", "決算", "取引日付", "借方勘定科目", "借方補助科目", "借方部門", 
                 "借方税区分", "借方金額", "借方税金額", "貸方勘定科目", "貸方補助科目", "貸方部門", 
                 "貸方税区分", "貸方金額", "貸方税金額", "摘要", "番号", "期日", "タイプ", "生成元", 
                 "仕訳メモ", "付箋1", "付箋2", "調整", "借方取引先名", "貸方取引先名"]
        
        # 出力データの準備
        output_rows = []
        error_count = 0
        
        for i, row in enumerate(rows, 1):
            # 「対象外」列が空白でない場合はスキップ
            if row.get("対象外", "").strip():
                continue
            
            # 入力データの検証
            if not row.get("発生日", "").strip():
                print(f"エラー（行 {i}）: 発生日が空です。")
                error_count += 1
                continue
                
            is_valid_date, normalized_date = validate_date(row["発生日"])
            if not is_valid_date:
                print(f"エラー（行 {i}）: 発生日の形式が無効です。YYYY/MM/DD形式で指定してください。")
                error_count += 1
                continue
                
            if not row.get("勘定科目", "").strip():
                print(f"エラー（行 {i}）: 勘定科目が空です。")
                error_count += 1
                continue
                
            account = row["勘定科目"].strip()
            if account not in VALID_ACCOUNTS:
                print(f"エラー（行 {i}）: 未知の勘定科目 '{account}' が見つかりました。")
                error_count += 1
                continue
                
            if not row.get("税込金額", "").strip():
                print(f"エラー（行 {i}）: 税込金額が空です。")
                error_count += 1
                continue
                
            if not validate_amount(row["税込金額"]):
                print(f"エラー（行 {i}）: 税込金額が無効です。")
                error_count += 1
                continue
            
            # 新しい行の作成（やよいの青色申告形式）
            new_row = {}
            
            # 基本データの設定
            new_row["識別フラグ"] = "2000"  # 1行の仕訳データ
            new_row["伝票No"] = ""
            new_row["決算"] = ""
            new_row["取引日付"] = normalized_date
            
            # 勘定科目の種類を確認
            account_type = VALID_ACCOUNTS[account]
            
            # 税区分の設定（シンプルにしています）
            # 実際の税区分は必要に応じて調整してください
            tax_category = ""
            
            # 費用科目は借方、収益は貸方として処理
            if account_type == "費用":
                # 費用は借方
                new_row["借方勘定科目"] = account
                new_row["借方補助科目"] = ""
                new_row["借方部門"] = ""
                new_row["借方税区分"] = tax_category
                new_row["借方金額"] = row["税込金額"]
                new_row["借方税金額"] = row.get("消費税額", "")
                
                # 貸方は現金
                new_row["貸方勘定科目"] = "現金"
                new_row["貸方補助科目"] = ""
                new_row["貸方部門"] = ""
                new_row["貸方税区分"] = ""
                new_row["貸方金額"] = row["税込金額"]
                new_row["貸方税金額"] = ""
            elif account_type == "収益":
                # 収益は貸方
                new_row["借方勘定科目"] = "現金"
                new_row["借方補助科目"] = ""
                new_row["借方部門"] = ""
                new_row["借方税区分"] = ""
                new_row["借方金額"] = row["税込金額"]
                new_row["借方税金額"] = ""
                
                new_row["貸方勘定科目"] = account
                new_row["貸方補助科目"] = ""
                new_row["貸方部門"] = ""
                new_row["貸方税区分"] = tax_category
                new_row["貸方金額"] = row["税込金額"]
                new_row["貸方税金額"] = row.get("消費税額", "")
            else:
                # その他の場合は借方に該当科目、貸方に現金
                new_row["借方勘定科目"] = account
                new_row["借方補助科目"] = ""
                new_row["借方部門"] = ""
                new_row["借方税区分"] = tax_category
                new_row["借方金額"] = row["税込金額"]
                new_row["借方税金額"] = row.get("消費税額", "")
                
                new_row["貸方勘定科目"] = "現金"
                new_row["貸方補助科目"] = ""
                new_row["貸方部門"] = ""
                new_row["貸方税区分"] = ""
                new_row["貸方金額"] = row["税込金額"]
                new_row["貸方税金額"] = ""
            
            # その他の項目
            摘要 = row.get("摘要", "")
            
            # インボイス情報がある場合は摘要に追加
            if "インボイス登録番号" in row and row["インボイス登録番号"].strip() and row["インボイス登録番号"].lower() != "なし":
                invoice_num = row["インボイス登録番号"]
                
                # インボイス番号が短すぎる場合（例：「T」だけ）は追加しない
                if len(invoice_num) <= 1:
                    new_row["摘要"] = 摘要[:30]  # 30文字制限
                else:
                    invoice_text = f"[インボイス:{invoice_num}]"
                    
                    # インボイス情報を含めた長さが30文字を超える場合は摘要を切り詰め
                    # ただし、摘要が極端に短くならないようにバランスを取る
                    if len(摘要) + len(invoice_text) + 1 > 30:  # +1はスペース分
                        # 摘要とインボイス情報の両方が見えるようにバランスよく分配
                        # 摘要に最低10文字は確保する
                        max_desc_len = max(10, 30 - len(invoice_text) - 1)
                        摘要 = 摘要[:max_desc_len]
                    
                    摘要 = f"{摘要} {invoice_text}" if 摘要 else invoice_text
                    new_row["摘要"] = 摘要[:30]  # 30文字制限
            else:
                new_row["摘要"] = 摘要[:30]  # 30文字制限
            
            new_row["番号"] = ""
            new_row["期日"] = ""
            new_row["タイプ"] = ""
            new_row["生成元"] = ""
            new_row["仕訳メモ"] = ""
            new_row["付箋1"] = "0"  # 指定なし
            new_row["付箋2"] = ""
            new_row["調整"] = ""
            
            # 取引先名を15文字以内に制限
            取引先名 = row.get("取引先", "")[:15]  # 15文字制限
            new_row["借方取引先名"] = 取引先名
            new_row["貸方取引先名"] = 取引先名
            
            output_rows.append(new_row)
        
        if error_count > 0:
            print(f"合計 {error_count} 件のエラーが見つかりました。修正してから再試行してください。")
            return False
        
        if not output_rows:
            print("警告: 変換可能なデータがありませんでした。")
            return False
        
        # 出力CSVの書き込み
        with codecs.open(output_file, 'w', 'utf-8', errors='replace') as f:
            writer = csv.DictWriter(f, fieldnames=header, quoting=csv.QUOTE_ALL)
            writer.writeheader()
            writer.writerows(output_rows)
        
        print(f"変換が完了しました。出力ファイル: {output_file}")
        print(f"変換された行数: {len(output_rows)}")
        return True
    
    except Exception as e:
        print(f"エラー: {str(e)}")
        return False

def main():
    """メイン関数"""
    if len(sys.argv) != 3:
        print("使用方法: python convert_csv.py 入力ファイル.csv 出力ファイル.csv")
        return
    
    input_file = sys.argv[1]
    output_file = sys.argv[2]
    
    if not os.path.exists(input_file):
        print(f"エラー: 入力ファイル '{input_file}' が見つかりません。")
        return
    
    if convert_csv(input_file, output_file):
        print("変換が正常に完了しました。")
    else:
        print("変換に失敗しました。")

if __name__ == "__main__":
    main()