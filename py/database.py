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
    has_simplified_chinese = Column(Boolean, default=False, index=True)
    has_traditional_chinese = Column(Boolean, default=False, index=True)
    last_scanned = Column(DateTime, nullable=True, index=True)
    
    # --- 最终版字段 ---
    total_reviews_all_purchase_types = Column(Integer, default=0)
    chinese_reviews_all_purchase_types = Column(Integer, default=0)
    total_reviews_steam_purchase_only = Column(Integer, default=0)
    chinese_reviews_steam_purchase_only = Column(Integer, default=0)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def create_db_and_tables():
    Base.metadata.create_all(bind=engine)
