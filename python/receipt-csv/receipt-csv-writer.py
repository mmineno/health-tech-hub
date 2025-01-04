import anthropic
import base64
import os
import json
import pandas as pd
from PIL import Image
from io import BytesIO
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
MAX_FILE_SIZE_MB = 2.5

# CSVの設定
COLUMNS = ["発生日", "取引先", "税込金額", "摘要", "インボイス登録番号", "仕訳", "ファイル名"]
ACCOUNTS = ["通信費", "旅費交通費", "会議費", "交際費", "租税公課", "消耗品費", "支払手数料"]

# プロンプトテンプレート
PROMPT_TEMPLATE = """
領収書の画像から以下の情報を抽出してください:

フォーマット:
- 発生日: YYYY/MM/DD形式 (例: 2023/12/31)
- 取引先: 領収書に記載された店舗名または発行元の名称 (例: "株式会社ABC商事", "セブンイレブン〇〇店")
- 税込金額: 領収書に記載された合計金額（例: 1234, 小数点なし）
- 摘要: 領収書の内容を要約した説明 (例: "昼食代", "交通費", "文房具購入")
- インボイス登録番号: "T"で始まる13桁番号 (例: T1234567890123)、存在しない場合は"なし"
- 仕訳: 以下の候補から選択: {accounts}

出力例:
{{
    "発生日": "2023/12/31",
    "取引先": "株式会社ABC商事",
    "税込金額": 1234,
    "摘要": "文房具購入",
    "インボイス登録番号": "T1234567890123",
    "仕訳": "消耗品費"
}},
{{
    "発生日": "2024/2/1",
    "取引先": "東海旅客鉄道株式会社",
    "税込金額": 6560,
    "摘要": "JR乗車券類",
    "インボイス登録番号": "T3180001031569",
    "仕訳": "旅費交通費"
}}
"""

# 既存のCSVファイルを読み込み
if os.path.exists(OUTPUT_CSV):
    processed_files = pd.read_csv(OUTPUT_CSV, encoding="utf-8-sig")["ファイル名"].tolist()
else:
    processed_files = []

# エラーログファイル
ERROR_LOG_FILE = "error_log.txt"

def compress_image(image_path, max_size_mb):
    """画像を指定されたサイズ以下に圧縮する"""
    with Image.open(image_path) as img:
        buffer = BytesIO()
        img.save(buffer, format="JPEG", quality=90)
        size_mb = len(buffer.getvalue()) / (1024 * 1024)
        if size_mb <= max_size_mb:
            return buffer.getvalue()
        for quality in range(85, 10, -5):
            buffer = BytesIO()
            img.save(buffer, format="JPEG", quality=quality)
            size_mb = len(buffer.getvalue()) / (1024 * 1024)
            if size_mb <= max_size_mb:
                break
        return buffer.getvalue()

def log_error(error_message):
    """エラーログを記録する関数"""
    with open(ERROR_LOG_FILE, "a", encoding="utf-8") as error_log:
        error_log.write(f"{error_message}\n")

# フォルダ内の画像を処理
if not os.path.exists(INPUT_FOLDER):
    raise ValueError(f"入力フォルダが存在しません: {INPUT_FOLDER}")

for i, filename in enumerate(os.listdir(INPUT_FOLDER)):
    file_path = os.path.join(INPUT_FOLDER, filename)

    # スキップ条件
    if filename in processed_files:
        print(f"スキップ: {filename} (既に処理済み)")
        continue
    if not os.path.isfile(file_path) or not any(filename.lower().endswith(ext) for ext in SUPPORTED_EXTENSIONS):
        continue

    if i > 10:
        break

    print(f"処理中 ({i+1}): {filename}")
    
    try:
        # 画像の圧縮
        with open(file_path, "rb") as image_file:
            original_size_mb = os.path.getsize(file_path) / (1024 * 1024)
            if original_size_mb > MAX_FILE_SIZE_MB:
                print(f"{filename} は {original_size_mb:.2f} MB です。圧縮を実行します。")
                compressed_image = compress_image(file_path, MAX_FILE_SIZE_MB)
                compressed_size_mb = len(compressed_image) / (1024 * 1024)
                image_data = base64.b64encode(compressed_image).decode("utf-8")
                print(f"{filename} は {compressed_size_mb:.2f} MB に圧縮されました。")
            else:
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
            # レスポンス解析
            if isinstance(message.content, list):
                content = message.content[0].text
            elif isinstance(message.content, str):
                content = message.content
            else:
                raise ValueError("予期しないAPIレスポンス形式です。")

            try:
                result_data = json.loads(content)
            except json.JSONDecodeError:
                start_idx = content.find('{')
                end_idx = content.rfind('}') + 1
                if start_idx != -1 and end_idx != -1:
                    json_str = content[start_idx:end_idx]
                    result_data = json.loads(json_str)
                else:
                    raise ValueError("JSONデータが見つかりません")
            
            print(f"解析結果: {result_data}")
            
            # CSVに追記
            row = {
                "発生日": result_data.get("発生日", ""),
                "取引先": result_data.get("取引先", ""),
                "税込金額": result_data.get("税込金額", ""),
                "摘要": result_data.get("摘要", ""),
                "インボイス登録番号": result_data.get("インボイス登録番号", "なし"),
                "仕訳": result_data.get("仕訳", ""),
                "ファイル名": filename,
            }
            df = pd.DataFrame([row])
            df.to_csv(OUTPUT_CSV, mode="a", index=False, header=not os.path.exists(OUTPUT_CSV), encoding="utf-8-sig")
            
        except (json.JSONDecodeError, AttributeError) as e:
            log_error(f"JSON解析エラー ({filename}): {e}\nレスポンス内容: {message.content}")
            continue

    except Exception as e:
        log_error(f"処理エラー ({filename}): {e}")
        continue

print("処理が完了しました。")
