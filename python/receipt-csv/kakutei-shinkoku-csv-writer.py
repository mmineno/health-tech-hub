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
INPUT_FOLDER = "/Users/mmineno/develop/project/health-tech-hub/領収書-2024-個人"  # 領収書画像/ PDFの格納フォルダ
OUTPUT_CSV = "output.csv"            # 結果CSVファイルのパス
ERROR_LOG_FILE = "error_log.txt"     # エラー記録用ファイル

# 再帰的に収集する際、対応可能な拡張子
SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".pdf"}

# Anthropicに送信する画像の上限サイズ(MB)
MAX_FILE_SIZE_MB = 2.5

# CSV出力用の列定義（青色申告で便利な項目）
COLUMNS = [
    "対象外",           # 対象外かどうかのチェック項目
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

ACCOUNTS = [
    "外注費",
    "旅費交通費",
    "通信費",
    "消耗品費",
    "事務用品費",
    "会議費",
    "接待交際費",
    "研修費",
    "新聞図書費",
    "水道光熱費",
    "支払手数料",
    "租税公課",
    "減価償却費",
    "雑費",
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
{{
  "発生日": "2025/01/31",
  "取引先": "株式会社ABC商事",
  "勘定科目": "消耗品費",
  "税込金額": 1200,
  "税抜金額": 1091,
  "消費税額": 109,
  "摘要": "文房具購入",
  "インボイス登録番号": "T1234567890123"
}}

必ず上記のキーをすべて含むJSONを出力してください。
""".strip()

def log_error(error_message: str):
    """
    エラーをログファイルに書き込むユーティリティ
    """
    print(f"エラー: {error_message}")
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
        print(f"APIリクエスト開始: モデル={model_id}, 画像サイズ={len(image_data)/1024:.1f}KB")
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
        print("APIリクエスト完了: レスポンス受信")
        
        # レスポンスの詳細をデバッグ表示
        print(f"レスポンスタイプ: {type(message.content)}")
        if isinstance(message.content, list):
            print(f"レスポンス要素数: {len(message.content)}")
            for i, content in enumerate(message.content):
                print(f"要素{i}のタイプ: {type(content)}")
                if hasattr(content, 'text'):
                    print(f"要素{i}のテキスト先頭: {content.text[:50]}...")
        elif isinstance(message.content, str):
            print(f"レスポンス先頭: {message.content[:50]}...")
            
    except Exception as e:
        print(f"APIリクエストエラー: {e}")
        print(f"エラータイプ: {type(e)}")
        import traceback
        traceback.print_exc()
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

    print(f"解析対象のテキスト: {raw_content[:100]}...")
    
    try:
        # JSONの開始と終了位置を探す
        start_idx = raw_content.find("{")
        end_idx = raw_content.rfind("}") + 1
        
        if start_idx == -1 or end_idx <= 0:
            print(f"JSONの開始・終了タグが見つかりません。テキスト全体: {raw_content}")
            raise ValueError("JSONの開始・終了タグが見つかりません")
            
        json_str = raw_content[start_idx:end_idx]
        print(f"抽出したJSON文字列: {json_str[:100]}...")
        
        result_data = json.loads(json_str)
        print("JSON解析成功")
    except Exception as e:
        print(f"JSON解析エラー: {e}")
        print(f"解析対象テキスト全体: {raw_content}")
        log_error(f"JSON解析エラー: {file_id_for_csv}\n{e}\nレスポンス: {raw_content}")
        return

    # CSVに書き込むデータ組み立て
    row = {
        "対象外": "",  # デフォルトは空欄
        "発生日": result_data.get("発生日", ""),
        "取引先": result_data.get("取引先", ""),
        "勘定科目": result_data.get("勘定科目", ""),
        "税込金額": result_data.get("税込金額", ""),
        "税抜金額": result_data.get("税抜金額", ""),
        "消費税額": result_data.get("消費税額", ""),
        "摘要": result_data.get("摘要", ""),
        "インボイス登録番号": result_data.get("インボイス登録番号", "なし"),
        "ファイル名": os.path.basename(file_id_for_csv),  # パスからファイル名のみを抽出
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
    processed_files = set()
    if os.path.exists(OUTPUT_CSV):
        try:
            # CSVからファイル名を読み込む
            df = pd.read_csv(OUTPUT_CSV, encoding="utf-8-sig")
            
            # 既存データのファイル名をすべて取得
            if "ファイル名" in df.columns:
                for file_name in df["ファイル名"].unique():
                    # フルパスの場合はそのまま、ファイル名のみの場合はファイル名のセットに追加
                    if os.path.isabs(file_name):
                        processed_files.add(file_name)
                    else:
                        # ファイル名のみの場合は、元のファイル名だけをメモリに保持
                        processed_files.add(os.path.basename(file_name))
            
            print(f"既存CSVから{len(processed_files)}件の処理済みファイル情報を読み込みました")
        except Exception as e:
            print(f"CSVの読み込み中にエラーが発生しました: {e}")
            # エラーの場合は空のセットで続行
            processed_files = set()
    else:
        print("既存のCSVが見つかりません。新規作成します。")

    file_count = 0
    processed_count = 0

    # os.walk で再帰的にファイルを探索
    for root, dirs, files in os.walk(INPUT_FOLDER):
        # ファイルをソートして名前順に処理
        for filename in sorted(files):
            ext = os.path.splitext(filename)[1].lower()
            if ext not in SUPPORTED_EXTENSIONS:
                continue

            file_path = os.path.join(root, filename)
            file_basename = os.path.basename(file_path)

            # ファイル名とフルパスの両方で重複チェック
            if file_basename in processed_files or file_path in processed_files:
                print(f"スキップ: {file_path} (既に処理済み)")
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

                # 処理したファイルを記録（ファイル名のみと完全パスの両方）
                processed_files.add(file_basename)
                processed_files.add(file_path)
                processed_count += 1

            except Exception as e:
                log_error(f"ファイル処理エラー: {file_path}\n{e}")

    print(f"処理が完了しました。合計{file_count}件のファイルをスキャンし、{processed_count}件の新規ファイルを処理しました。")

if __name__ == "__main__":
    main()