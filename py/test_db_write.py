# test_db_write.py
import argparse
import datetime
from sqlalchemy.orm import Session
from database import SessionLocal, SteamGame, create_db_and_tables

def run_write_test(app_id: int):
    """
    一个极简的测试，只验证能否向 last_scanned 字段写入时间戳。
    """
    print(f"--- 开始对 AppID: {app_id} 进行数据库写入测试 ---")
    
    # --- 步骤 1: 写入数据 ---
    db: Session = SessionLocal()
    try:
        print(f"\n[步骤 1] 正在查询游戏并尝试写入数据...")
        game = db.query(SteamGame).filter(SteamGame.app_id == app_id).first()
        if not game:
            print(f"错误：在数据库中未找到 AppID {app_id}。")
            return

        print(f"  - 写入前, 数据库中的 last_scanned 值为: {game.last_scanned}")
        
        # 准备要写入的时间戳
        current_time = datetime.datetime.now(datetime.timezone.utc)
        game.last_scanned = current_time
        
        print(f"  - 在内存中, last_scanned 已被设置为: {game.last_scanned}")
        
        print("  - 正在执行 db.commit()...")
        db.commit()
        print("  - commit 执行完毕。")

    except Exception as e:
        print(f"写入过程中发生严重错误: {e}")
        db.rollback()
    finally:
        print("  - 正在关闭数据库会话...")
        db.close()

    # --- 步骤 2: 验证数据 ---
    print("\n[步骤 2] 为了验证，将开启一个全新的会话，重新从数据库读取数据...")
    verify_db: Session = SessionLocal()
    try:
        game_after_update = verify_db.query(SteamGame).filter(SteamGame.app_id == app_id).first()
        
        print(f"  - 重新读取后, 数据库中的 last_scanned 值为: {game_after_update.last_scanned}")

        if game_after_update.last_scanned:
            print("\n✅ 测试成功！时间戳被成功写入并读取。")
            print("这意味着数据库连接、SQLAlchemy模型和timestamptz类型都没有问题。")
        else:
            print("\n❌ 测试失败！时间戳未能成功写入数据库。")
            print("这表明问题可能出在数据库配置或SQLAlchemy与数据类型的交互上。")
            
    except Exception as e:
        print(f"验证过程中发生严重错误: {e}")
    finally:
        verify_db.close()
        
    print("\n--- 测试结束 ---")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="测试能否向数据库的timestamptz字段写入数据。")
    parser.add_argument("app_id", type=int, help="要测试的Steam游戏的AppID。")
    args = parser.parse_args()
    run_write_test(args.app_id)
