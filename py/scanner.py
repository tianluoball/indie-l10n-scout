# scanner.py
import requests
import time
import datetime
from sqlalchemy.orm import Session
from sqlalchemy import or_
from database import SessionLocal, SteamGame, create_db_and_tables

STEAM_API_URL = "https://store.steampowered.com/api/appdetails"
REVIEW_API_URL = "https://store.steampowered.com/appreviews"
REQUEST_DELAY = 1.5

def get_app_details_with_retry(app_id: int, max_retries=3):
    params = {'appids': app_id, 'l': 'english'}
    for attempt in range(max_retries):
        try:
            response = requests.get(STEAM_API_URL, params=params, timeout=20)
            if response.status_code == 429:
                print(f"  - AppID {app_id}: 收到 429 错误 (请求过于频繁)。将暂停5分钟...")
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
    s_chinese = "simplified chinese" in supported_languages_str.lower()
    t_chinese = "traditional chinese" in supported_languages_str.lower()
    return s_chinese, t_chinese

def parse_tags(genres: list, categories: list):
    tags = set()
    if genres:
        for genre in genres:
            tags.add(genre.get('description', '').strip())
    if categories:
        for cat in categories:
            tags.add(cat.get('description', '').strip())
    return ",".join(filter(None, tags))

def get_review_count(app_id: int, language: str, purchase_type: str):
    """获取指定条件的评测总数"""
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

def process_single_game(game: SteamGame, db: Session):
    """处理单个游戏的扫描和数据更新逻辑"""
    print(f"--> 正在处理 AppID: {game.app_id} ({game.name})")
    try:
        details = get_app_details_with_retry(game.app_id)
        if not details or not details.get(str(game.app_id), {}).get('success'):
            print(f"  - AppID {game.app_id}: 获取详情失败或数据无效，跳过。")
            game.tags = ""
        else:
            app_data = details[str(game.app_id)]['data']
            game.has_simplified_chinese, game.has_traditional_chinese = parse_languages(app_data.get('supported_languages', ''))
            game.tags = parse_tags(app_data.get('genres', []), app_data.get('categories', []))
            print(f"  - AppID {game.app_id} 详情获取成功！")

        print("  - 正在获取评测数据...")
        game.total_reviews_all_purchase_types = get_review_count(game.app_id, 'all', 'all')
        time.sleep(0.2)
        game.chinese_reviews_all_purchase_types = get_review_count(game.app_id, 'schinese', 'all')
        time.sleep(0.2)
        game.total_reviews_steam_purchase_only = get_review_count(game.app_id, 'all', 'steam')
        time.sleep(0.2)
        game.chinese_reviews_steam_purchase_only = get_review_count(game.app_id, 'schinese', 'steam')
        print(f"  - 评测数据获取完毕: Total(All): {game.total_reviews_all_purchase_types}, Chinese(All): {game.chinese_reviews_all_purchase_types}")

    finally:
        game.last_scanned = datetime.datetime.utcnow()
        print(f"  - AppID {game.app_id} 的时间戳属性已在内存中更新。")

def scan_and_update_games():
    db: Session = SessionLocal()
    try:
        while True:
            games_to_scan = db.query(SteamGame).filter(SteamGame.last_scanned == None).limit(100).all()
            if games_to_scan:
                print(f"\n--- 发现 {len(games_to_scan)} 个新游戏，开始扫描 ---")
                for game in games_to_scan:
                    process_single_game(game, db)
                    db.commit()
                    print(f"  - AppID {game.app_id} 的更改已提交到数据库。")
                    time.sleep(REQUEST_DELAY)
                continue
            print("\n--- 没有新游戏，开始检查超过7天未更新的旧数据 ---")
            seven_days_ago = datetime.datetime.utcnow() - datetime.timedelta(days=7)
            games_to_rescan = db.query(SteamGame).filter(SteamGame.last_scanned < seven_days_ago).order_by(SteamGame.last_scanned.asc()).limit(100).all()
            if games_to_rescan:
                print(f"--- 发现 {len(games_to_rescan)} 个旧游戏需要更新，开始扫描 ---")
                for game in games_to_rescan:
                    process_single_game(game, db)
                    db.commit()
                    print(f"  - AppID {game.app_id} 的更改已提交到数据库。")
                    time.sleep(REQUEST_DELAY)
            else:
                print("--- 所有数据都比较新，暂停1小时后再次检查 ---")
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
