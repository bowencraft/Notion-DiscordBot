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
        self.send_startup_notification.start()  # 添加启动通知任务

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
        self.send_startup_notification.cancel()  # 取消启动通知任务

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
        monitor = self.db.query(models.NotionMonitorConfig).filter_by(
            guild_id=ctx.guild.id,
            channel_id=ctx.channel.id
        ).first()
        
        if not monitor:
            await ctx.send("此频道未设置监控，请先使用 monitor_setup 命令设置")
            return

        if setting is None:
            # 显示当前配置
            embed = discord.Embed(
                title="当前监控配置",
                description=f"数据库ID: {monitor.database_id}\n"
                           f"检查间隔: {monitor.interval}分钟\n"
                           f"显示列: {monitor.display_columns}\n"
                           f"状态: {'活跃' if monitor.is_active else '停止'}",
                color=discord.Color.blue()
            )
            await ctx.send(embed=embed)
            return

        if setting.lower() != 'interval':
            await ctx.send("无效的设置选项。只支持设置 interval（检查间隔）")
            return

        if value is None:
            await ctx.send("请提供间隔时间（分钟）")
            return

        try:
            interval = int(value)
            if interval < 1:
                await ctx.send("间隔时间必须大于0分钟")
                return
            monitor.interval = interval
            self.db.commit()
            await ctx.send(f"已将检查间隔设置为 {interval} 分钟")
        except ValueError:
            await ctx.send("请输入有效的数字")
        except Exception as e:
            await ctx.send(f"设置失败: {str(e)}")

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

    def compare_page_changes(self, old_content, new_content):
        """比较页面变化"""
        changes = []
        try:
            old_props = json.loads(old_content)["properties"]
            new_props = new_content["properties"]
            
            for prop_name in new_props:
                if prop_name not in old_props:
                    # 新增的属性
                    new_value = self.format_property_value(new_props[prop_name])
                    if new_value:
                        changes.append(f"新增 {prop_name}: {new_value}")
                else:
                    # 比较现有属性
                    old_value = self.format_property_value(old_props[prop_name])
                    new_value = self.format_property_value(new_props[prop_name])
                    if old_value != new_value:
                        changes.append(f"修改 {prop_name}: {old_value} → {new_value}")
            
            for prop_name in old_props:
                if prop_name not in new_props:
                    # 删除的属性
                    old_value = self.format_property_value(old_props[prop_name])
                    if old_value:
                        changes.append(f"删除 {prop_name}: {old_value}")
                        
        except Exception as e:
            print(f"比较页面变化时出错: {e}")
            
        return changes

    def format_page_message(self, page, selected_columns=None, changes=None):
        """将Notion页面格式化为Discord消息"""
        try:
            embed = discord.Embed(
                title="📝 Notion更新通知",
                color=discord.Color.blue(),
                timestamp=datetime.utcnow()
            )
            
            # 处理选定的列
            if selected_columns:
                for column in selected_columns:
                    if column in page["properties"]:
                        value = self.format_property_value(page["properties"][column])
                        if value:
                            embed.add_field(name=column, value=value, inline=True)
            else:
                # 使用默认格式
                return self.format_default_message(page, embed)
            
            # 添加页面链接
            url = page.get("url", "")
            if url:
                embed.url = url
            
            # 添加变更信息
            if changes:
                change_text = "\n".join(changes)
                embed.add_field(
                    name="📋 变更详情",
                    value=change_text if len(change_text) <= 1024 else change_text[:1021] + "...",
                    inline=False
                )
            elif not changes and page.get("is_new", False):
                embed.add_field(
                    name="📋 状态",
                    value="✨ 新增条目",
                    inline=False
                )
                
            return embed
            
        except Exception as e:
            print(f"格式化页面消息时出错: {e}")
            print(f"页面数据: {json.dumps(page, indent=2)}")
            return None

    async def process_page_updates(self, monitor, pages):
        """处理页面更新"""
        updates = []
        for page in pages:
            try:
                # 查找页面的上一个快照
                snapshot = self.db.query(models.NotionPageSnapshot).filter_by(
                    monitor_id=monitor.id,
                    page_id=page["id"]
                ).first()
                
                if snapshot:
                    # 现有页面更新
                    changes = self.compare_page_changes(snapshot.content, page)
                    if changes:
                        # 更新快照
                        snapshot.content = json.dumps(page)
                        snapshot.last_updated = datetime.utcnow().isoformat() + "Z"
                        updates.append((page, changes))
                else:
                    # 新页面
                    page["is_new"] = True
                    # 创建新快照
                    new_snapshot = models.NotionPageSnapshot(
                        monitor_id=monitor.id,
                        page_id=page["id"],
                        content=json.dumps(page),
                        last_updated=datetime.utcnow().isoformat() + "Z"
                    )
                    self.db.add(new_snapshot)
                    updates.append((page, None))
                    
                self.db.commit()
                
            except Exception as e:
                print(f"处理页面 {page.get('id')} 更新时出错: {e}")
                
        return updates

    @tasks.loop(minutes=1)
    async def check_notion_updates(self):
        """检查所有活动的监控配置"""
        monitors = self.db.query(models.NotionMonitorConfig).filter_by(is_active=True).all()
        
        for monitor in monitors:
            try:
                if monitor.last_checked:
                    last_check = self.parse_iso_datetime(monitor.last_checked)
                    if (datetime.utcnow() - last_check).total_seconds() < monitor.interval * 60:
                        continue

                guild_info = self.bot.guild_info[str(monitor.guild_id)]
                pages = self.get_notion_pages(guild_info, monitor)
                
                if pages:
                    channel = self.bot.get_channel(monitor.channel_id)
                    if channel:
                        # 处理更新并获取变更信息
                        updates = await self.process_page_updates(monitor, pages)
                        for page, changes in updates:
                            message = self.format_page_message(
                                page,
                                json.loads(monitor.display_columns),
                                changes
                            )
                            if message:
                                await channel.send(embed=message)

                monitor.last_checked = datetime.utcnow().isoformat() + "Z"
                self.db.commit()

            except Exception as e:
                print(f"检查监控 {monitor.id} 时出错: {e}")
                import traceback
                traceback.print_exc()

    @check_notion_updates.before_loop
    async def before_check(self):
        await self.bot.wait_until_ready()

    def get_notion_pages(self, guild_info, monitor):
        """获取自上次检查以来更新的Notion页面"""
        try:
            print(f"上次检查时间: {monitor.last_checked}")
            
            url = "https://api.notion.com/v1/databases/" + monitor.database_id + "/query"
            headers = {
                'Authorization': guild_info.notion_api_key,
                'Notion-Version': '2021-08-16',
                'Content-Type': 'application/json'
            }
            
            query_data = {
                "filter": {
                    "timestamp": "last_edited_time",
                    "last_edited_time": {
                        "after": monitor.last_checked
                    }
                }
            }
            
            print(f"正在查询Notion数据库: {monitor.database_id}")
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
                    start = date_data.get("start", "")
                    end = date_data.get("end", "")
                    if end:
                        return f"{start} 至 {end}"
                    return start
                    
            elif property_type == "people":
                people = property_data.get("people", [])
                return ", ".join([person.get("name", "未知") for person in people])
                
            elif property_type == "files":
                files = property_data.get("files", [])
                return ", ".join([
                    f"[{file.get('name', '文件')}]({file.get('file', {}).get('url', '')})"
                    for file in files
                ])
                
            elif property_type == "checkbox":
                return "✅" if property_data.get("checkbox") else "❌"
                
            elif property_type == "number":
                return str(property_data.get("number", ""))
                
            elif property_type == "url":
                url = property_data.get("url", "")
                return f"[链接]({url})" if url else ""
                
            elif property_type == "email":
                return property_data.get("email", "")
                
            elif property_type == "phone_number":
                return property_data.get("phone_number", "")
                
            elif property_type == "formula":
                formula = property_data.get("formula", {})
                return str(formula.get("string") or formula.get("number") or 
                         formula.get("boolean") or formula.get("date"))
                
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
                embed.add_field(name="⏰ 更新间", value=edit_time, inline=True)
            
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

            # 获取guild_info
            guild_info = self.bot.guild_info[str(ctx.guild.id)]

            # 获取数据库ID
            embed = discord.Embed(description="请输入要监控的Notion数据库ID")
            await ctx.send(embed=embed)
            msg = await self.bot.wait_for(
                "message",
                check=lambda m: m.author == ctx.author and m.channel == ctx.channel,
                timeout=60
            )
            database_id = msg.content.strip()

            # 验证数据库ID
            db_structure = await self.get_database_structure(ctx.guild.id, database_id)
            if not db_structure:
                await ctx.send("无法获取数据库结构，请检查数据库ID是否正确")
                return

            # 获取监控间隔
            embed = discord.Embed(description="请输入监控间隔（分钟，建议不小于2分钟）")
            await ctx.send(embed=embed)
            msg = await self.bot.wait_for(
                "message",
                check=lambda m: m.author == ctx.author and m.channel == ctx.channel,
                timeout=60
            )
            
            try:
                interval = int(msg.content.strip())
                if interval < 1:
                    await ctx.send("间隔时间必须大于0分钟")
                    return
            except ValueError:
                await ctx.send("请输入有效的数字")
                return

            # 显示可用的列
            db_columns = list(db_structure.keys())
            columns_display = [f"{i+1}. {col} ({db_structure[col]})" for i, col in enumerate(db_columns)]
            embed = discord.Embed(
                title="可用的数据库列",
                description="\n".join(columns_display) + "\n\n请输入要显示的列的编号（用逗号分隔）",
                color=discord.Color.blue()
            )
            await ctx.send(embed=embed)
            
            msg = await self.bot.wait_for(
                "message",
                check=lambda m: m.author == ctx.author and m.channel == ctx.channel,
                timeout=60
            )
            
            try:
                selected_columns = []
                for num in msg.content.strip().split(","):
                    try:
                        idx = int(num.strip()) - 1
                        if 0 <= idx < len(db_columns):
                            selected_columns.append(db_columns[idx])
                        else:
                            await ctx.send(f"编号 {num} 超出范围，已忽略")
                    except ValueError:
                        await ctx.send(f"���效的编号 '{num}'，已忽略")
                
                if not selected_columns:
                    await ctx.send("未选择任何有效的列，请重新设置")
                    return
            except Exception as e:
                await ctx.send(f"处理列选择时出错: {str(e)}")
                return

            # 保存配置
            if monitor:
                # 更新现有配置
                monitor.database_id = database_id
                monitor.interval = interval
                monitor.display_columns = json.dumps(selected_columns)
                monitor.is_active = True
                monitor.last_checked = datetime.utcnow().isoformat() + "Z"
            else:
                # 创建新配置
                monitor = models.NotionMonitorConfig(
                    guild_id=ctx.guild.id,
                    channel_id=ctx.channel.id,
                    database_id=database_id,
                    interval=interval,
                    display_columns=json.dumps(selected_columns),
                    is_active=True
                )
                monitor.last_checked = datetime.utcnow().isoformat() + "Z"
                self.db.add(monitor)
            
            self.db.commit()

            embed = discord.Embed(
                title="监控设置完成",
                description=f"已设置监控:\n"
                           f"频道: {ctx.channel.mention}\n"
                           f"数据库: {database_id}\n"
                           f"间隔: {interval}分钟\n"
                           f"显示列: {', '.join(selected_columns)}",
                color=discord.Color.green()
            )
            await ctx.send(embed=embed)

        except asyncio.TimeoutError:
            await ctx.send("设置超时，请重新开始")
        except Exception as e:
            print(f"设置监控时出错: {str(e)}")  # 添加详细的错误日志
            import traceback
            traceback.print_exc()  # 打印完整的错误堆栈
            await ctx.send(f"设置失败: {str(e)}")

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
                        return {
                            name: prop['type'] 
                            for name, prop in data['properties'].items()
                        }
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

    @tasks.loop(count=1)  # 只执行一次
    async def send_startup_notification(self):
        """发送机器人启动通知"""
        try:
            # 获取所有活动的监控配置
            monitors = self.db.query(models.NotionMonitorConfig).filter_by(is_active=True).all()
            
            for monitor in monitors:
                try:
                    channel = self.bot.get_channel(monitor.channel_id)
                    if channel:
                        # 解析显示列
                        display_columns = json.loads(monitor.display_columns)
                        
                        embed = discord.Embed(
                            title="🤖 Notion监控已启动",
                            description="机器人已成功启动，正在监控以下内容：",
                            color=discord.Color.green(),
                            timestamp=datetime.utcnow()
                        )
                        
                        embed.add_field(
                            name="📊 数据库",
                            value=f"`{monitor.database_id}`",
                            inline=False
                        )
                        
                        embed.add_field(
                            name="⏱️ 检查间隔",
                            value=f"每 {monitor.interval} 分钟",
                            inline=True
                        )
                        
                        embed.add_field(
                            name="📋 监控列",
                            value=", ".join(display_columns) if display_columns else "无",
                            inline=True
                        )
                        
                        # embed.set_footer(text="Bot by Your Name")
                        
                        await channel.send(embed=embed)
                        
                except Exception as e:
                    print(f"发送启动通知到频道 {monitor.channel_id} 时出错: {e}")
                    
        except Exception as e:
            print(f"发送启动通知时出错: {e}")

    @send_startup_notification.before_loop
    async def before_startup_notification(self):
        """等待机器人准备就绪"""
        await self.bot.wait_until_ready()

def setup(bot):
    bot.add_cog(NotionMonitor(bot)) 