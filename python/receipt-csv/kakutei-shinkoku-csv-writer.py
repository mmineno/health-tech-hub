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

# Anthropic API のキーを環境変数から取得
API_KEY = os.getenv("ANTHROPIC_API_KEY")
if not API_KEY:
    raise ValueError("Anthropic APIキーが設定されていません。.envファイルを確認してください。")

# Anthropicクライアントの初期化
client = anthropic.Anthropic(api_key=API_KEY)

# AnthropicモデルID（2025年現在の最新・推奨モデルを指定：claude-2, claude-instant-1 など）
MODEL_ID = "claude-3-7-sonnet-20250219"

# フォルダ・ファイル設定
INPUT_FOLDER = "./領収書-2024-個人"  # 領収書画像/ PDFの格納フォルダ
OUTPUT_CSV = "output.csv"            # 結果CSVファイルのパス
ERROR_LOG_FILE = "error_log.txt"     # エラー記録用ファイル

# 再帰的に収集する際、対応可能な拡張子
SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".pdf"}

# Anthropicに送信する画像の上限サイズ(MB)
MAX_FILE_SIZE_MB = 2.5

# CSV出力用の列定義（青色申告で便利な項目）
COLUMNS = [
    "発生日",           # YYYY/MM/DD
    "取引先",           # 領収書発行元
    "勘定科目",         # 仕訳科目
    "税込金額",         # 合計支払額
    "税抜金額",         # （税込金額 － 消費税額）
    "消費税額",         # 領収書に記載の税額や逆算した額
    "摘要",            # "昼食代" "交通費" "文房具購入"など
    "インボイス登録番号", # あれば "Txxxxxxxxxxxxx"
    "ファイル名",       # 元のファイル名
]

# 税理士が推奨する青色申告の主要勘定科目例
ACCOUNTS = [
    "消耗品費",
    "通信費",
    "旅費交通費",
    "広告宣伝費",
    "接待交際費",
    "水道光熱費",
    "租税公課",
    "外注工賃",
    "雑費",
    "その他"
]

# Anthropicへ送信するプロンプト(ユーザーメッセージ)
PROMPT_TEMPLATE = """
以下は、日本の個人事業主が青色申告（インボイス制度対応）で使用する「領収書情報」の抽出タスクです。
領収書画像から、次の項目を JSON 形式で出力してください。

【出力すべき項目】
1. "発生日": 領収書にある支払日・発行日 (YYYY/MM/DD形式)
2. "取引先": 店舗名、発行元の名称
3. "勘定科目": 下記候補のうち最も適切な1つ -> {accounts}
4. "税込金額": 領収書に書かれた合計金額（整数のみ, 小数点不要）
5. "税抜金額": (税込金額 - 消費税額)
6. "消費税額": 領収書上で判明する消費税額。明示的に書かれていない場合は概算や0も可
7. "摘要": 取引の内容 (例: "文房具購入", "電車代", "昼食代", "タクシー代" など)
8. "インボイス登録番号": 領収書に記載があれば (T＋13桁)。なければ "なし"

【JSON出力例】
{
  "発生日": "2025/01/31",
  "取引先": "株式会社ABC商事",
  "勘定科目": "消耗品費",
  "税込金額": 1200,
  "税抜金額": 1091,
  "消費税額": 109,
  "摘要": "文房具購入",
  "インボイス登録番号": "T1234567890123"
}

必ず上記のキーをすべて含むJSONを出力してください。
""".strip()

def log_error(error_message: str):
    """
    エラーをログファイルに書き込むユーティリティ
    """
    with open(ERROR_LOG_FILE, "a", encoding="utf-8") as error_log:
        error_log.write(f"{error_message}\n")

