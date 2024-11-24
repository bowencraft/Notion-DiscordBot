import asyncio
import discord
from discord.ext import commands
from functionality import setupBot, utils
import os
from database import SessionLocal, engine
import models
import json
import functionality.utils as utils
import functionality.security as security

# database setup
db = SessionLocal()
models.Base.metadata.create_all(bind=engine)

# prefix data
prefix = ""
prefix_data = {}

# cogs
cogs = ["cogs.notion_monitor", "cogs.help"]

try:
    prefix = os.environ["PREFIX"]
except:
    prefix = "*"

try:
    token = os.environ["TOKEN"]
except:
    print("No token found, exiting...")
    exit()

# get prefixes from the database
def fillPrefix():
    global prefix_data
    prefix_data = {}
    monitors = db.query(models.NotionMonitorConfig).all()
    for monitor in monitors:
        prefix_data[str(monitor.guild_id)] = monitor.prefix

# get prefix of the guild that triggered bot
def get_prefix(client, message):
    global prefix_data
    try:
        prefix = prefix_data[str(message.guild.id)]
    except:
        prefix = "*"
    return prefix

fillPrefix()

bot = commands.Bot(command_prefix=(get_prefix), help_command=None)

# setup command
@bot.command(name="setup")
async def setup(ctx):
    """设置Notion API密钥和数据库"""
    monitor = await setupBot.setupConversation(ctx, bot)
    if monitor is not None:
        # 更新prefix_data
        prefix_data[str(monitor.guild_id)] = monitor.prefix

        embed = discord.Embed(
            description="已连接Notion数据库。",
            color=discord.Color.green(),
        )
        await ctx.send(embed=embed)
    else:
        embed = discord.Embed(
            title="设置失败",
            description="设置失败",
            color=discord.Color.red()
        )
        await ctx.send(embed=embed)

@bot.command(name="prefix")
async def changePrefix(ctx):
    """更改机器人的命令前缀"""
    monitor = db.query(models.NotionMonitorConfig).filter_by(
        guild_id=ctx.guild.id,
        channel_id=ctx.channel.id
    ).first()
    
    if not monitor:
        embed = discord.Embed(
            description=f"请先运行 `{prefix}setup` 设置此频道",
            color=discord.Color.red(),
        )
        await ctx.send(embed=embed)
        return

    current_prefix = monitor.prefix
    embed = discord.Embed(
        title="输入新的命令前缀",
        description=f"当前前缀是：{current_prefix}",
    )
    await ctx.send(embed=embed)

    try:
        msg = await bot.wait_for(
            "message",
            check=lambda message: message.author == ctx.author,
            timeout=60
        )
    except asyncio.TimeoutError:
        embed = discord.Embed(
            title="超时",
            description="您花费的时间太长",
            color=discord.Color.red(),
        )
        await ctx.send(embed=embed)
        return

    new_prefix = msg.content.strip()
    monitor.prefix = new_prefix
    try:
        db.commit()
    except Exception as e:
        print(e)
        await ctx.send("出错了，请重试！")
        return

    embed = discord.Embed(
        title="前缀更新成功",
        description=f"前缀已更改为 {new_prefix}",
        color=discord.Color.green(),
    )
    await ctx.send(embed=embed)

    # 更新prefix_data
    prefix_data[str(ctx.guild.id)] = new_prefix

# 加载所有cog
for cog in cogs:
    bot.load_extension(cog)

try:
    bot.run(token)
except Exception as e:
    print("No token...exiting!")
