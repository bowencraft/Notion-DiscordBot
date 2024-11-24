import discord
from discord.ext import commands
from database import SessionLocal
import models
import os

try:
    PREFIX = os.environ["PREFIX"]
except:
    PREFIX = "*"

class Help(commands.Cog):
    def __init__(self, client):
        self.bot = client
        self.db = SessionLocal()

    @commands.command(name="help", aliases=["h"])
    async def help(self, ctx, *args):
        """显示命令列表"""
        # 检查频道是否已设置
        monitor = self.db.query(models.NotionMonitorConfig).filter_by(
            guild_id=ctx.guild.id,
            channel_id=ctx.channel.id
        ).first()
        
        if not monitor:
            embed = discord.Embed(
                description=f"请先运行 `{PREFIX}setup` 设置此频道",
                color=discord.Color.red(),
            )
            await ctx.send(embed=embed)
            return
        
        prefix = monitor.prefix
        commands = {
            f"```{prefix}setup```": "设置Notion API密钥和数据库",
            f"```{prefix}prefix```": "更改机器人的命令前缀",
            f"```{prefix}monitor_setup (或 ms)```": "设置新的Notion数据库监控",
            f"```{prefix}monitor_start (或 mstart)```": "启动当前频道的监控",
            f"```{prefix}monitor_stop (或 mstop)```": "停止当前频道的监控",
            f"```{prefix}notion_monitor (或 nm)```": "立即执行一次更新检查",
            f"```{prefix}monitor_config (或 mc)```": "查看当前监控配置",
            f"```{prefix}mc interval <分钟>```": "设置检查间隔时间",
            f"```{prefix}map_users (或 mu)```": "映射Notion用户ID到Discord用户"
        }

        embed = discord.Embed(
            title="命令列表:", 
            description="以下是机器人支持的命令", 
            color=discord.Color.green()
        )
        count = 1
        for command in commands:
            embed.add_field(
                name=str(count)+". "+ command, 
                value=commands[command], 
                inline=False
            )
            count += 1
        await ctx.send(embed=embed)

def setup(client):
    client.add_cog(Help(client))