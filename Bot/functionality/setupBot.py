import asyncio
import discord
import requests
from database import SessionLocal, engine
import models
from functionality.security import *
import os

db = SessionLocal()

try:
    PREFIX = os.environ["PREFIX"]
except:
    PREFIX = "*"

async def verifyDetails(notion_api_key, ctx):
    """验证API密钥是否有效"""
    headers = {
        "Authorization": notion_api_key,
        "Notion-Version": "2021-05-13",
        "Content-Type": "application/json",
    }
    # 尝试获取用户信息来验证API密钥
    url = "https://api.notion.com/v1/users/me"
    res = requests.get(url, headers=headers)
    if res.status_code != 200:
        res = res.json()
        if res["code"] == "unauthorized":
            await ctx.send("无效的Notion API密钥")
            return False
        else:
            print(res)
            return False
    return True

async def setupConversation(ctx, bot):
    """
    设置频道的Notion API密钥
    """
    guild_id = ctx.guild.id
    channel_id = ctx.channel.id

    # 检查是否已经设置过
    monitor = db.query(models.NotionMonitorConfig).filter_by(
        guild_id=guild_id,
        channel_id=channel_id
    ).first()

    embed = discord.Embed(description="请输入此频道使用的Notion API密钥")
    await ctx.send(embed=embed)
    try:
        msg = await bot.wait_for(
            "message",
            check=lambda message: message.author == ctx.author,
            timeout=60,
        )
    except asyncio.TimeoutError:
        embed = discord.Embed(
            title="超时",
            description="设置超时，请重新开始",
            color=discord.Color.red(),
        )
        await ctx.send(embed=embed)
        return
    notion_api_key = msg.content.strip()

    # 验证API密钥
    if not notion_api_key.startswith('ntn_'):
        embed = discord.Embed(
            title="错误",
            description="无效的Notion API密钥",
            color=discord.Color.red(),
        )
        await ctx.send(embed=embed)
        return None

    # 验证API密钥是否有效
    if not await verifyDetails(notion_api_key, ctx):
        return None

    # 如果已存在配置，更新它
    if monitor:
        monitor.notion_api_key = notion_api_key
        db.commit()
        embed = discord.Embed(
            title="更新成功",
            description=f"已更新频道 {ctx.channel.mention} 的API密钥",
            color=discord.Color.green(),
        )
        await ctx.send(embed=embed)
    else:
        # 创建新配置
        monitor = models.NotionMonitorConfig(
            guild_id=guild_id,
            channel_id=channel_id,
            notion_api_key=notion_api_key,
            database_id="",  # 空数据库ID，等待ms命令设置
            is_active=False  # 默认不激活，需要使用ms命令设置
        )
        db.add(monitor)
        db.commit()
        embed = discord.Embed(
            title="设置成功",
            description=f"已为频道 {ctx.channel.mention} 设置Notion API密钥\n"
                       f"请使用 `{PREFIX}ms` 命令设置要监控的数据库",
            color=discord.Color.green(),
        )
        await ctx.send(embed=embed)

    return monitor
