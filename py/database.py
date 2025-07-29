# database.py

import os
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Boolean, Text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base
from dotenv import load_dotenv
import datetime

load_dotenv()
SQLALCHEMY_DATABASE_URL = os.getenv("DATABASE_URL")
engine = create_engine(SQLALCHEMY_DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class GameOpportunity(Base):
    __tablename__ = "game_opportunities"
    app_id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    last_checked = Column(DateTime, default=datetime.datetime.utcnow)
    chinese_review_count = Column(Integer)
    keyword_mentions = Column(Integer)

class SteamGame(Base):
    __tablename__ = "steam_games"
    app_id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    tags = Column(Text, nullable=True)
    # 修改开始
    supported_languages = Column(Text, nullable=True)  # 新增: 通用语言字段
    language_reviews = Column(Text, nullable=True) # 新增: 存储不同语言评测数 (JSON格式字符串)
    # 修改结束
    last_scanned = Column(DateTime, nullable=True, index=True)
    
    # --- 最终版字段 ---
    total_reviews_all_purchase_types = Column(Integer, default=0)
    total_reviews_steam_purchase_only = Column(Integer, default=0)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def create_db_and_tables():
    Base.metadata.create_all(bind=engine)