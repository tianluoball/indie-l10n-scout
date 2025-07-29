# main.py

import os
import requests
import datetime
import traceback
import time
from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session, aliased
from sqlalchemy import func, or_, desc, case
from dotenv import load_dotenv

from database import get_db, GameOpportunity, SteamGame, create_db_and_tables
from scanner import process_single_game

load_dotenv()
STEAM_API_KEY = os.getenv("STEAM_API_KEY")
create_db_and_tables()

app = FastAPI(
    title="Indie Game Localization Opportunity Finder",
    description="一个用于分析Steam游戏本地化潜力的API"
)

# --- CORS配置 ---
origins = ["http://localhost", "http://127.0.0.1", "http://doko-doa.local"]
app.add_middleware(CORSMiddleware, allow_origins=origins, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

# --- 辅助函数：按需更新单个游戏 ---
def update_single_game_if_stale(app_id: int, db: Session):
    """检查并按需更新单个游戏的数据"""
    game = db.query(SteamGame).filter(SteamGame.app_id == app_id).first()
    if not game:
        raise HTTPException(status_code=404, detail="数据库中未找到该游戏。")
    
    current_utc_time = datetime.datetime.now(datetime.timezone.utc)
    is_stale = not game.last_scanned or (current_utc_time - game.last_scanned > datetime.timedelta(hours=24))

    if is_stale:
        print(f"AppID {app_id} 的数据已过时，正在触发即时更新...")
        process_single_game(game, db)
        db.commit()
        db.refresh(game)
        print(f"AppID {app_id} 即时更新成功！")
    
    return game

# --- 根路径和搜索接口 ---
@app.get("/")
def read_root(): return {"message": "欢迎！"}

@app.get("/search", response_model=list[dict])
def search_games(query: str, db: Session = Depends(get_db)):
    if not query: return []
    search_query = f"%{query}%"
    found_games = db.query(SteamGame).filter(SteamGame.name.ilike(search_query)).limit(10).all()
    if not found_games: return []
    return [{"name": game.name, "appid": game.app_id} for game in found_games]

# --- V2分析接口 (最终版) ---
@app.get("/analyze/v2/{app_id}", response_model=dict)
def analyze_game_v2(app_id: int, db: Session = Depends(get_db)):
    """执行详细的对比分析，并返回所有精确数据"""
    try:
        target_game = update_single_game_if_stale(app_id, db)
        if not target_game.tags:
            raise HTTPException(status_code=400, detail="该游戏标签数据为空，无法进行对比分析。")
        
        target_tags = [tag.strip() for tag in target_game.tags.split(',') if tag.strip()]
        if not target_tags:
            raise HTTPException(status_code=400, detail="该游戏没有有效的标签，无法进行对比分析。")

        # --- 使用最准确的评测数进行对比 ---
        base_query = db.query(func.avg(SteamGame.total_reviews_all_purchase_types)) \
                       .filter(SteamGame.tags.isnot(None), SteamGame.tags != '') \
                       .filter(func.string_to_array(SteamGame.tags, ',').op('&&')(target_tags)) \
                       .filter(SteamGame.app_id != app_id)

        avg_with_chinese = base_query.filter((SteamGame.has_simplified_chinese == True) | (SteamGame.has_traditional_chinese == True)).scalar() or 0
        avg_without_chinese = base_query.filter((SteamGame.has_simplified_chinese == False) & (SteamGame.has_traditional_chinese == False)).scalar() or 0

        # (此处省略了返回对比案例的复杂逻辑，以确保核心功能稳定)

        return {
            "target_game": {
                "name": target_game.name,
                "app_id": target_game.app_id,
                "tags": target_tags,
                "has_simplified_chinese": target_game.has_simplified_chinese,
                "has_traditional_chinese": target_game.has_traditional_chinese,
                "total_reviews_all_purchase_types": target_game.total_reviews_all_purchase_types,
                "chinese_reviews_all_purchase_types": target_game.chinese_reviews_all_purchase_types,
                "total_reviews_steam_purchase_only": target_game.total_reviews_steam_purchase_only,
                "chinese_reviews_steam_purchase_only": target_game.chinese_reviews_steam_purchase_only,
            },
            "comparison": {
                "avg_reviews_with_chinese": round(avg_with_chinese),
                "avg_reviews_without_chinese": round(avg_without_chinese),
                "with_chinese_examples": [], # 简化返回
                "without_chinese_examples": [], # 简化返回
            }
        }
    except Exception as e:
        error_trace = traceback.format_exc()
        raise HTTPException(status_code=500, detail=f"服务器内部发生严重错误: {str(e)}\nTrace: {error_trace}")
