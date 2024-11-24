import os
from sqlalchemy import Column, Integer, String
from sqlalchemy.sql.expression import null
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
    notion_db_id = Column(String, nullable=False)
    tag = Column(Boolean, default=False)
    prefix = Column(String, default=PREFIX)
    notion_channel = Column(Integer, nullable=True)

    def __init__(self, guild_id, notion_api_key, notion_db_id, tag, prefix=PREFIX, notion_channel=None):
        self.guild_id = guild_id
        self.notion_api_key = notion_api_key
        self.notion_db_id = notion_db_id
        self.tag = tag
        self.prefix = prefix
        self.notion_channel = notion_channel

    @property
    def serialize(self):
        return {
            "guild_id": self.guild_id,
            "notion_api_key": self.notion_api_key,
            "notion_db_id": self.notion_db_id,
            "tag": self.tag,
            "prefix": self.prefix,
            "notion_channel": self.notion_channel,
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
