import anthropic
import base64
import os
import json
import pandas as pd
from dotenv import load_dotenv

# .envファイルから環境変数を読み込む
load_dotenv()

MODEL_ID = "claude-3-haiku-20240307"

# Anthropic APIの設定
API_KEY = os.getenv("ANTHROPIC_API_KEY")
if not API_KEY:
    raise ValueError("APIキーが設定されていません。'.env'ファイルを確認してください。")

client = anthropic.Anthropic(api_key=API_KEY)

# 入力/出力の設定
INPUT_FOLDER = "./ryoshusho-202411"
OUTPUT_CSV = "output.csv"
SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png"}

# CSVの設定
COLUMNS = ["発生日", "取引先", "税込金額", "摘要", "インボイス登録番号", "仕訳", "ファイル名"]
ACCOUNTS = ["通信費", "旅費交通費", "会議費", "交際費", "租税公課", "消耗品費", "支払手数料"]

# プロンプトテンプレート
PROMPT_TEMPLATE = """
領収書の画像から以下の情報を抽出してください:

フォーマット:
- 発生日: YYYY-MM-DD形式 (例: 2023-12-31)
- 取引先: 領収書に記載された店舗名または発行元の名称 (例: "株式会社ABC商事", "セブンイレブン〇〇店")
- 税込金額: 領収書に記載された合計金額（例: 1234, 小数点なし）
- 摘要: 領収書の内容を要約した説明 (例: "昼食代", "交通費", "文房具購入")
- インボイス登録番号: "T"で始まる13桁番号 (例: T1234567890123)、存在しない場合は"なし"
- 仕訳: 以下の候補から選択: {accounts}

出力例:
{{
    "発生日": "2023-12-31",
    "取引先": "株式会社ABC商事",
    "税込金額": 1234,
    "摘要": "文房具購入",
    "インボイス登録番号": "T1234567890123",
    "仕訳": "消耗品費"
}},
{{
    "発生日": "2024-01-15",
    "取引先": "株式会社交通サービス",
    "税込金額": 2200,
    "摘要": "電車賃",
    "インボイス登録番号": "なし",
    "仕訳": "旅費交通費"
}}
"""

# 出力ディレクトリの作成
output_dir = os.path.dirname(OUTPUT_CSV)
if output_dir:  # ディレクトリが指定されている場合のみ作成
    os.makedirs(output_dir, exist_ok=True)

# データ格納用リスト
data = []

# エラーログファイル
ERROR_LOG_FILE = "error_log.txt"

def log_error(error_message):
    """エラーログを記録する関数"""
    with open(ERROR_LOG_FILE, "a", encoding="utf-8") as error_log:
        error_log.write(f"{error_message}\n")

# フォルダ内の画像を処理
if not os.path.exists(INPUT_FOLDER):
    raise ValueError(f"入力フォルダが存在しません: {INPUT_FOLDER}")

for i, filename in enumerate(os.listdir(INPUT_FOLDER)):
    file_path = os.path.join(INPUT_FOLDER, filename)

    # ファイルが画像かどうかをチェック
    if not os.path.isfile(file_path):
        continue  # ディレクトリや隠しファイルをスキップ
    if not any(filename.lower().endswith(ext) for ext in SUPPORTED_EXTENSIONS):
        continue

    if i > 3:
        break

    print(f"処理中 ({i+1}): {filename}")
    
    try:
        # 画像をbase64エンコード
        with open(file_path, "rb") as image_file:
            image_data = base64.b64encode(image_file.read()).decode("utf-8")
        
        # APIリクエスト
        message = client.messages.create(
            model=MODEL_ID,
            max_tokens=1024*2,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/jpeg",
                                "data": image_data,
                            },
                        },
                        {
                            "type": "text",
                            "text": PROMPT_TEMPLATE.format(accounts=ACCOUNTS)
                        }
                    ],
                }
            ],
        )

        try:
            # レスポンスの中身を確認してテキストを抽出
            if isinstance(message.content, list):
                # リスト内の最初の`TextBlock`オブジェクトの`text`属性を取得
                content = message.content[0].text
            elif isinstance(message.content, str):
                # contentが文字列の場合はそのまま使用
                content = message.content
            else:
                raise ValueError("予期しないAPIレスポンス形式です。")

            # JSON解析
            try:
                result_data = json.loads(content)
            except json.JSONDecodeError:
                # JSON部分の特定と解析
                start_idx = content.find('{')
                end_idx = content.rfind('}') + 1
                if start_idx != -1 and end_idx != -1:
                    json_str = content[start_idx:end_idx]
                    result_data = json.loads(json_str)
                else:
                    raise ValueError("JSONデータが見つかりません")
            
            print(f"解析結果: {result_data}")
            
            # CSVの行を作成
            row = [
                result_data.get("発生日", ""),
                result_data.get("取引先", ""),
                result_data.get("税込金額", ""),
                result_data.get("摘要", ""),
                result_data.get("インボイス登録番号", "なし"),
                result_data.get("仕訳", ""),  # デフォルト値
                filename,
            ]
            data.append(row)
            
        except (json.JSONDecodeError, AttributeError) as e:
            error_message = f"JSON解析エラー ({filename}): {e}\nレスポンス内容: {message.content}"
            print(error_message)
            log_error(error_message)
            continue

    except Exception as e:
        error_message = f"処理エラー ({filename}): {e}"
        print(error_message)
        log_error(error_message)
        continue

# データをCSVに保存
if data:
    df = pd.DataFrame(data, columns=COLUMNS)
    df.to_csv(OUTPUT_CSV, index=False, encoding="utf-8-sig")
    print(f"CSVファイルを出力しました: {OUTPUT_CSV}")
else:
    print("処理可能な画像が見つからないか、すべての処理が失敗しました。")
