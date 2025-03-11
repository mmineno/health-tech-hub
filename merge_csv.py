import os
import glob

# enaviフォルダへのパス
enavi_folder = 'enavi'

# CSVファイルのパスをすべて取得
csv_files = glob.glob(os.path.join(enavi_folder, '*.csv'))

# ファイルが見つからなかった場合のエラー処理
if not csv_files:
    print(f"エラー: {enavi_folder}フォルダ内にCSVファイルが見つかりません。")
    exit(1)

print(f"{len(csv_files)}個のCSVファイルが見つかりました:")
for file in csv_files:
    print(f"  - {file}")

# すべてのCSVファイルを連結
combined_content = ''
header = None

for file in sorted(csv_files):  # ファイル名でソート
    print(f"{file}を処理中...")
    
    # テキストモードでファイルを開く
    with open(file, 'r', encoding='utf-8', errors='replace') as f:
        content = f.read()
        
        # 最初のファイルのヘッダーを保存
        if header is None:
            # 最初の行をヘッダーとして保存
            lines = content.split('\n')
            if lines:
                header = lines[0]
                combined_content = header + '\n'  # ヘッダーを出力に追加
                content = '\n'.join(lines[1:])  # ヘッダー以外の行を結合
        else:
            # 2つ目以降のファイルはヘッダー行を除去
            lines = content.split('\n')
            if len(lines) > 1:
                content = '\n'.join(lines[1:])
        
        # ヘッダー以外の内容を結合
        combined_content += content
        if not content.endswith('\n'):
            combined_content += '\n'

# 出力ファイル名
output_file = 'combined_enavi.csv'

# 結合したデータを書き込む
with open(output_file, 'w', encoding='utf-8') as f:
    f.write(combined_content)

print(f"\n処理完了: {len(csv_files)}個のCSVファイルを連結して{output_file}に保存しました。") 