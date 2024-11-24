import os
from sqlalchemy import Column, Integer, String
from sqlalchemy.sql.sqltypes import Boolean
from database import Base

try:
    PREFIX = os.environ["PREFIX"]
except:
    PREFIX = "*"

class Clients(Base):
    __tablename__ = 'clients'
    id = Column(Integer, primary_key=True, index=True)
    guild_id = Column(Integer, index=True, nullable=False)
    notion_api_key = Column(String, nullable=False)
    prefix = Column(String, default=PREFIX)

    def __init__(self, guild_id, notion_api_key, prefix=PREFIX):
        self.guild_id = guild_id
        self.notion_api_key = notion_api_key
        self.prefix = prefix

    @property
    def serialize(self):
        return {
            "guild_id": self.guild_id,
            "notion_api_key": self.notion_api_key,
            "prefix": self.prefix,
        }

class NotionMonitorConfig(Base):
    __tablename__ = 'notion_monitors'
    id = Column(Integer, primary_key=True, index=True)
    guild_id = Column(Integer, index=True, nullable=False)
    channel_id = Column(Integer, nullable=False)
    database_id = Column(String, nullable=False)
    interval = Column(Integer, default=2)  # 监控间隔（分钟）
    display_columns = Column(String, nullable=False)  # JSON格式存储要显示的列
    is_active = Column(Boolean, default=False)
    last_checked = Column(String, nullable=True)

    def __init__(self, guild_id, channel_id, database_id, interval=2, display_columns="[]", is_active=False):
        self.guild_id = guild_id
        self.channel_id = channel_id
        self.database_id = database_id
        self.interval = interval
        self.display_columns = display_columns
        self.is_active = is_active
        self.last_checked = None

class NotionPageSnapshot(Base):
    __tablename__ = 'notion_page_snapshots'
    id = Column(Integer, primary_key=True, index=True)
    monitor_id = Column(Integer, nullable=False)  # 关联到NotionMonitorConfig的id
    page_id = Column(String, nullable=False)  # Notion页面ID
    content = Column(String, nullable=False)  # JSON格式存储页面内容
    last_updated = Column(String, nullable=False)  # 最后更新时间

    def __init__(self, monitor_id, page_id, content, last_updated):
        self.monitor_id = monitor_id
        self.page_id = page_id
        self.content = content
        self.last_updated = last_updated

class NotionDiscordUserMap(Base):
    __tablename__ = 'notion_discord_user_maps'
    id = Column(Integer, primary_key=True, index=True)
    guild_id = Column(Integer, nullable=False)
    notion_user_name = Column(String, nullable=False)
    discord_user_id = Column(String, nullable=False)

    def __init__(self, guild_id, notion_user_name, discord_user_id):
        self.guild_id = guild_id
        self.notion_user_name = notion_user_name
        self.discord_user_id = discord_user_id
