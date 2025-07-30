# py/scanner.py
import requests
import time
import datetime
import json
import re
from sqlalchemy.orm import Session
from database import SessionLocal, SteamGame, create_db_and_tables

# ... (顶部的常量等保持不变) ...
STEAM_API_URL = "https://store.steampowered.com/api/appdetails"
REVIEW_API_URL = "https://store.steampowered.com/appreviews"
REQUEST_DELAY = 1.5
CORE_LANGUAGES = ["schinese", "japanese", "french", "koreana"]
ALL_STEAM_LANGUAGES = [
    "arabic", "bulgarian", "schinese", "tchinese", "czech", "danish", "dutch",
    "english", "finnish", "french", "german", "greek", "hungarian", "indonesian",
    "italian", "japanese", "koreana", "norwegian", "polish", "portuguese",
    "brazilian", "romanian", "russian", "spanish", "latam", "swedish", "thai",
    "turkish", "ukrainian", "vietnamese"
]

def get_app_details_with_retry(app_id: int, max_retries=3):
    params = {'appids': app_id, 'l': 'english'}
    for attempt in range(max_retries):
        try:
            response = requests.get(STEAM_API_URL, params=params, timeout=20)
            if response.status_code == 429:
                print(f"  - AppID {app_id}: 收到 429 错误。将暂停5分钟...")
                time.sleep(300)
                continue
            if response.status_code == 200:
                return response.json()
            print(f"  - AppID {app_id}: 收到状态码 {response.status_code}，将在 {5 * (attempt + 1)} 秒后重试。")
            time.sleep(5 * (attempt + 1))
        except requests.exceptions.RequestException as e:
            print(f"  - AppID {app_id}: 请求时发生网络错误: {e}。将在 {5 * (attempt + 1)} 秒后重试。")
            time.sleep(5 * (attempt + 1))
    print(f"  - AppID {app_id}: 重试 {max_retries} 次后仍然失败。")
    return None

def parse_languages(supported_languages_str: str):
    if not supported_languages_str:
        return ""
    clean_str = re.sub('<[^<]+?>', ' ', supported_languages_str)
    clean_str = clean_str.replace('*', '')
    clean_str = re.sub(r'languages with full audio support', '', clean_str, flags=re.IGNORECASE)
    languages = [lang.strip() for lang in clean_str.split(',') if lang.strip()]
    unique_languages = sorted(list(set(languages)), key=str.lower)
    return ",".join(filter(None, unique_languages))

def parse_tags(genres: list, categories: list):
    tags = set()
    if genres:
        for genre in genres:
            tags.add(genre.get('description', '').strip())
    if categories:
        for cat in categories:
            tags.add(cat.get('description', '').strip())
    return ",".join(filter(None, tags))

def get_review_count(app_id: int, language: str, purchase_type: str, api_key: str | None = None):
    params = {'json': 1, 'language': language, 'purchase_type': purchase_type}
    try:
        response = requests.get(f"{REVIEW_API_URL}/{app_id}", params=params, timeout=10)
        if response.status_code == 200:
            data = response.json()
            if data and data.get('success') == 1:
                return data.get('query_summary', {}).get('total_reviews', 0)
        return 0
    except requests.exceptions.RequestException:
        return 0

