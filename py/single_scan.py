# single_scan.py
import argparse
from sqlalchemy.orm import Session
from database import SessionLocal, SteamGame, create_db_and_tables
from scanner import process_single_game # 导入更新后的核心处理函数

def run_single_scan(app_id: int):
    """
    对单个AppID执行一次完整的扫描、数据更新和提交。
    """
    db: Session = SessionLocal()
    try:
        # 确保表存在
        create_db_and_tables()

        # 查找数据库中的游戏
        game_to_scan = db.query(SteamGame).filter(SteamGame.app_id == app_id).first()

        if not game_to_scan:
            print(f"错误：在数据库的 'steam_games' 表中未找到 AppID {app_id}。")
            print("请先确保你已经运行过 sync_steam_apps.py 来填充游戏列表。")
            return

        # 1. 调用核心函数来修改 game 对象
        # --- 修改：新增 force_details_update=True 参数 ---
        # 确保每次手动扫描都会更新包括“支持语言”在内的所有核心信息
        print("正在以强制更新模式执行单次扫描...")
        process_single_game(game_to_scan, db, force_details_update=True)
        
        # 2. 提交所有更改
        db.commit()
        
        print(f"\n✅ 事务已提交！AppID {app_id} 的数据已在数据库中完整更新。")
        print("现在您可以去数据库检查 supported_languages 和 language_reviews 字段了。")

    except Exception as e:
        print(f"执行单次扫描时发生错误: {e}")
        db.rollback() # 如果发生错误，则回滚所有更改
    finally:
        db.close()
        
if __name__ == "__main__":
    # --- 设置命令行参数解析 ---
    parser = argparse.ArgumentParser(description="对单个Steam游戏执行一次数据扫描和更新。")
    parser.add_argument("app_id", type=int, help="要扫描的Steam游戏的AppID。")
    
    args = parser.parse_args()
    
    # --- 执行主函数 ---
    run_single_scan(args.app_id)
