#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import csv
import shutil
import argparse
import sys

def parse_arguments():
    parser = argparse.ArgumentParser(description='カード利用の有無に基づいてファイルを振り分けるスクリプト')
    parser.add_argument('csv_file', help='カード紐付け情報が記載されたCSVファイル')
    parser.add_argument('source_dir', help='振り分け対象の領収書が格納されているディレクトリ')
    return parser.parse_args()

def read_card_data(csv_file):
    """
    CSVファイルから「ファイル名」と「カード利用」の列を読み込む
    """
    card_data = {}
    try:
        with open(csv_file, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                filename = row.get('ファイル名', '')
                card_usage = row.get('カード利用', '')
                if filename:
                    card_data[filename] = card_usage
    except Exception as e:
        print(f"CSV読み込みエラー: {e}", file=sys.stderr)
        sys.exit(1)
    
    return card_data

def create_output_directories():
    """
    出力用のディレクトリを作成
    """
    os.makedirs('結果_カード利用あり', exist_ok=True)
    os.makedirs('結果_カード利用なし', exist_ok=True)
    print('出力ディレクトリを作成しました：')
    print('- 結果_カード利用あり')
    print('- 結果_カード利用なし')

def sort_files(source_dir, card_data):
    """
    ファイルをカード利用の有無に基づいて振り分ける
    """
    card_files = 0
    non_card_files = 0
    missing_files = 0
    
    try:
        file_list = os.listdir(source_dir)
        
        for filename in file_list:
            source_path = os.path.join(source_dir, filename)
            
            # ディレクトリの場合はスキップ
            if os.path.isdir(source_path):
                continue
                
            if filename in card_data:
                # カード利用の有無を確認
                if card_data[filename]:
                    dest_dir = '結果_カード利用あり'
                    card_files += 1
                else:
                    dest_dir = '結果_カード利用なし'
                    non_card_files += 1
                
                # ファイルをコピー
                dest_path = os.path.join(dest_dir, filename)
                shutil.copy2(source_path, dest_path)
            else:
                print(f"警告: CSVにファイル '{filename}' の情報がありません", file=sys.stderr)
                missing_files += 1
    
    except Exception as e:
        print(f"ファイル処理エラー: {e}", file=sys.stderr)
        sys.exit(1)
    
    return card_files, non_card_files, missing_files

def main():
    # コマンドライン引数の解析
    args = parse_arguments()
    
    print(f"CSVファイル: {args.csv_file}")
    print(f"領収書ディレクトリ: {args.source_dir}")
    
    # CSVからカード情報を読み込む
    card_data = read_card_data(args.csv_file)
    print(f"{len(card_data)}件のファイル情報を読み込みました")
    
    # 出力ディレクトリの作成
    create_output_directories()
    
    # ファイルの振り分け
    card_files, non_card_files, missing_files = sort_files(args.source_dir, card_data)
    
    # 結果の表示
    print("\n処理結果:")
    print(f"- カード利用あり: {card_files}ファイル")
    print(f"- カード利用なし: {non_card_files}ファイル")
    print(f"- CSVに情報なし: {missing_files}ファイル")
    print("\n処理が完了しました")

if __name__ == "__main__":
    main() 