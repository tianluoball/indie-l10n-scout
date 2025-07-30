# ------------------------------------------------------------------
# py/main.py (最终完整版)
# ------------------------------------------------------------------
import os
import datetime
import json
import time
import traceback
import requests
from dotenv import load_dotenv
from fastapi import FastAPI, Depends, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import func, or_, desc

from database import get_db, SteamGame, create_db_and_tables
from scanner import process_single_game, ALL_STEAM_LANGUAGES, CORE_LANGUAGES

# 确保在程序开始时加载环境变量
load_dotenv()
create_db_and_tables()

app = FastAPI(
    title="Indie Game Localization Opportunity Finder",
    description="一个用于分析Steam游戏本地化潜力的API"
)

# CORS (跨域资源共享) 设置，允许前端访问
origins = ["http://localhost", "http://127.0.0.1", "http://doko-doa.local", "null"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- API 端点 ---

@app.get("/validate_api_key")
def validate_api_key(api_key: str):
    """验证用户提供的Steam API Key是否有效。"""
    if not api_key:
        raise HTTPException(status_code=400, detail="API key cannot be empty.")
    validation_url = "https://api.steampowered.com/ISteamWebAPIUtil/GetServerInfo/v1/"
    try:
        response = requests.get(validation_url, params={'key': api_key}, timeout=10)
        if response.status_code == 200:
            return {"status": "valid", "message": "API Key is valid."}
        elif response.status_code == 403:
            raise HTTPException(status_code=403, detail="Invalid API Key provided.")
        else:
            raise HTTPException(status_code=response.status_code, detail=f"Steam API returned status {response.status_code}.")
    except requests.exceptions.RequestException as e:
        raise HTTPException(status_code=500, detail=f"Failed to connect to Steam API: {e}")

@app.get("/get_languages")
def get_languages(full_list: bool = False):
    """根据请求返回核心语言列表或全部语言列表。"""
    if full_list:
        return ALL_STEAM_LANGUAGES
    return CORE_LANGUAGES

def update_games_on_demand(app_ids: list[int], language: str, db: Session, api_key: str):
    """使用用户的API Key按需更新指定游戏和语言的数据。"""
    print(f"--- 即时更新任务启动 (使用用户Key): 语言 '{language}', AppIDs: {app_ids} ---")
    for app_id in app_ids:
        game = db.query(SteamGame).filter(SteamGame.app_id == app_id).first()
        if not game:
            continue
        process_single_game(game, db, languages_to_scan=[language], force_details_update=True, api_key=api_key)
        db.commit()
        db.refresh(game)
    print("--- 即时更新任务完成 ---")

@app.get("/search", response_model=list[dict])
def search_games(query: str, db: Session = Depends(get_db)):
    """根据关键词搜索游戏。"""
    if not query:
        return []
    search_query = f"%{query}%"
    found_games = db.query(SteamGame).filter(SteamGame.name.ilike(search_query)).limit(10).all()
    return [{"name": g.name, "appid": g.app_id} for g in found_games]

@app.get("/analyze_by_tags", response_model=dict)
def analyze_by_tags(
    tags: str = Query(..., description="用户输入的标签，用逗号或分号分隔。"),
    language: str = Query(..., description="目标分析语言的代码，例如 'schinese'。"),
    db: Session = Depends(get_db)
):
    """
    根据用户输入的自定义标签（Tags）进行本地化潜力分析。
    """
    # 1. 解析用户输入的标签字符串
    raw_tags = tags.replace(';', ',') # 将分号也替换为逗号
    user_tags = [t.strip() for t in raw_tags.split(',') if t.strip()]
    
    if not user_tags:
        raise HTTPException(status_code=400, detail="输入的标签列表为空，请至少提供一个标签。")

    # 2. 获取语言全名以用于查询
    lang_code_to_name_map = {
        "schinese": "Simplified Chinese", "tchinese": "Traditional Chinese", "japanese": "Japanese", "koreana": "Korean",
        # ... (这里省略了所有语言的映射，请从你的analyze_game_v2函数中复制过来) ...
    }
    language_fullname_for_query = lang_code_to_name_map.get(language, language)

    # 3. 构建相似性比较查询
    # 使用你现有的逻辑来匹配至少一个标签
    # 注意：这里直接使用 user_tags 作为匹配条件
    base_comparison_query = db.query(SteamGame).filter(
        SteamGame.tags.isnot(None), 
        SteamGame.tags != '',
        SteamGame.total_reviews_all_purchase_types > 10,
        func.string_to_array(SteamGame.tags, ',').op('&&')(user_tags)
    )

    # 4. 根据语言支持情况进行分组
    with_lang_query = base_comparison_query.filter(SteamGame.supported_languages.ilike(f"%{language_fullname_for_query}%"))
    without_lang_query = base_comparison_query.filter(func.coalesce(SteamGame.supported_languages, '').not_ilike(f"%{language_fullname_for_query}%"))

    # 5. 执行分析并返回结果
    avg_with_language = with_lang_query.with_entities(func.avg(SteamGame.total_reviews_all_purchase_types)).scalar() or 0
    with_language_examples = with_lang_query.order_by(desc(SteamGame.total_reviews_all_purchase_types)).limit(3).all()
    avg_without_language = without_lang_query.with_entities(func.avg(SteamGame.total_reviews_all_purchase_types)).scalar() or 0
    without_language_examples = without_lang_query.order_by(desc(SteamGame.total_reviews_all_purchase_types)).limit(3).all()

    # 格式化示例的辅助函数
    def format_examples(games: list[SteamGame], target_language_code: str) -> list[dict]:
        results = []
        for g in games:
            lang_reviews_dict = {}
            try:
                lang_reviews_dict = json.loads(g.language_reviews) if g.language_reviews else {}
            except (json.JSONDecodeError, TypeError):
                pass
            results.append({
                "app_id": g.app_id, "name": g.name,
                "total_reviews_all_purchase_types": g.total_reviews_all_purchase_types,
                "language_specific_reviews": lang_reviews_dict.get(target_language_code, 0)
            })
        return results

    return {
        "query": {
            "tags": user_tags,
            "language": language,
        },
        "comparison": {
            "analyzed_language": language,
            "avg_reviews_with_language": round(avg_with_language),
            "avg_reviews_without_language": round(avg_without_language),
            "with_language_examples": format_examples(with_language_examples, language),
            "without_language_examples": format_examples(without_language_examples, language),
        }
    }


@app.get("/analyze/v2/{app_id}", response_model=dict)
def analyze_game_v2(
    app_id: int,
    language: str,  # 这是API代码，如 'schinese'
    db: Session = Depends(get_db),
    user_api_key: str | None = None
):
    """核心分析接口，支持默认模式和使用用户Key的实时模式。"""
    lang_code_to_name_map = {
        "schinese": "Simplified Chinese", "tchinese": "Traditional Chinese", "japanese": "Japanese", "koreana": "Korean",
        "thai": "Thai", "bulgarian": "Bulgarian", "czech": "Czech", "danish": "Danish", "german": "German",
        "spanish": "Spanish - Spain", "latam": "Spanish - Latin America", "greek": "Greek", "french": "French",
        "italian": "Italian", "indonesian": "Indonesian", "hungarian": "Hungarian", "dutch": "Dutch", "norwegian": "Norwegian",
        "polish": "Polish", "portuguese": "Portuguese - Portugal", "brazilian": "Portuguese - Brazil", "romanian": "Romanian",
        "russian": "Russian", "finnish": "Finnish", "swedish": "Swedish", "turkish": "Turkish", "vietnamese": "Vietnamese",
        "ukrainian": "Ukrainian", "english": "English", "arabic": "Arabic"
    }
    language_fullname_for_query = lang_code_to_name_map.get(language, language)

    try:
        if not user_api_key and language not in CORE_LANGUAGES:
            raise HTTPException(status_code=403, detail=f"分析 '{language}' 语言需要提供有效的Steam API Key。")

        target_game = db.query(SteamGame).filter(SteamGame.app_id == app_id).first()
        if not target_game:
            raise HTTPException(status_code=404, detail="数据库中未找到该游戏。")

        if not target_game.tags and user_api_key:
            update_games_on_demand([app_id], language, db, api_key=user_api_key)
            target_game = db.query(SteamGame).filter(SteamGame.app_id == app_id).first()

        if not target_game.tags:
            raise HTTPException(status_code=400, detail="游戏标签数据为空，无法进行对比分析。")

        target_tags = [tag.strip() for tag in target_game.tags.split(',') if tag.strip()]
        base_comparison_query = db.query(SteamGame).filter(
            SteamGame.app_id != app_id, SteamGame.tags.isnot(None), SteamGame.tags != '',
            SteamGame.total_reviews_all_purchase_types > 10,
            func.string_to_array(SteamGame.tags, ',').op('&&')(target_tags)
        )
        with_lang_query = base_comparison_query.filter(SteamGame.supported_languages.ilike(f"%{language_fullname_for_query}%"))
        without_lang_query = base_comparison_query.filter(func.coalesce(SteamGame.supported_languages, '').not_ilike(f"%{language_fullname_for_query}%"))

        if user_api_key:
            with_language_examples_pre = with_lang_query.order_by(desc(SteamGame.total_reviews_all_purchase_types)).limit(3).all()
            without_language_examples_pre = without_lang_query.order_by(desc(SteamGame.total_reviews_all_purchase_types)).limit(3).all()
            app_ids_to_update = {g.app_id for g in with_language_examples_pre} | {g.app_id for g in without_language_examples_pre} | {target_game.app_id}
            update_games_on_demand(list(app_ids_to_update), language, db, api_key=user_api_key)

        def format_examples(games: list[SteamGame]) -> list[dict]:
            results = []
            for g in games:
                try:
                    lang_reviews_dict = json.loads(g.language_reviews) if g.language_reviews else {}
                except:
                    lang_reviews_dict = {}
                results.append({
                    "app_id": g.app_id, "name": g.name,
                    "total_reviews_all_purchase_types": g.total_reviews_all_purchase_types,
                    "language_specific_reviews": lang_reviews_dict.get(language, 0)
                })
            return results

        target_game = db.query(SteamGame).filter(SteamGame.app_id == app_id).first()
        avg_with_language = with_lang_query.with_entities(func.avg(SteamGame.total_reviews_all_purchase_types)).scalar() or 0
        with_language_examples = with_lang_query.order_by(desc(SteamGame.total_reviews_all_purchase_types)).limit(3).all()
        avg_without_language = without_lang_query.with_entities(func.avg(SteamGame.total_reviews_all_purchase_types)).scalar() or 0
        without_language_examples = without_lang_query.order_by(desc(SteamGame.total_reviews_all_purchase_types)).limit(3).all()

        supported_languages_list = [lang.strip().lower() for lang in (target_game.supported_languages or "").split(',')]
        language_reviews_dict = json.loads(target_game.language_reviews) if target_game.language_reviews else {}

        return {
            "target_game": {
                "name": target_game.name, "app_id": target_game.app_id, "tags": target_tags,
                "has_target_language": language_fullname_for_query.lower() in supported_languages_list,
                "supported_languages": supported_languages_list,
                "total_reviews_all_purchase_types": target_game.total_reviews_all_purchase_types,
                "language_reviews": language_reviews_dict,
            },
            "comparison": {
                "analyzed_language": language,
                "avg_reviews_with_language": round(avg_with_language),
                "avg_reviews_without_language": round(avg_without_language),
                "with_language_examples": format_examples(with_language_examples),
                "without_language_examples": format_examples(without_language_examples),
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"服务器内部发生严重错误: {traceback.format_exc()}")