def compress_image(img: Image.Image, max_size_mb: float) -> bytes:
    """
    画像を指定サイズ以下に圧縮し、圧縮後のバイト列を返す
    (JPEGクオリティを段階的に落としながらサイズを下げる)
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
    PDFを複数ページ読み込み、縦方向に連結して一枚のRGBイメージとして返す
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
        log_error(f"PDF変換エラー: {file_path}\n{e}")
        raise

def extract_images(file_path: str, dpi: int = 150) -> list[Image.Image]:
    """
    拡張子をチェックし、PDFならpdf_to_single_image、画像ならImage.openで読み込む
    返り値は PIL.Image のリスト
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
    model_id: str
):
    """
    1. PIL.Image を base64エンコード
    2. Anthropic APIに送信してJSONレスポンスを得る
    3. CSVへ追記する
    """
    # 画像をRGBに統一
    pil_img = pil_img.convert("RGB")

    # まず元サイズで取得
    raw_buffer = BytesIO()
    pil_img.save(raw_buffer, format="JPEG")
    original_size_mb = len(raw_buffer.getvalue()) / (1024 * 1024)

    # サイズが大きければ圧縮
    if original_size_mb > MAX_FILE_SIZE_MB:
        compressed_data = compress_image(pil_img, MAX_FILE_SIZE_MB)
        image_data = base64.b64encode(compressed_data).decode("utf-8")
    else:
        image_data = base64.b64encode(raw_buffer.getvalue()).decode("utf-8")

    # Anthropicへメッセージ送信
    try:
        message = client.messages.create(
            model=model_id,
            max_tokens=2048,
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
        log_error(f"APIリクエストエラー: {file_id_for_csv}\n{e}")
        return

    # レスポンス解析
    if isinstance(message.content, str):
        raw_content = message.content
    elif isinstance(message.content, list) and message.content:
        raw_content = message.content[0].text
    else:
        log_error(f"予期しないレスポンス形式: {file_id_for_csv}\n{message}")
        return

    try:
        start_idx = raw_content.find("{")
        end_idx = raw_content.rfind("}") + 1
        json_str = raw_content[start_idx:end_idx] if start_idx != -1 and end_idx != -1 else ""
        result_data = json.loads(json_str)
    except Exception as e:
        log_error(f"JSON解析エラー: {file_id_for_csv}\n{e}\nレスポンス: {raw_content}")
        return

    # CSVに書き込むデータ組み立て
    row = {
        "発生日": result_data.get("発生日", ""),
        "取引先": result_data.get("取引先", ""),
        "勘定科目": result_data.get("勘定科目", ""),
        "税込金額": result_data.get("税込金額", ""),
        "税抜金額": result_data.get("税抜金額", ""),
        "消費税額": result_data.get("消費税額", ""),
        "摘要": result_data.get("摘要", ""),
        "インボイス登録番号": result_data.get("インボイス登録番号", "なし"),
        "ファイル名": file_id_for_csv,
    }

    # CSVへ追記
    try:
        # 既存ヘッダが無ければヘッダをつける
        header_required = not os.path.exists(OUTPUT_CSV)
        df = pd.DataFrame([row])
        df.to_csv(OUTPUT_CSV, mode="a", index=False, header=header_required, encoding="utf-8-sig")
    except Exception as e:
        log_error(f"CSV書き込みエラー: {file_id_for_csv}\n{e}")

def main():
    """
    領収書フォルダ内（サブフォルダ含む）を再帰的に走査し、
    PDF・画像をAnthropicに送信 → CSVに仕訳候補を保存
    """
    if not os.path.exists(INPUT_FOLDER):
        raise ValueError(f"入力フォルダが存在しません: {INPUT_FOLDER}")

    # 既存のCSVをチェックし、重複を防ぐ
    if os.path.exists(OUTPUT_CSV):
        processed_files = pd.read_csv(OUTPUT_CSV, encoding="utf-8-sig")["ファイル名"].unique().tolist()
    else:
        processed_files = []

    file_count = 0

    # os.walk で再帰的にファイルを探索
    for root, dirs, files in os.walk(INPUT_FOLDER):
        for filename in files:
            ext = os.path.splitext(filename)[1].lower()
            if ext not in SUPPORTED_EXTENSIONS:
                continue

            file_path = os.path.join(root, filename)

            # 同じファイル名(厳密にはパス)が既に処理済みであればスキップ
            if filename in processed_files:
                print(f"スキップ: {filename} (既に処理済み)")
                continue

            file_count += 1
            print(f"処理中({file_count}): {file_path}")

            # 画像/ PDFを抽出
            try:
                pil_images = extract_images(file_path, dpi=150)
                for idx, pil_img in enumerate(pil_images, start=1):
                    # PDFの場合ページ番号を付与する
                    file_id_for_csv = f"{file_path}_page{idx}" if ext == ".pdf" else file_path

                    process_image_data(
                        pil_img=pil_img,
                        prompt_template=PROMPT_TEMPLATE,
                        file_id_for_csv=file_id_for_csv,
                        model_id=MODEL_ID
                    )

                processed_files.append(filename)

            except Exception as e:
                log_error(f"ファイル処理エラー: {file_path}\n{e}")

    print("処理が完了しました。")

if __name__ == "__main__":
    main()