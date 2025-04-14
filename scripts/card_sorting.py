#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import csv
import shutil
import argparse
import sys
from datetime import datetime

def parse_arguments():
    parser = argparse.ArgumentParser(description='カード利用の有無と発生日に基づいてファイルを振り分けるスクリプト')
    parser.add_argument('csv_file', help='カード紐付け情報が記載されたCSVファイル')
    parser.add_argument('source_dir', help='振り分け対象の領収書が格納されているディレクトリ')
    return parser.parse_args()

def read_card_data(csv_file):
    """
    CSVファイルから「ファイル名」と「カード利用」と「発生日」の列を読み込む
    """
    card_data = {}
    try:
        with open(csv_file, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                filename = row.get('ファイル名', '')
                card_usage = row.get('カード利用', '')
                issue_date = row.get('発生日', '')
                if filename:
                    card_data[filename] = {
                        'card_usage': card_usage,
                        'issue_date': issue_date
                    }
    except Exception as e:
        print(f"CSV読み込みエラー: {e}", file=sys.stderr)
        sys.exit(1)
    
    return card_data

def get_month_from_date(date_str):
    """
    日付文字列から月を抽出する
    """
    try:
        # 日付フォーマットに合わせて適宜変更してください
        # 例: 2023/01/15 や 2023-01-15 など
        if '/' in date_str:
            date_obj = datetime.strptime(date_str, '%Y/%m/%d')
        elif '-' in date_str:
            date_obj = datetime.strptime(date_str, '%Y-%m-%d')
        else:
            # フォーマットが不明な場合は空文字を返す
            return ''
        
        return date_obj.month
    except Exception:
        # 日付の解析に失敗した場合は空文字を返す
        return ''

def create_output_directories(months):
    """
    月ごとの出力用ディレクトリを作成
    """
    created_dirs = []
    
    for month in months:
        if month:  # 月の情報がある場合のみディレクトリを作成
            card_dir = f'結果_カード利用あり{month}月'
            non_card_dir = f'結果_カード利用なし{month}月'
            
            os.makedirs(card_dir, exist_ok=True)
            os.makedirs(non_card_dir, exist_ok=True)
            
            created_dirs.append((card_dir, non_card_dir))
    
    # 月の情報がない場合のためのデフォルトディレクトリ
    os.makedirs('結果_カード利用あり_月不明', exist_ok=True)
    os.makedirs('結果_カード利用なし_月不明', exist_ok=True)
    created_dirs.append(('結果_カード利用あり_月不明', '結果_カード利用なし_月不明'))
    
    print('出力ディレクトリを作成しました：')
    for card_dir, non_card_dir in created_dirs:
        print(f'- {card_dir}')
        print(f'- {non_card_dir}')

def sort_files(source_dir, card_data):
    """
    ファイルをカード利用の有無と月に基づいて振り分ける
    """
    card_files = 0
    non_card_files = 0
    missing_files = 0
    months = set()
    month_stats = {}
    
    # 先に存在する月を収集して、ディレクトリを作成
    for filename, data in card_data.items():
        issue_date = data.get('issue_date', '')
        month = get_month_from_date(issue_date)
        if month:
            months.add(month)
    
    create_output_directories(months)
    
    try:
        file_list = os.listdir(source_dir)
        
        for filename in file_list:
            source_path = os.path.join(source_dir, filename)
            
            # ディレクトリの場合はスキップ
            if os.path.isdir(source_path):
                continue
                
            if filename in card_data:
                # カード利用情報と発生月を取得
                card_usage = card_data[filename]['card_usage']
                issue_date = card_data[filename]['issue_date']
                month = get_month_from_date(issue_date)
                
                # 月の統計情報を記録
                month_key = f"{month}月" if month else "月不明"
                if month_key not in month_stats:
                    month_stats[month_key] = {'card': 0, 'non_card': 0}
                
                # カード利用の有無と月に基づいて振り分け先を決定
                if card_usage:
                    if month:
                        dest_dir = f'結果_カード利用あり{month}月'
                    else:
                        dest_dir = '結果_カード利用あり_月不明'
                    card_files += 1
                    month_stats[month_key]['card'] += 1
                else:
                    if month:
                        dest_dir = f'結果_カード利用なし{month}月'
                    else:
                        dest_dir = '結果_カード利用なし_月不明'
                    non_card_files += 1
                    month_stats[month_key]['non_card'] += 1
                
                # ファイルをコピー
                dest_path = os.path.join(dest_dir, filename)
                shutil.copy2(source_path, dest_path)
            else:
                print(f"警告: CSVにファイル '{filename}' の情報がありません", file=sys.stderr)
                missing_files += 1
    
    except Exception as e:
        print(f"ファイル処理エラー: {e}", file=sys.stderr)
        sys.exit(1)
    
    return card_files, non_card_files, missing_files, month_stats

def main():
    # コマンドライン引数の解析
    args = parse_arguments()
    
    print(f"CSVファイル: {args.csv_file}")
    print(f"領収書ディレクトリ: {args.source_dir}")
    
    # CSVからカード情報を読み込む
    card_data = read_card_data(args.csv_file)
    print(f"{len(card_data)}件のファイル情報を読み込みました")
    
    # ファイルの振り分け
    card_files, non_card_files, missing_files, month_stats = sort_files(args.source_dir, card_data)
    
    # 結果の表示
    print("\n処理結果:")
    print(f"- カード利用あり: {card_files}ファイル")
    print(f"- カード利用なし: {non_card_files}ファイル")
    print(f"- CSVに情報なし: {missing_files}ファイル")
    
    print("\n月別統計:")
    for month, stats in month_stats.items():
        print(f"- {month}: カード利用あり {stats['card']}ファイル, カード利用なし {stats['non_card']}ファイル")
    
    print("\n処理が完了しました")

if __name__ == "__main__":
    main() 