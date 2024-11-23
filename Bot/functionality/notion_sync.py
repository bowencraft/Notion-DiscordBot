import asyncio
from datetime import datetime
import logging
from typing import List, Dict
from notion_client import Client
import discord
from config.notion_config import get_last_checked, update_last_checked

# 设置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Notion客户端缓存
notion_clients: Dict[str, Client] = {}

def get_notion_client(api_key: str) -> Client:
    """获取或创建Notion客户端"""
    if api_key not in notion_clients:
        notion_clients[api_key] = Client(auth=api_key)
    return notion_clients[api_key]

async def get_notion_pages(guild_id: str, api_key: str, database_id: str) -> List[dict]:
    """获取指定服务器的Notion数据库更新"""
    try:
        notion = get_notion_client(api_key)
        last_checked = get_last_checked(guild_id)
        
        pages = notion.databases.query(
            **{
                "database_id": database_id,
                "filter": {
                    "and": [
                        {
                            "timestamp": "last_edited_time",
                            "last_edited_time": {"after": last_checked},
                        }
                    ]
                },
            }
        ).get("results")
        
        update_last_checked(guild_id)
        logger.info(f"Guild {guild_id} checked at: {get_last_checked(guild_id)}")
        return pages
    except Exception as e:
        logger.error(f"Error fetching pages from Notion for guild {guild_id}: {e}")
        return []

def format_page_message(page: dict) -> str:
    """格式化Notion页面信息为Discord消息"""
    try:
        # 适配现有数据库结构
        title = page["properties"]["Title"]["rich_text"][0]["text"]["content"]
        url = page["properties"]["URL"]["url"]
        contributor = page["properties"]["Contributor"]["title"][0]["text"]["content"]
        
        message = f"**新更新**\n标题: {title}\n链接: {url}\n贡献者: {contributor}"
        
        # 如果有标签，也显示出来
        if "Tag" in page["properties"]:
            tags = [tag["name"] for tag in page["properties"]["Tag"]["multi_select"]]
            if tags:
                message += f"\n标签: {', '.join(tags)}"
                
        return message
    except Exception as e:
        logger.error(f"Error formatting page message: {e}")
        return "无法获取更新内容"

async def poll_notion_database(bot: discord.Client) -> None:
    """轮询所有服务器的Notion数据库"""
    while True:
        try:
            # 遍历所有已配置的服务器
            for guild_id, guild_info in bot.guild_info.items():
                if hasattr(guild_info, 'notion_api_key') and hasattr(guild_info, 'notion_db_id'):
                    pages = await get_notion_pages(
                        guild_id,
                        guild_info.notion_api_key,
                        guild_info.notion_db_id
                    )
                    
                    # 获取通知频道
                    if hasattr(guild_info, 'notification_channel_id'):
                        channel = bot.get_channel(guild_info.notification_channel_id)
                        if channel:
                            for page in pages:
                                message = format_page_message(page)
                                await channel.send(message)
                
            await asyncio.sleep(120)  # 每2分钟检查一次
        except Exception as e:
            logger.error(f"Error in poll_notion_database: {e}")
            await asyncio.sleep(120) 