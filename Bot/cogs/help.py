import discord
from discord.ext import commands
from functionality.utils import *
import os

try:
    PREFIX = os.environ["PREFIX"]
except:
    PREFIX = "*"

class Help(commands.Cog):
    def __init__(self, client):
        self.bot = client
        self.guild_data = self.bot.guild_info

    @commands.command(name="help", aliases=["h"])
    async def help(self, ctx, *args):
        """Give commands list"""
        # check if guild is present
        if not checkIfGuildPresent(ctx.guild.id):
            # embed send
            embed = discord.Embed(
                description="You are not registered, please run `" + PREFIX + "setup` first",
                title="",
                color=discord.Color.red(),
            )
            await ctx.send(embed=embed)
            return
        
        guild = self.guild_data[str(ctx.guild.id)]
        prefix = guild.prefix
        commands = {
            f"```{prefix}setup```": "设置Notion API密钥",
            f"```{prefix}prefix```": "更改机器人的命令前缀",
            f"```{prefix}monitor_setup (或 ms)```": "设置新的Notion数据库监控",
            f"```{prefix}monitor_start (或 mstart)```": "启动当前频道的监控",
            f"```{prefix}monitor_stop (或 mstop)```": "停止当前频道的监控",
            f"```{prefix}notion_monitor (或 nm)```": "立即执行一次更新检查",
            f"```{prefix}monitor_config (或 mc)```": "查看当前监控配置",
            f"```{prefix}mc interval <分钟>```": "设置检查间隔时间"
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