import discord
from discord.ext import commands, tasks
from datetime import datetime
import asyncio
from database import SessionLocal
import models
import functionality.utils as utils
from functionality.security import getKey
import requests
import json

class NotionMonitor(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = SessionLocal()
        self.last_checked = {}  # 用于存储每个公会的最后检查时间
        self.check_notion_updates.start()

        print("Initialized")
        
        # 添加自定义格式化配置
        self.format_config = {
            'show_contributor': True,
            'show_tags': True,
            'show_url': True,
            'show_edit_time': True,
            'embed_color': discord.Color.blue()
        }

    def cog_unload(self):
        self.check_notion_updates.cancel()

    @commands.command(name="notion_monitor", aliases=["nm"])
    @commands.has_permissions(administrator=True)
    async def manual_check(self, ctx):
        """立即执行一次Notion监控检查"""
        if not utils.checkIfGuildPresent(ctx.guild.id):
            embed = discord.Embed(
                description="请先运行 setup 命令进行设置",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
            return

        async with ctx.typing():
            guild_info = self.bot.guild_info[str(ctx.guild.id)]
            pages = self.get_notion_pages(guild_info, self.last_checked.get(str(ctx.guild.id), ""))
            
            if not pages:
                embed = discord.Embed(
                    description="没有发现新的更新",
                    color=discord.Color.green()
                )
                await ctx.send(embed=embed)
                return
                
            for page in pages:
                message = self.format_page_message(page)
                await ctx.send(embed=message)
                
            self.last_checked[str(ctx.guild.id)] = datetime.utcnow().isoformat()

    @commands.command(name="monitor_config", aliases=["mc"])
    @commands.has_permissions(administrator=True)
    async def configure_monitor(self, ctx, setting: str = None, value: str = None):
        """配置监控的显示设置"""
        if setting is None:
            # 显示当前配置
            embed = discord.Embed(
                title="当前监控配置",
                description="使用 `monitor_config <设置> <值>` 来修改配置",
                color=discord.Color.blue()
            )
            for key, value in self.format_config.items():
                embed.add_field(name=key, value=str(value), inline=False)
            await ctx.send(embed=embed)
            return
            
        setting = setting.lower()
        if setting not in self.format_config:
            await ctx.send("无效的设置选项。可用选项: " + ", ".join(self.format_config.keys()))
            return
            
        if setting in ['show_contributor', 'show_tags', 'show_url', 'show_edit_time']:
            value = value.lower() == 'true'
        elif setting == 'embed_color':
            try:
                value = getattr(discord.Color, value)()
            except:
                await ctx.send("无效的颜色值。请使用 discord.Color 支持的颜色名称。")
                return
                
        self.format_config[setting] = value
        await ctx.send(f"已更新设置 {setting} = {value}")

    @commands.command(name="set_notion_channel", aliases=["snc"])
    @commands.has_permissions(administrator=True)
    async def set_notion_channel(self, ctx, channel: discord.TextChannel = None):
        """设置Notion更新通知的目标频道"""
        if not utils.checkIfGuildPresent(ctx.guild.id):
            embed = discord.Embed(
                description="请先运行 setup 命令进行设置",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
            return

        if channel is None:
            if len(ctx.message.channel_mentions) > 0:
                channel = ctx.message.channel_mentions[0]
            else:
                embed = discord.Embed(
                    description="请提及一个频道（例如：#通知频道）",
                    color=discord.Color.red()
                )
                await ctx.send(embed=embed)
                return

        # 更新数据库
        client = self.db.query(models.Clients).filter_by(guild_id=ctx.guild.id).first()
        client.notion_channel = channel.id
        self.db.commit()

        # 更新guild_info
        self.bot.guild_info[str(ctx.guild.id)].notion_channel = channel.id

        embed = discord.Embed(
            description=f"已将Notion更新通知频道设置为 {channel.mention}",
            color=discord.Color.green()
        )
        await ctx.send(embed=embed)

    @tasks.loop(minutes=2)
    async def check_notion_updates(self):
        # print("开始检查更新")
        for guild_id, guild_info in self.bot.guild_info.items():
            try:
                if guild_id not in self.last_checked:
                    # 使用ISO 8601格式的UTC时间
                    self.last_checked[guild_id] = datetime.utcnow().isoformat() + "Z"
                    print(f"初始化公会 {guild_id} 的检查时间: {self.last_checked[guild_id]}")
                    continue

                print(f"检查公会 {guild_id} 的更新")
                print(f"上次检查时间: {self.last_checked[guild_id]}")
                
                pages = self.get_notion_pages(guild_info, self.last_checked[guild_id])
                
                if pages:
                    print(f"找到 {len(pages)} 个更新")
                    # 检查是否设置了通知频道
                    if not hasattr(guild_info, 'notion_channel') or guild_info.notion_channel is None:
                        print(f"公会 {guild_id} 未设置通知频道")
                        continue
                        
                    channel = self.bot.get_channel(int(guild_info.notion_channel))
                    if channel:
                        for page in pages:
                            message = self.format_page_message(page)
                            if message:  # 确保消息格式化成功
                                await channel.send(embed=message)
                    else:
                        print(f"找不到通知频道: {guild_info.notion_channel}")
                else:
                    print("没有找到更新")

                # 更新检查时间，添加Z表示UTC时间
                self.last_checked[guild_id] = datetime.utcnow().isoformat() + "Z"

            except Exception as e:
                print(f"检查公会 {guild_id} 的Notion更新时出错: {e}")
                import traceback
                traceback.print_exc()  # 打印完整的错误堆栈

    @check_notion_updates.before_loop
    async def before_check(self):
        await self.bot.wait_until_ready()

    def get_notion_pages(self, guild_info, last_checked):
        """获取自上次检查以来更新的Notion页面"""
        try:
            # print(f"上次检查时间: {last_checked}")
            
            url = "https://api.notion.com/v1/databases/" + guild_info.notion_db_id + "/query"
            headers = {
                'Authorization': guild_info.notion_api_key,
                'Notion-Version': '2021-08-16',
                'Content-Type': 'application/json'
            }
            
            query_data = {
                "filter": {
                    "timestamp": "last_edited_time",
                    "last_edited_time": {
                        "after": last_checked
                    }
                },
                "sorts": [
                    {
                        "timestamp": "last_edited_time",
                        "direction": "descending"
                    }
                ]
            }
            
            print(f"正在查询Notion数据库: {guild_info.notion_db_id}")
            print(f"查询条件: {json.dumps(query_data, indent=2)}")
            
            payload = json.dumps(query_data)
            response = requests.post(url, headers=headers, data=payload)
            
            print(f"Notion API响应状态码: {response.status_code}")
            if response.status_code == 200:
                result = response.json()
                # print(f"找到 {len(result.get('results', []))} 条更新")
                return result.get("results", [])
            else:
                print(f"Notion API错误响应: {response.text}")
                return []
                
        except Exception as e:
            print(f"从Notion获取页面时出错: {e}")
            return []

    def format_page_message(self, page):
        """将Notion页面格式化为Discord消息"""
        try:
            # 获取标题
            title = "无标题"
            if "Title" in page["properties"]:
                title_prop = page["properties"]["Title"]
                if title_prop.get("rich_text") and len(title_prop["rich_text"]) > 0:
                    if "text" in title_prop["rich_text"][0]:
                        title = title_prop["rich_text"][0]["text"].get("content", "无标题")
            
            # 创建自定义的 Embed
            embed = discord.Embed(
                title="📝 Notion页面更新",  # 修改标题
                description=f"**{title}**",  # 修改描述格式
                color=self.format_config['embed_color'],
                timestamp=datetime.fromisoformat(page.get("last_edited_time", "").replace("Z", "+00:00"))  # 添加时间戳
            )
            
            # 添加缩略图
            embed.set_thumbnail(url="你的缩略图URL")
            
            # 添加页脚
            embed.set_footer(text="Notion Monitor Bot", icon_url="你的图标URL")
            
            # 自定义字段显示
            if self.format_config['show_url']:
                url = page.get("url", "")
                if url:
                    embed.add_field(name="🔗 链接", value=f"[点击查看]({url})", inline=False)
            
            if self.format_config['show_contributor'] and "Contributor" in page["properties"]:
                contributor_prop = page["properties"]["Contributor"]
                contributor = "未知"
                if contributor_prop.get("title") and len(contributor_prop["title"]) > 0:
                    if "text" in contributor_prop["title"][0]:
                        contributor = contributor_prop["title"][0]["text"].get("content", "未知")
                embed.add_field(name="👤 贡献者", value=contributor, inline=True)
            
            if self.format_config['show_tags'] and "Tag" in page["properties"]:
                tag_prop = page["properties"]["Tag"]
                if tag_prop.get("multi_select"):
                    tags = [tag.get("name", "") for tag in tag_prop["multi_select"] if tag.get("name")]
                    if tags:
                        embed.add_field(name="🏷️ 标签", value=", ".join(tags), inline=True)
            
            if self.format_config['show_edit_time']:
                edit_time = page.get("last_edited_time", "未知").split("T")[0]
                embed.add_field(name="⏰ 更新时间", value=edit_time, inline=True)
            
            return embed
            
        except Exception as e:
            print(f"格式化页面消息时出错: {e}")
            print(f"页面数据: {json.dumps(page, indent=2)}")
            return None

def setup(bot):
    bot.add_cog(NotionMonitor(bot)) 