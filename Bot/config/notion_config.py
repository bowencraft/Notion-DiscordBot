import os
from datetime import datetime

# Notion API Configuration
NOTION_TOKEN = os.getenv("NOTION_TOKEN")
DATABASE_ID = os.getenv("NOTION_DATABASE_ID")

# 初始化最后检查时间字典，用guild_id作为key
last_checked_times = {}

def get_last_checked(guild_id: str) -> str:
    """获取指定服务器的最后检查时间"""
    if guild_id not in last_checked_times:
        last_checked_times[guild_id] = datetime.utcnow().replace(microsecond=0).isoformat()
    return last_checked_times[guild_id]

def update_last_checked(guild_id: str) -> None:
    """更新指定服务器的最后检查时间"""
    last_checked_times[guild_id] = datetime.utcnow().replace(microsecond=0).isoformat() 