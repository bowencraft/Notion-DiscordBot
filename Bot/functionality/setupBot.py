import asyncio
import discord
import requests
from database import SessionLocal, engine
import models
from functionality.security import *

db = SessionLocal()

# TODO: Use discord component buttons to make this more user friendly


async def verifyDetails(notion_api_key, notion_db_id, ctx):
    url = "https://api.notion.com/v1/databases/" + notion_db_id
    headers = {
        "Authorization": notion_api_key,
        "Notion-Version": "2021-05-13",
        "Content-Type": "application/json",
    }
    res = requests.get(url, headers=headers)
    if res.status_code != 200:
        res = res.json()
        if res["code"] == "unauthorized":
            await ctx.send("Invalid Notion API key")
            return False
        elif res["code"] == "object_not_found":
            await ctx.send("Invalid Notion database id")
            return False
        else:
            print(res)
            return False
    else:
        return True


async def setupConversation(ctx, bot):
    """
    获取Notion API密钥并设置
    """
    guild_id = ctx.guild.id
    embed = discord.Embed(description="请输入Notion API密钥")
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

    # 如果guild已存在，更新它
    client = db.query(models.Clients).filter(models.Clients.guild_id == guild_id).first()
    if client:
        client.notion_api_key = encrypt(notion_api_key)
        db.commit()
        embed = discord.Embed(
            title="更新成功",
            description="设置已更新",
            color=discord.Color.green(),
        )
        await ctx.send(embed=embed)

        # 创建返回对象
        obj = models.Clients(
            guild_id=guild_id,
            notion_api_key=notion_api_key,
        )
        return obj

    # 如果是新guild，创建新记录
    new_client = models.Clients(
        guild_id=guild_id,
        notion_api_key=encrypt(notion_api_key),
    )

    obj = models.Clients(
        guild_id=guild_id,
        notion_api_key=notion_api_key,
    )
    db.add(new_client)
    db.commit()
    return obj
