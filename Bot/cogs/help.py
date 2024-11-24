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
        commands = {}
        if guild.tag:
            # check if the guild has tags enabled
            commands = {
                f"```{prefix}add <URL> <Tag 1> <Tag2>...<TagN>```": "添加URL到数据库并设置标签",
                f"```{prefix}search <Tag 1> <Tag2>...<TagN>```": "搜索包含指定标签的记录",
                f"```{prefix}searchTitle <Title>```": "按标题搜索记录",
                f"```{prefix}delete <Tag1> <Tag2>....<TagN>```": "删除包含指定标签的记录",
                f"```{prefix}deleteTitle <Title>```": "按标题删除记录",
                f"```{prefix}upload <Tag 1> <Tag2>...<TagN>```": "上传文件到Notion数据库并设置标签",
                f"```{prefix}prefix```": "更改机器人的命令前缀",
                # 添加新的监控相关命令
                f"```{prefix}monitor_setup (或 ms)```": "设置Notion数据库监控，包括选择数据库、监控间隔和显示列",
                f"```{prefix}monitor_start (或 mstart)```": "启动当前频道的Notion监控",
                f"```{prefix}monitor_stop (或 mstop)```": "停止当前频道的Notion监控",
                f"```{prefix}notion_monitor (或 nm)```": "立即执行一次Notion更新检查",
                f"```{prefix}monitor_config (或 mc)```": "查看或修改监控显示设置",
                f"```{prefix}mc show_contributor true/false```": "显示/隐藏贡献者信息",
                f"```{prefix}mc show_tags true/false```": "显示/隐藏标签信息",
                f"```{prefix}mc show_url true/false```": "显示/隐藏URL链接",
                f"```{prefix}mc show_edit_time true/false```": "显示/隐藏编辑时间",
                f"```{prefix}mc embed_color <颜色>```": "设置消息卡片颜色"
            }
        else:
            # no tags enabled
            commands = {
                f"```{prefix}add <URL>```": "添加URL到数据库",
                f"```{prefix}search <Title>```": "按标题搜索记录",
                f"```{prefix}delete <Title>```": "按标题删除记录",
                f"```{prefix}upload```": "上传文件到Notion数据库",
                f"```{prefix}prefix```": "更改机器人的命令前缀",
                # 添加新的监控相关命令
                f"```{prefix}monitor_setup (或 ms)```": "设置Notion数据库监控，包括选择数据库、监控间隔和显示列",
                f"```{prefix}monitor_start (或 mstart)```": "启动当前频道的Notion监控",
                f"```{prefix}monitor_stop (或 mstop)```": "停止当前频道的Notion监控",
                f"```{prefix}notion_monitor (或 nm)```": "立即执行一次Notion更新检查",
                f"```{prefix}monitor_config (或 mc)```": "查看或修改监控显示设置",
                f"```{prefix}mc show_contributor true/false```": "显示/隐藏贡献者信息",
                f"```{prefix}mc show_tags true/false```": "显示/隐藏标签信息",
                f"```{prefix}mc show_url true/false```": "显示/隐藏URL链接",
                f"```{prefix}mc show_edit_time true/false```": "显示/隐藏编辑时间",
                f"```{prefix}mc embed_color <颜色>```": "设置消息卡片颜色"
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