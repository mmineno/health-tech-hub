import anthropic
import base64
import os
import json
import pandas as pd
from PIL import Image
from io import BytesIO
from dotenv import load_dotenv
from pdf2image import convert_from_path

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
SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".pdf"}
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
- インボイス登録番号: "T"で始まる14桁番号 (例: T12345678901234)、存在しない場合は"なし"
- 注意: 「ヘルステックハブ株式会社」は当社の法人名であり、取引先としては出力しない
- 仕訳: 以下の候補から選択: {accounts}

出力例:
{
    "発生日": "2023/12/31",
    "取引先": "株式会社ABC商事",
    "税込金額": 1234,
    "摘要": "文房具購入",
    "インボイス登録番号": "T1234567890123",
    "仕訳": "消耗品費"
},
{
    "発生日": "2024/2/1",
    "取引先": "東海旅客鉄道株式会社",
    "税込金額": 6560,
    "摘要": "JR乗車券類",
    "インボイス登録番号": "T3180001031569",
    "仕訳": "旅費交通費"
}
"""

# 既存のCSVファイルを読み込み
if os.path.exists(OUTPUT_CSV):
    processed_files = pd.read_csv(OUTPUT_CSV, encoding="utf-8-sig")["ファイル名"].tolist()
else:
    processed_files = []

# エラーログファイル
ERROR_LOG_FILE = "error_log.txt"

def log_error(error_message: str):
    """エラーログを記録する関数"""
    with open(ERROR_LOG_FILE, "a", encoding="utf-8") as error_log:
        error_log.write(f"{error_message}\n")

def compress_image(img: Image.Image, max_size_mb: float) -> bytes:
    """
    画像を指定されたサイズ以下に圧縮してバイナリデータを返す関数。
    引数は PIL.Image オブジェクト。
    """
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

def pdf_to_single_image(file_path: str, dpi: int = 150) -> Image.Image:
    """
    PDFを読み込んで、複数ページを縦方向に連結し、
    1枚のPIL.Imageとして返す。
    """
    try:
        pages = convert_from_path(file_path, dpi=dpi)
        if not pages:
            raise ValueError("PDFにページが存在しません。")

        max_width = max(page.width for page in pages)
        total_height = sum(page.height for page in pages)
        combined_img = Image.new("RGB", (max_width, total_height), (255, 255, 255))

        y_offset = 0
        for page in pages:
            combined_img.paste(page, (0, y_offset))
            y_offset += page.height

        return combined_img

    except Exception as e:
        log_error(f"PDF変換エラー ({file_path}): {e}")
        raise

def extract_images(file_path: str, dpi: int = 150) -> list[Image.Image]:
    """
    ファイルパスを受け取り、PIL.Image のリストを返す関数。
    - PDF の場合は pdf_to_single_image() でページを1枚にまとめて返す。
    - 画像ファイル（jpg/pngなど）は 1枚だけのリストにして返す。
    """
    ext = os.path.splitext(file_path)[1].lower()
    if ext == ".pdf":
        single_img = pdf_to_single_image(file_path, dpi=dpi)
        return [single_img]
    else:
        img = Image.open(file_path)
        return [img]

def process_image_data(
    pil_img: Image.Image,
    prompt_template: str,
    file_id_for_csv: str,
    model_id: str = MODEL_ID
):
    """
    PIL.Image を Anthropic API に送信し、レスポンス解析・結果記録を行う
    """
    pil_img = pil_img.convert("RGB")
    raw_buffer = BytesIO()
    pil_img.save(raw_buffer, format="JPEG")
    original_size_mb = len(raw_buffer.getvalue()) / (1024 * 1024)

    if original_size_mb > MAX_FILE_SIZE_MB:
        compressed_data = compress_image(pil_img, MAX_FILE_SIZE_MB)
        image_data = base64.b64encode(compressed_data).decode("utf-8")
    else:
        image_data = base64.b64encode(raw_buffer.getvalue()).decode("utf-8")

    try:
        message = client.messages.create(
            model=model_id,
            max_tokens=1024 * 2,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": image_data}},
                        {"type": "text", "text": prompt_template.format(accounts=ACCOUNTS)},
                    ],
                }
            ],
        )
    except Exception as e:
        log_error(f"APIリクエストエラー ({file_id_for_csv}): {e}")
        return

    if isinstance(message.content, (str, list)):
        raw_content = message.content if isinstance(message.content, str) else message.content[0].text
        # print(f"DEBUG raw content: {repr(raw_content)}")
        try:
            start_idx = raw_content.find("{")
            end_idx = raw_content.rfind("}") + 1
            json_str = raw_content[start_idx:end_idx] if start_idx != -1 and end_idx != -1 else ""
            result_data = json.loads(json_str)
        except json.JSONDecodeError as e:
            log_error(f"JSON解析エラー ({file_id_for_csv}): {e}\nレスポンス内容: {raw_content}")
            return
    else:
        log_error(f"予期しないAPIレスポンス形式 ({file_id_for_csv}): {message}")
        return

    try:
        row = {
            "発生日": result_data.get("発生日", ""),
            "取引先": result_data.get("取引先", ""),
            "税込金額": result_data.get("税込金額", ""),
            "摘要": result_data.get("摘要", ""),
            "インボイス登録番号": result_data.get("インボイス登録番号", "なし"),
            "仕訳": result_data.get("仕訳", ""),
            "ファイル名": file_id_for_csv,
        }
        df = pd.DataFrame([row])
        df.to_csv(OUTPUT_CSV, mode="a", index=False, header=not os.path.exists(OUTPUT_CSV), encoding="utf-8-sig")
    except Exception as e:
        log_error(f"CSV書き込みエラー ({file_id_for_csv}): {e}")

if not os.path.exists(INPUT_FOLDER):
    raise ValueError(f"入力フォルダが存在しません: {INPUT_FOLDER}")

for i, filename in enumerate(os.listdir(INPUT_FOLDER)):
    file_path = os.path.join(INPUT_FOLDER, filename)

    if filename in processed_files:
        print(f"スキップ: {filename} (既に処理済み)")
        continue

    ext = os.path.splitext(filename)[1].lower()
    if not (os.path.isfile(file_path) and ext in SUPPORTED_EXTENSIONS):
        continue

    print(f"処理中 ({i+1}): {filename}")

    try:
        pil_images = extract_images(file_path, dpi=150)
        for idx, pil_img in enumerate(pil_images, start=1):

            process_image_data(
                pil_img=pil_img,
                prompt_template=PROMPT_TEMPLATE,
                file_id_for_csv=filename,
                model_id=MODEL_ID
            )

        processed_files.append(filename)

    except Exception as e:
        log_error(f"ファイル処理エラー ({filename}): {e}")

print("処理が完了しました。")