def process_single_game(game: SteamGame, db: Session, languages_to_scan: list[str] | None = None, force_details_update: bool = False, api_key: str | None = None):
    print(f"--> 开始处理 AppID: {game.app_id} ({game.name})")

    if force_details_update or not game.last_scanned:
        print("  - 正在更新游戏基本详情...")
        details = get_app_details_with_retry(game.app_id)
        
        if not details or not details.get(str(game.app_id), {}).get('success'):
            print(f"  - AppID {game.app_id}: 获取详情失败或返回无效数据，标记后跳过。")
            game.last_scanned = datetime.datetime.now(datetime.timezone.utc)
            return
        
        app_data = details[str(game.app_id)]['data']
        app_type = app_data.get('type')
        game.type = app_type

        # --- 核心修改在这里 ---
        if app_type not in ['game', 'demo']:
            print(f"  - AppID {game.app_id} 不是游戏或Demo (类型: {app_type})。标记后跳过。")
            game.last_scanned = datetime.datetime.now(datetime.timezone.utc)
            return

        raw_lang_str = app_data.get('supported_languages', '')
        game.supported_languages = parse_languages(raw_lang_str)
        game.tags = parse_tags(app_data.get('genres', []), app_data.get('categories', []))
        print(f"  - AppID {game.app_id} 详情解析完成！")

        game.total_reviews_all_purchase_types = get_review_count(game.app_id, 'all', 'all', api_key=api_key)
        time.sleep(0.2)
        game.total_reviews_steam_purchase_only = get_review_count(game.app_id, 'all', 'steam', api_key=api_key)
        print(f"  - 总评测数更新完毕: {game.total_reviews_all_purchase_types}")
    
    scan_list = languages_to_scan if languages_to_scan is not None else CORE_LANGUAGES
    if scan_list:
      print(f"  - 准备扫描以下语言的评测: {scan_list}")
      try:
          existing_reviews = json.loads(game.language_reviews) if game.language_reviews else {}
      except (json.JSONDecodeError, TypeError):
          existing_reviews = {}

      for lang_code in scan_list:
          if lang_code not in ALL_STEAM_LANGUAGES:
              continue
          print(f"    - 正在获取 {lang_code} 评测...")
          review_count = get_review_count(game.app_id, lang_code, 'all', api_key=api_key)
          existing_reviews[lang_code] = review_count
          time.sleep(REQUEST_DELAY)

      game.language_reviews = json.dumps(existing_reviews)
    
    game.last_scanned = datetime.datetime.now(datetime.timezone.utc)
    print(f"  - AppID {game.app_id} 处理完成，时间戳已更新。")


def scan_and_update_games():
    db: Session = SessionLocal()
    try:
        while True:
            games_to_scan = db.query(SteamGame).filter(SteamGame.last_scanned == None).limit(100).all()
            if games_to_scan:
                print(f"\n--- 发现 {len(games_to_scan)} 个新条目，开始常规扫描 ---")
                for game in games_to_scan:
                    process_single_game(game, db, languages_to_scan=CORE_LANGUAGES, force_details_update=True)
                    db.commit()
                    print(f"  - AppID {game.app_id} 的更改已提交到数据库。")
                    time.sleep(REQUEST_DELAY)
                continue

            print("\n--- 没有新条目，开始检查超过7天未更新的游戏 ---")
            seven_days_ago = datetime.datetime.utcnow() - datetime.timedelta(days=7)
            # --- 核心修改在这里 ---
            games_to_rescan = db.query(SteamGame).filter(
                SteamGame.last_scanned < seven_days_ago, 
                SteamGame.type.in_(['game', 'demo'])
            ).order_by(SteamGame.last_scanned.asc()).limit(100).all()
            
            if games_to_rescan:
                print(f"--- 发现 {len(games_to_rescan)} 个旧游戏需要更新，开始常规扫描 ---")
                for game in games_to_rescan:
                    process_single_game(game, db, languages_to_scan=CORE_LANGUAGES, force_details_update=True)
                    db.commit()
                    print(f"  - AppID {game.app_id} 的更改已提交到数据库。")
                    time.sleep(REQUEST_DELAY)
            else:
                print("--- 所有游戏数据都比较新，暂停1小时后再次检查 ---")
                time.sleep(3600)
    except KeyboardInterrupt:
        print("\n收到中断信号，程序退出。")
    except Exception as e:
        print(f"扫描过程中发生严重错误: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    print("--- 开始后台数据扫描任务 (按 Ctrl+C 退出) ---")
    create_db_and_tables()
    scan_and_update_games()