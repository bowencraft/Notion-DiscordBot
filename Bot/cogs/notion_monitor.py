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
import aiohttp

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

    def parse_iso_datetime(self, iso_string):
        """解析ISO格式的时间字符串"""
        try:
            # 移除Z后缀并添加UTC时区标识
            iso_string = iso_string.replace('Z', '+00:00')
            # 分离日期和时间
            date_part, time_part = iso_string.split('T')
            year, month, day = map(int, date_part.split('-'))
            
            # 处理时间部分
            time_part = time_part.split('+')[0]  # 移除时区部分
            hour, minute, second = map(float, time_part.split(':'))
            
            return datetime(year, month, day, 
                          int(hour), int(minute), int(float(second)),
                          int((float(second) % 1) * 1000000))
        except Exception as e:
            print(f"解析时间字符串失败: {e}")
            return datetime.utcnow()

    @tasks.loop(minutes=1)
    async def check_notion_updates(self):
        """检查所有活动的监控配置"""
        monitors = self.db.query(models.NotionMonitorConfig).filter_by(is_active=True).all()
        
        for monitor in monitors:
            try:
                # 检查是否到达检查间隔
                if monitor.last_checked:
                    last_check = self.parse_iso_datetime(monitor.last_checked)
                    if (datetime.utcnow() - last_check).total_seconds() < monitor.interval * 60:
                        continue

                # 获取更新
                guild_info = self.bot.guild_info[str(monitor.guild_id)]
                pages = self.get_notion_pages(guild_info, monitor.last_checked)
                if pages:
                    channel = self.bot.get_channel(monitor.channel_id)
                    if channel:
                        for page in pages:
                            message = self.format_page_message(page, json.loads(monitor.display_columns))
                            if message:
                                await channel.send(embed=message)

                # 更新检查时间
                monitor.last_checked = datetime.utcnow().isoformat() + 'Z'
                self.db.commit()

            except Exception as e:
                print(f"检查监控 {monitor.id} 时出错: {e}")
                import traceback
                traceback.print_exc()  # 打印完整的错误堆栈

    @check_notion_updates.before_loop
    async def before_check(self):
        await self.bot.wait_until_ready()

    def get_notion_pages(self, guild_info, last_checked):
        """获取自上次检查以来更新的Notion页面"""
        try:
            print(f"上次检查时间: {last_checked}")
            
            url = "https://api.notion.com/v1/databases/" + guild_info.notion_db_id + "/query"
            headers = {
                'Authorization': guild_info.notion_api_key,
                'Notion-Version': '2021-08-16',
                'Content-Type': 'application/json'
            }
            
            query_data = {
                "filter": {
                    "and": [
                        {
                            "timestamp": "last_edited_time",
                            "last_edited_time": {
                                "after": last_checked
                            }
                        }
                    ]
                }
            }
            
            print(f"正在查询Notion数据库: {guild_info.notion_db_id}")
            print(f"查询条件: {json.dumps(query_data, indent=2)}")
            
            payload = json.dumps(query_data)
            response = requests.post(url, headers=headers, data=payload)
            
            print(f"Notion API响应状态码: {response.status_code}")
            if response.status_code == 200:
                result = response.json()
                print(f"找到 {len(result.get('results', []))} 条更新")
                return result.get("results", [])
            else:
                print(f"Notion API错误响应: {response.text}")
                return []
                
        except Exception as e:
            print(f"从Notion获取页面时出错: {e}")
            return []

    def format_page_message(self, page, selected_columns=None):
        """将Notion页面格式化为Discord消息"""
        try:
            # 解析时间戳
            last_edited_time = page.get("last_edited_time", "")
            if last_edited_time:
                timestamp = self.parse_iso_datetime(last_edited_time)
            else:
                timestamp = datetime.utcnow()

            embed = discord.Embed(
                title="📝 Notion更新通知",
                color=self.format_config['embed_color'],
                timestamp=timestamp
            )
            
            # 如果没有指定列，使用默认格式
            if not selected_columns:
                return self.format_default_message(page, embed)
            
            # 处理选定的列
            for column in selected_columns:
                if column in page["properties"]:
                    value = self.format_property_value(page["properties"][column])
                    if value:
                        embed.add_field(name=column, value=value, inline=True)
            
            # 添加页面链接
            url = page.get("url", "")
            if url:
                embed.url = url
                
            return embed
            
        except Exception as e:
            print(f"格式化页面消息时出错: {e}")
            print(f"页面数据: {json.dumps(page, indent=2)}")
            return None

    def format_property_value(self, property_data):
        """格式化Notion属性值"""
        try:
            property_type = property_data.get("type")
            if not property_type:
                return None
                
            if property_type == "title" or property_type == "rich_text":
                text_list = property_data.get(property_type, [])
                if text_list and len(text_list) > 0:
                    return text_list[0]["text"]["content"]
                    
            elif property_type == "select":
                select_data = property_data.get("select")
                if select_data:
                    return select_data.get("name")
                    
            elif property_type == "multi_select":
                multi_select = property_data.get("multi_select", [])
                return ", ".join([item["name"] for item in multi_select if "name" in item])
                
            elif property_type == "date":
                date_data = property_data.get("date")
                if date_data:
                    return date_data.get("start")
                    
            elif property_type == "number":
                return str(property_data.get("number"))
                
            elif property_type == "url":
                return property_data.get("url")
                
            return str(property_data.get(property_type, ""))
            
        except Exception as e:
            print(f"格式化属性值时出错: {e}")
            return None

    def format_default_message(self, page, embed):
        """使用默认格式创建消息"""
        try:
            # 获取标题
            title = "无标题"
            if "Title" in page["properties"]:
                title = self.format_property_value(page["properties"]["Title"]) or "无标题"
            
            embed.description = f"**{title}**"
            
            # 添加URL
            if self.format_config['show_url']:
                url = page.get("url", "")
                if url:
                    embed.add_field(name="🔗 链接", value=f"[点击查看]({url})", inline=False)
            
            # 添加贡献者
            if self.format_config['show_contributor'] and "Contributor" in page["properties"]:
                contributor = self.format_property_value(page["properties"]["Contributor"]) or "未知"
                embed.add_field(name="👤 贡献者", value=contributor, inline=True)
            
            # 添加标签
            if self.format_config['show_tags'] and "Tag" in page["properties"]:
                tags = self.format_property_value(page["properties"]["Tag"])
                if tags:
                    embed.add_field(name="🏷️ 标签", value=tags, inline=True)
            
            # 添加编辑时间
            if self.format_config['show_edit_time']:
                edit_time = page.get("last_edited_time", "未知").split("T")[0]
                embed.add_field(name="⏰ 更新时间", value=edit_time, inline=True)
            
            return embed
            
        except Exception as e:
            print(f"格式化默认消息时出错: {e}")
            return None

    @commands.command(name="monitor_setup", aliases=["ms"])
    @commands.has_permissions(administrator=True)
    async def setup_monitor(self, ctx):
        """设置Notion数据库监控"""
        try:
            # 检查是否已经设置过
            monitor = self.db.query(models.NotionMonitorConfig).filter_by(
                guild_id=ctx.guild.id,
                channel_id=ctx.channel.id
            ).first()

            # 获取数据库ID
            embed = discord.Embed(description="请输入要监控的Notion数据库ID")
            await ctx.send(embed=embed)
            msg = await self.bot.wait_for(
                "message",
                check=lambda m: m.author == ctx.author and m.channel == ctx.channel,
                timeout=60
            )
            database_id = msg.content.strip()

            # 获取监控间隔
            embed = discord.Embed(description="请输入监控间隔（分钟，建议不小于2分钟）")
            await ctx.send(embed=embed)
            msg = await self.bot.wait_for(
                "message",
                check=lambda m: m.author == ctx.author and m.channel == ctx.channel,
                timeout=60
            )
            interval = int(msg.content.strip())

            # 获取数据库结构
            db_structure = await self.get_database_structure(ctx.guild.id, database_id)
            if not db_structure:
                await ctx.send("无法获取数据库结构，请检查数据库ID是否正确")
                return

            # 显示可用的列
            columns = [f"{i+1}. {col}" for i, col in enumerate(db_structure)]
            embed = discord.Embed(
                title="可用的数据库列",
                description="\n".join(columns) + "\n\n请输入要显示的列的编号（用逗号分隔）"
            )
            await ctx.send(embed=embed)
            msg = await self.bot.wait_for(
                "message",
                check=lambda m: m.author == ctx.author and m.channel == ctx.channel,
                timeout=60
            )
            
            selected_columns = []
            for num in msg.content.strip().split(","):
                idx = int(num.strip()) - 1
                if 0 <= idx < len(db_structure):
                    selected_columns.append(db_structure[idx])

            # 保存配置
            if monitor:
                monitor.database_id = database_id
                monitor.interval = interval
                monitor.display_columns = json.dumps(selected_columns)
                monitor.is_active = True
                monitor.last_checked = datetime.utcnow().isoformat() + "Z"  # 添加初始检查时间
            else:
                monitor = models.NotionMonitorConfig(
                    guild_id=ctx.guild.id,
                    channel_id=ctx.channel.id,
                    database_id=database_id,
                    interval=interval,
                    display_columns=json.dumps(selected_columns),
                    is_active=True
                )
                monitor.last_checked = datetime.utcnow().isoformat() + "Z"  # 添加初始检查时间
                self.db.add(monitor)
            
            self.db.commit()

            embed = discord.Embed(
                title="监控设置完成",
                description=f"已设置监控:\n数据库: {database_id}\n间隔: {interval}分钟\n显示列: {', '.join(selected_columns)}",
                color=discord.Color.green()
            )
            await ctx.send(embed=embed)

        except asyncio.TimeoutError:
            await ctx.send("设置超时，请重新开始")
        except Exception as e:
            await ctx.send(f"��置失败: {str(e)}")

    async def get_database_structure(self, guild_id, database_id):
        """获取数据库的列结构"""
        guild_info = self.bot.guild_info[str(guild_id)]
        url = f"https://api.notion.com/v1/databases/{database_id}"
        headers = {
            'Authorization': guild_info.notion_api_key,
            'Notion-Version': '2021-08-16'
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers) as response:
                    if response.status == 200:
                        data = await response.json()
                        return list(data['properties'].keys())
        except Exception as e:
            print(f"获取数据库结构失败: {e}")
            return None

    @commands.command(name="monitor_start", aliases=["mstart"])
    @commands.has_permissions(administrator=True)
    async def start_monitor(self, ctx):
        """启动当前频道的Notion监控"""
        monitor = self.db.query(models.NotionMonitorConfig).filter_by(
            guild_id=ctx.guild.id,
            channel_id=ctx.channel.id
        ).first()
        
        if not monitor:
            await ctx.send("此频道未设置监控，请先使用 monitor_setup 命令设置")
            return
            
        monitor.is_active = True
        monitor.last_checked = datetime.utcnow().isoformat() + "Z"  # 添加初始检查时间
        self.db.commit()
        await ctx.send("监控已启动")

    @commands.command(name="monitor_stop", aliases=["mstop"])
    @commands.has_permissions(administrator=True)
    async def stop_monitor(self, ctx):
        """停止当前频道的Notion监控"""
        monitor = self.db.query(models.NotionMonitorConfig).filter_by(
            guild_id=ctx.guild.id,
            channel_id=ctx.channel.id
        ).first()
        
        if not monitor:
            await ctx.send("此频道未设置监控")
            return
            
        monitor.is_active = False
        self.db.commit()
        await ctx.send("监控已停止")

def setup(bot):
    bot.add_cog(NotionMonitor(bot)) 