import os

def concatenate_md_files(folder_path, output_file):
    try:
        def process_folder(folder):
            md_files = []
            for root, _, files in os.walk(folder):
                for file in files:
                    if file.endswith('.md'):
                        md_files.append(os.path.join(root, file))
            return sorted(md_files)

        # 再帰的にフォルダ内の.mdファイルを取得
        md_files = process_folder(folder_path)

        with open(output_file, 'w', encoding='utf-8') as outfile:
            for md_file in md_files:
                with open(md_file, 'r', encoding='utf-8') as infile:
                    outfile.write(infile.read())
                    outfile.write('\n\n')  # ファイル間に改行を追加

        print(f"All .md files in '{folder_path}' have been recursively concatenated into '{output_file}'.")
    except Exception as e:
        print(f"An error occurred: {e}")

# 使用例
# 'path_to_folder' を対象のフォルダのパスに変更
# 'output.md' を出力ファイル名に変更
folder_path = '/Users/mmineno/Downloads/hotnavi_md'
output_file = 'output.md'
concatenate_md_files(folder_path, output_file)