#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import csv
import re
import os
import argparse
from datetime import datetime

def generalize_description(description, account_type, creditor_name=None, debtor_name=None):
    """
    摘要を勘定科目に基づいて汎用的な表現に変換する関数
    
    Parameters:
        description (str): 元の摘要文
        account_type (str): 勘定科目
        creditor_name (str): 貸方取引先名
        debtor_name (str): 借方取引先名
    
    Returns:
        str: 汎用化された摘要文
    """
    # インボイス番号を削除
    description = re.sub(r'\s*\[インボイス:.*?\]', '', description)
    
    # 「」や()などの記号を削除
    description = re.sub(r'「|」|\(|\)', '', description)
    
    # Creative Cの場合はソフトウェア使用料に変換
    if "Creative C" in description or "creative c" in description.lower():
        return "ソフトウェア使用料"
    
    # 証紙切手引受は郵便料金に変換
    if "証紙切手引受" in description or "切手" in description or "郵便" in description:
        return "郵便料金"
    
    # ヨドバシカメラが取引先の場合は全て書籍代に変換
    if (creditor_name and "ヨドバシ" in creditor_name) or (debtor_name and "ヨドバシ" in debtor_name):
        return "書籍代"
    
    # AIツール関連の摘要をAI使用料に変換
    ai_tools = ["Claude", "ChatGPT", "GitHub", "OpenAI", "AI"]
    for tool in ai_tools:
        if tool.lower() in description.lower():
            return "AI使用料"
    
    # 通信費関連の摘要を通信費に変換
    if description.lower().startswith("home wifi") or "wifi" in description.lower() or "インターネット" in description:
        return "通信費"
    
    # 交通費関連の摘要を適切に変換
    # JR、乗車券、特急券などの電車関連キーワードを拡充
    train_keywords = ["JR東車券", "新幹線", "特急", "JR乗車券", "乗車券類", "JR", "乗車券", "電車", "スイカ", "SUICA", "PASMO", "パスモ", "ICカード"]
    for keyword in train_keywords:
        if keyword in description:
            return "電車代・特急券代"
    
    if description.startswith("タクシー") or "タクシー" in description:
        return "タクシー代"
    
    # 勘定科目別の処理
    if account_type == "外注費":
        if "質問・アンケート" in description:
            # クラウドワークスが取引先の場合
            if (creditor_name and "クラウドワークス" in creditor_name) or (debtor_name and "クラウドワークス" in debtor_name):
                return "外注アンケート調査費 クラウドワークス"
            return "外注アンケート調査費"
        else:
            return "外注費"
    
    elif account_type == "新聞図書費":
        # 書籍名を抽出し、「書籍購入費」に変換
        return "書籍購入費"
    
    elif account_type == "消耗品費":
        return "消耗品費"
    
    elif account_type == "会議費":
        if "カフェ" in description or "食事" in description or "飲食" in description:
            return "会議用飲食費"
        else:
            return "会議費"
    
    elif account_type == "接待交際費":
        # 接待交際費は「接待飲食費」か「接待贈答費」のみに限定
        if "飲食" in description or "食事" in description or "カラオケ" in description:
            return "接待飲食費"
        elif "スイーツ" in description or "ショコラ" in description or "贈答" in description or "ギフト" in description:
            return "接待贈答費"
        else:
            # その他の接待交際費は飲食費として扱う
            return "接待飲食費"
    
    # 旅費交通費の勘定科目も追加
    elif account_type == "旅費交通費":
        if "タクシー" in description:
            return "タクシー代"
        else:
            # すべての旅費交通費を「電車代・特急券代」に変換（デフォルト）
            return "電車代・特急券代"
    
    # その他の勘定科目はそのまま返す
    return description

def process_csv(input_file, output_file):
    """
    CSVファイルを読み込み、摘要欄を汎用的な表現に変換して新しいCSVに書き出す
    
    Parameters:
        input_file (str): 入力CSVファイルのパス
        output_file (str): 出力CSVファイルのパス
    """
    try:
        with open(input_file, 'r', encoding='utf-8') as f_in, \
             open(output_file, 'w', encoding='utf-8', newline='') as f_out:
            
            reader = csv.reader(f_in, quotechar='"')
            writer = csv.writer(f_out, quotechar='"', quoting=csv.QUOTE_ALL)
            
            # ヘッダーの読み込みと書き込み
            header = next(reader)
            writer.writerow(header)
            
            # データ行の処理
            for row in reader:
                if len(row) > 26:  # 必要な列数があることを確認（25,26列目は取引先名）
                    # 勘定科目と摘要を取得
                    account_type = row[4]  # 借方勘定科目
                    description = row[16]  # 摘要
                    debtor_name = row[25] if len(row) > 25 else ""  # 借方取引先名
                    creditor_name = row[26] if len(row) > 26 else ""  # 貸方取引先名
                    
                    # 摘要を汎用的な表現に変換
                    generalized_description = generalize_description(description, account_type, creditor_name, debtor_name)
                    
                    # 変換した摘要を設定
                    row[16] = generalized_description
                
                # 処理した行を書き込み
                writer.writerow(row)
        
        print(f"処理が完了しました: {output_file}")
        return True
    
    except Exception as e:
        print(f"エラーが発生しました: {str(e)}")
        return False

def main():
    parser = argparse.ArgumentParser(description='複式簿記CSVの摘要を汎用的な表現に変換するスクリプト')
    parser.add_argument('input_file', help='入力CSVファイルパス')
    parser.add_argument('-o', '--output', help='出力CSVファイルパス（指定がない場合は自動生成）')
    
    args = parser.parse_args()
    
    input_file = args.input_file
    
    if args.output:
        output_file = args.output
    else:
        # 出力ファイル名を自動生成
        basename = os.path.basename(input_file)
        name, ext = os.path.splitext(basename)
        timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
        output_file = f"{name}_generalized_{timestamp}{ext}"
    
    process_csv(input_file, output_file)

if __name__ == "__main__":
    main() 