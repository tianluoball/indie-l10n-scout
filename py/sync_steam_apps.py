# sync_steam_apps.py
import requests
from sqlalchemy.orm import Session
# --- 修改：新增导入 create_db_and_tables ---
from database import SessionLocal, SteamGame, create_db_and_tables

def fetch_all_steam_games():
    """从Steam API获取所有应用的列表"""
    print("正在从Steam API获取所有游戏列表...")
    try:
        url = "https://api.steampowered.com/ISteamApps/GetAppList/v2/"
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        data = response.json()
        print(f"成功获取到 {len(data['applist']['apps'])} 个应用的信息。")
        return data['applist']['apps']
    except requests.exceptions.RequestException as e:
        print(f"错误：无法从Steam API获取数据。{e}")
        return None

def populate_database(apps_list: list):
    """将游戏列表填充到数据库中"""
    if not apps_list:
        print("没有应用数据可供填充。")
        return

    db: Session = SessionLocal()
    try:
        print("正在准备将数据写入数据库... 这可能需要几分钟。")
        
        # 获取数据库中已有的所有 app_id，避免重复插入
        existing_app_ids = {result[0] for result in db.query(SteamGame.app_id).all()}
        print(f"数据库中已存在 {len(existing_app_ids)} 条游戏记录。")

        games_to_add = []
        for app in apps_list:
            app_id = app.get('appid')
            name = app.get('name')
            
            # 过滤掉没有名字或已存在的游戏
            if name and app_id not in existing_app_ids:
                games_to_add.append(SteamGame(app_id=app_id, name=name))

        if not games_to_add:
            print("没有新的游戏需要添加到数据库。")
            db.close() # <-- 确保在返回前关闭数据库连接
            return

        print(f"即将向数据库中添加 {len(games_to_add)} 个新游戏...")
        
        # 批量插入，提高效率
        db.bulk_save_objects(games_to_add)
        db.commit()
        
        print(f"成功添加 {len(games_to_add)} 个新游戏到数据库！")

    except Exception as e:
        print(f"数据库操作时发生错误: {e}")
        db.rollback()
    finally:
        db.close()
        print("数据库会话已关闭。")

if __name__ == "__main__":
    # --- 新增：在执行任何操作前，先创建数据库表 ---
    print("正在检查并创建数据库表（如果不存在）...")
    create_db_and_tables()
    print("数据库表检查完成。")
    # -----------------------------------------

    all_apps = fetch_all_steam_games()
    if all_apps:
        populate_database(all_apps)
    
    print("\n同步完成！现在你的搜索功能应该可以正常使用了。")
