import os
import sys
import json
import re
import requests
import io
import pandas as pd
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("NUMBERS_UPDATER")

NUMBERS_CSV_URLS = {
    'n3': 'https://loto-life.net/csv/numbers3',
    'n4': 'https://loto-life.net/csv/numbers4'
}

def clean_val(val):
    if not isinstance(val, str):
        return val
    s = val.strip()
    match = re.search(r'="(.+?)"', s)
    if match:
        return match.group(1)
    return s.strip('"')

def clean_data(df: pd.DataFrame) -> pd.DataFrame:
    return df.map(clean_val)

def fetch_and_parse_csv(game_key, url):
    logger.info(f"Downloading CSV for {game_key} from {url}...")
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    response = requests.get(url, headers=headers, timeout=15)
    response.raise_for_status()
    
    csv_bytes = response.content
    decoded_text = None
    for enc in ('cp932', 'utf-8', 'utf-8-sig'):
        try:
            decoded_text = csv_bytes.decode(enc)
            break
        except UnicodeDecodeError:
            continue
            
    if not decoded_text:
        raise ValueError(f"Failed to decode CSV bytes for {game_key}")
        
    df = pd.read_csv(io.StringIO(decoded_text.strip()))
    df.columns = [clean_val(c) if isinstance(c, str) else c for c in df.columns]
    df = clean_data(df)
    
    parsed_history = []
    
    # 桁数の設定
    pick_count = 3 if game_key == 'n3' else 4
    
    for _, row in df.iterrows():
        try:
            # 1列目: 回号
            round_no = int(row.iloc[0])
            # 2列目: 抽せん日
            date_str = str(row.iloc[1]).strip()
            # 3列目: 抽せん数字 (例: "191", "0097", または数値 97)
            num_val = str(row.iloc[2]).strip()
            
            # 小数点表記（例: 97.0）の場合は丸める
            if num_val.endswith('.0'):
                num_val = num_val[:-2]
                
            # 指定された桁数にゼロ埋め
            num_val = num_val.zfill(pick_count)
            numbers = [int(char) for char in num_val]
            
            # 基本的なバリデーション
            if len(numbers) != pick_count or any(not (0 <= n <= 9) for n in numbers):
                continue
                
            parsed_history.append({
                "round": round_no,
                "date": date_str,
                "numbers": numbers
            })
        except Exception as e:
            continue
            
    # 回号の降順でソートし、最新の100回分を切り出す
    parsed_history.sort(key=lambda x: x['round'], reverse=True)
    return parsed_history[:100]

def main():
    target_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "numbers_data.js")
    
    all_data = {}
    success_count = 0
    
    for game_key, url in NUMBERS_CSV_URLS.items():
        try:
            history = fetch_and_parse_csv(game_key, url)
            if not history:
                logger.error(f"No parsed data for {game_key}")
                continue
            all_data[game_key] = history
            success_count += 1
        except Exception as e:
            logger.error(f"Error updating {game_key}: {e}")
            
    if success_count == len(NUMBERS_CSV_URLS):
        try:
            # JavaScriptファイルとして書き出し
            js_content = f"""// ナンバーズ履歴データ（直近100回分）
// 自動生成・同期機能用
const DEFAULT_NUMBERS_DATA = {json.dumps(all_data, ensure_ascii=False, indent=2)};
"""
            with open(target_file, 'w', encoding='utf-8') as f:
                f.write(js_content)
            logger.info(f"Successfully updated numbers_data.js. Rounds: n3={len(all_data['n3'])}, n4={len(all_data['n4'])}")
            sys.exit(0)
        except Exception as e:
            logger.error(f"Error writing to numbers_data.js: {e}")
            sys.exit(1)
    else:
        logger.warning(f"Some updates failed. Successful: {success_count}/{len(NUMBERS_CSV_URLS)}")
        sys.exit(1)

if __name__ == "__main__":
    main()
