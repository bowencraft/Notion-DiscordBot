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
from settings.logging_config import log, get_random_footer, config

class NotionMonitor(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = SessionLocal()
        self.last_checked = {}
        self.check_notion_updates.start()
        self.send_startup_notification.start()

        log("Notion监控已初始化", "info")
        
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
        log("Notion监控已停止", "info")

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
    async def configure_monitor(self, ctx, setting: str = None, *, value: str = None):
        """配置监控的设置"""
        monitor = self.db.query(models.NotionMonitorConfig).filter_by(
            guild_id=ctx.guild.id,
            channel_id=ctx.channel.id
        ).first()
        
        if not monitor:
            await ctx.send("此频道未设置监控，请先使用 monitor_setup 命令设置")
            return

        if setting is None:
            # 显示当前配置
            current_title = monitor.title_column or "默认"
            embed = discord.Embed(
                title="当前监控配置",
                description=f"数据库ID: {monitor.database_id}\n"
                           f"检查间隔: {monitor.interval}分钟\n"
                           f"显示列: {monitor.display_columns}\n"
                           f"标题来源: {current_title}\n"
                           f"状态: {'活跃' if monitor.is_active else '停止'}",
                color=discord.Color.blue()
            )
            await ctx.send(embed=embed)
            return

        setting = setting.lower()
        if setting == 'interval':
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
            return

        elif setting == 'task_name':
            if value is None:
                current_title = monitor.title_column or "默认"
                embed = discord.Embed(
                    title="通知标题设置",
                    description=f"当前标题来源: {current_title}\n\n"
                               f"使用 `{monitor.prefix}mc task_name <列名>` 设置标题来源\n"
                               f"使用 `{monitor.prefix}mc task_name default` 恢复默认标题",
                    color=discord.Color.blue()
                )
                await ctx.send(embed=embed)
                return

            if value.lower() == "default":
                monitor.title_column = None
                self.db.commit()
                await ctx.send("✅ 已恢复默认标题")
                return

            # 验证列名是否存在
            db_structure = await self.get_database_structure_with_key(monitor.notion_api_key, monitor.database_id)
            if not db_structure or value not in db_structure:
                await ctx.send(f"❌ 列名 '{value}' 不存在\n可用的列: {', '.join(db_structure.keys())}")
                return

            monitor.title_column = value
            self.db.commit()
            await ctx.send(f"✅ 已设置标题来源为: {value}")
            return

        await ctx.send("无效的设置选项。可用选项:\n"
                      "- interval: 设置检查间隔（分钟）\n"
                      "- task_name: 设置通知标题来源")

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

    async def compare_page_changes(self, old_content, new_content, guild_id=None):
        """比较页面变化"""
        changes = []
        try:
            old_props = json.loads(old_content)["properties"]
            new_props = new_content["properties"]
            
            for prop_name in new_props:
                if prop_name not in old_props:
                    # 新增的属性
                    new_value = await self.format_property_value(new_props[prop_name], guild_id)
                    if new_value:
                        changes.append(f"**新增 {prop_name}**: {new_value}")
                else:
                    # 比较现有属性
                    old_value = await self.format_property_value(old_props[prop_name], guild_id)
                    new_value = await self.format_property_value(new_props[prop_name], guild_id)
                    if old_value != new_value:
                        changes.append(f"**修改 {prop_name}**: {old_value} → {new_value}")
            
            for prop_name in old_props:
                if prop_name not in new_props:
                    # 删除的性
                    old_value = await self.format_property_value(old_props[prop_name], guild_id)
                    if old_value:
                        changes.append(f"**删 {prop_name}**: {old_value}")
                        
        except Exception as e:
            print(f"比较页面变化时出错: {e}")
            
        return changes

    async def format_page_message(self, page, selected_columns=None, changes=None, guild_id=None):
        """将Notion页面格式化为Discord消息"""
        try:
            # 在debug模式下记录原始数据
            log(f"处理页面原始数据:\n{json.dumps(page, indent=2, ensure_ascii=False)}", "debug")
            
            # 获取标题
            if page.get("is_new", False):
                base_title = "📝 Notion 新条目"
            else:
                base_title = "📝 Notion 更新通知"

            title = base_title
            if guild_id:
                monitor = self.db.query(models.NotionMonitorConfig).filter_by(
                    guild_id=guild_id
                ).first()
                
                if monitor and monitor.title_column:
                    if monitor.title_column in page["properties"]:
                        custom_title = await self.format_property_value(
                            page["properties"][monitor.title_column],
                            guild_id
                        )
                        if custom_title:
                            title = f"{base_title}：{custom_title}"
                            log(f"设置自定义标题: {title}", "debug")

            # 获取颜色
            embed_color = discord.Color.blue()
            for prop_name, prop_data in page.get("properties", {}).items():
                if prop_data.get("type") in ["select", "multi_select", "status"]:
                    if prop_data.get("type") == "status" and prop_data.get("status"):
                        color = prop_data["status"].get("color")
                        if color:
                            embed_color = self.notion_color_to_discord(color)
                            log(f"使用状态颜色: {color}", "debug")
                            break
                    elif prop_data.get("type") == "select" and prop_data.get("select"):
                        color = prop_data["select"].get("color")
                        if color:
                            embed_color = self.notion_color_to_discord(color)
                            log(f"使用选择颜色: {color}", "debug")
                            break
                    elif prop_data.get("type") == "multi_select" and prop_data.get("multi_select"):
                        if prop_data["multi_select"] and prop_data["multi_select"][0].get("color"):
                            color = prop_data["multi_select"][0]["color"]
                            embed_color = self.notion_color_to_discord(color)
                            log(f"使用多选颜色: {color}", "debug")
                            break

            embed = discord.Embed(
                title=title,
                color=embed_color,
                timestamp=datetime.utcnow()
            )
            
            # 处理选定列
            if selected_columns:
                log(f"处理选定列: {selected_columns}", "debug")
                for column in selected_columns:
                    if column in page["properties"]:
                        value = await self.format_property_value(page["properties"][column], guild_id)
                        if value:
                            embed.add_field(name=column, value=value, inline=True)
                            log(f"添加字段 {column}: {value}", "debug")
            
            # 添加页面链接
            url = page.get("url", "")
            if url:
                embed.url = url
                log(f"添加页面链接: {url}", "debug")
            
            # 添加变更信息
            if changes:
                change_text = "\n".join(changes)
                log(f"变更详情:\n{change_text}", "debug")
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
                log("新增条目", "debug")

            # 添加随机footer
            footer_text = get_random_footer()
            if footer_text:
                embed.set_footer(text=footer_text)
                log(f"添加footer: {footer_text}", "debug")
            
            # 在debug模式下记录最终的消息内容
            log("最终消息内容:", "debug")
            log(f"标题: {embed.title}", "debug")
            log(f"颜色: {embed.color}", "debug")
            log("字段:", "debug")
            for field in embed.fields:
                log(f"  {field.name}: {field.value}", "debug")
                
            return embed
            
        except Exception as e:
            log(f"格式化页面消息时出错: {e}", "info")
            log(f"页面数据: {json.dumps(page, indent=2, ensure_ascii=False)}", "debug")
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
                    changes = await self.compare_page_changes(snapshot.content, page, monitor.guild_id)
                    if changes:
                        # 新快照
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

                log(f"开始检查频道 {monitor.channel_id} 的更新", "info")
                pages = self.get_notion_pages(monitor)
                
                if pages:
                    log(f"找到 {len(pages)} 个更新", "debug")
                    channel = self.bot.get_channel(monitor.channel_id)
                    if channel:
                        updates = await self.process_page_updates(monitor, pages)
                        for page, changes in updates:
                            message = await self.format_page_message(
                                page,
                                json.loads(monitor.display_columns),
                                changes,
                                monitor.guild_id
                            )
                            if message:
                                await channel.send(embed=message)

                monitor.last_checked = datetime.utcnow().isoformat() + "Z"
                self.db.commit()
                log(f"完成频道 {monitor.channel_id} 的更新检查", "info")

            except Exception as e:
                log(f"检查监控 {monitor.id} 时出错: {e}", "info")
                if should_log("debug"):
                    import traceback
                    traceback.print_exc()

    @check_notion_updates.before_loop
    async def before_check(self):
        await self.bot.wait_until_ready()

    def get_notion_pages(self, monitor):
        """获取自上次检查以来更新的Notion页面"""
        try:
            log(f"上次检查时间: {monitor.last_checked}", "debug")
            
            url = "https://api.notion.com/v1/databases/" + monitor.database_id + "/query"
            headers = {
                'Authorization': monitor.notion_api_key,
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
            
            log(f"正在查询Notion数据库: {monitor.database_id}", "debug")
            log(f"查询条件: {json.dumps(query_data, indent=2)}", "debug")
            
            payload = json.dumps(query_data)
            response = requests.post(url, headers=headers, data=payload)
            
            log(f"Notion API响应状态码: {response.status_code}", "debug")
            if response.status_code == 200:
                result = response.json()
                log(f"找到 {len(result.get('results', []))} 条更新", "debug")
                return result.get("results", [])
            else:
                log(f"Notion API错误响应: {response.text}", "info")
                return []
                
        except Exception as e:
            log(f"从Notion获取页面时出错: {e}", "info")
            return []

    async def get_related_pages(self, monitor, page_ids):
        """获取关联页面的信息"""
        try:
            results = []
            for page_id in page_ids:
                url = f"https://api.notion.com/v1/pages/{page_id}"
                headers = {
                    'Authorization': monitor.notion_api_key,
                    'Notion-Version': '2021-08-16'
                }
                
                async with aiohttp.ClientSession() as session:
                    async with session.get(url, headers=headers) as response:
                        if response.status == 200:
                            page = await response.json()
                            # 获取页面标题
                            title = None
                            for prop_name, prop_data in page["properties"].items():
                                if prop_data["type"] == "title":
                                    title_list = prop_data.get("title", [])
                                    if title_list and len(title_list) > 0:
                                        title = title_list[0].get("plain_text", "无标题")
                                    break
                            
                            if title:
                                results.append({
                                    'title': title,
                                    'url': page.get('url', '')
                                })
            
            return results
        except Exception as e:
            print(f"获取关联页面时出错: {e}")
            return []

    async def format_property_value(self, property_data, guild_id=None):
        """格式化Notion属性值"""
        try:
            property_type = property_data.get("type")
            if not property_type:
                return None
                
            if property_type == "select":
                select_data = property_data.get("select")
                if select_data:
                    return select_data.get("name", "")
                return None
            
            elif property_type == "status":
                select_data = property_data.get("status")
                if select_data:
                    return select_data.get("name", "")
                return None
                
            elif property_type == "multi_select":
                multi_select = property_data.get("multi_select", [])
                return ", ".join([item.get("name", "") for item in multi_select])
                
            elif property_type == "title":
                text_list = property_data.get("title", [])
                formatted_texts = []
                
                for text_item in text_list:
                    if text_item.get("type") == "mention" and text_item["mention"].get("type") == "user":
                        # 处理用户提及
                        user_id = text_item["mention"]["user"].get("id")
                        if guild_id and user_id:
                            # 查找用户映射
                            user_map = self.db.query(models.NotionDiscordUserMap).filter_by(
                                guild_id=guild_id,
                                notion_user_id=user_id
                            ).first()
                            if user_map:
                                formatted_texts.append(user_map.discord_mention)
                            else:
                                formatted_texts.append(f"`{user_id}`")
                    else:
                        # 处理普通文本
                        formatted_texts.append(text_item.get("plain_text", ""))
                
                return "".join(formatted_texts) if formatted_texts else None
                    
            elif property_type == "rich_text":
                text_list = property_data.get("rich_text", [])
                formatted_texts = []
                
                for text_item in text_list:
                    if text_item.get("type") == "mention" and text_item["mention"].get("type") == "user":
                        # 处理用户提及
                        user_id = text_item["mention"]["user"].get("id")
                        if guild_id and user_id:
                            # 查找用户映射
                            user_map = self.db.query(models.NotionDiscordUserMap).filter_by(
                                guild_id=guild_id,
                                notion_user_id=user_id
                            ).first()
                            if user_map:
                                formatted_texts.append(user_map.discord_mention)
                            else:
                                formatted_texts.append(f"`{user_id}`")
                        else:
                            formatted_texts.append(text_item.get("plain_text", ""))
                    else:
                        # 处理普通文本
                        formatted_texts.append(text_item.get("plain_text", ""))
                
                return " ".join(formatted_texts) if formatted_texts else None
                    
            elif property_type == "date":
                date_data = property_data.get("date")
                if date_data:
                    start = date_data.get("start", "")
                    end = date_data.get("end", "")
                    if end:
                        return f"{start} 至 {end}"
                    return start
                    
            elif property_type == "people":
                if guild_id:
                    return self.format_user_value(property_data.get("people", []), guild_id)
                else:
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
                         formula.get("boolean") or formula.get("date", ""))
                
            elif property_type == "created_time":
                return property_data.get("created_time", "")
                
            elif property_type == "last_edited_time":
                return property_data.get("last_edited_time", "")
                
            elif property_type == "relation":
                relation_data = property_data.get("relation", [])
                if not relation_data:
                    return None
                    
                # 获取所有关联页面的ID
                page_ids = [item["id"] for item in relation_data]
                if not page_ids:
                    return None
                    
                # 如果没有提供guild_id，只返回ID列表
                if not guild_id:
                    return ", ".join([f"`{id}`" for id in page_ids])
                    
                # 获取guild_info
                guild_info = self.bot.guild_info[str(guild_id)]
                
                # 直接调用异步函数
                related_pages = await self.get_related_pages(guild_info, page_ids)
                
                # 格式化为标题和链接
                if related_pages:
                    return "\n".join([
                        f"[{page['title']}]({page['url']})"
                        for page in related_pages
                    ])
                return None
                
            return str(property_data.get(property_type, ""))
            
        except Exception as e:
            print(f"格式化属性值时出错: {e}")
            print(f"属性数据: {json.dumps(property_data, indent=2)}")
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

            if not monitor:
                embed = discord.Embed(
                    description=f"请先运行 `{PREFIX}setup` 设置此频道的Notion API密钥",
                    color=discord.Color.red()
                )
                await ctx.send(embed=embed)
                return

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
            db_structure = await self.get_database_structure_with_key(monitor.notion_api_key, database_id)
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
                description="\n".join(columns_display) + "\n\n请输入要显示的列的编号（用逗号隔开）",
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
                        await ctx.send(f"无效的编号 '{num}'，已忽略")
                
                if not selected_columns:
                    await ctx.send("未选择任何有效的列，请重新设置")
                    return
            except Exception as e:
                await ctx.send(f"处理列选择时出错: {str(e)}")
                return

            # 更新配置
            monitor.database_id = database_id
            monitor.interval = interval
            monitor.display_columns = json.dumps(selected_columns)
            monitor.is_active = True
            monitor.last_checked = datetime.utcnow().isoformat() + "Z"
            
            self.db.commit()

            # 创建初始快照
            await ctx.send("正在创建数据库快照，这可能需要一些时间...")
            await self.create_initial_snapshots(monitor)

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
            print(f"设置监控时出错: {str(e)}")
            import traceback
            traceback.print_exc()
            await ctx.send(f"设置失败: {str(e)}")

    async def get_database_structure_with_key(self, notion_api_key, database_id):
        """获取数据库的列结构"""
        url = f"https://api.notion.com/v1/databases/{database_id}"
        headers = {
            'Authorization': notion_api_key,
            'Notion-Version': '2021-08-16'
        }
        
        log(f"正在获取数据库结构: {database_id}", "debug")
        log(f"API URL: {url}", "debug")
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers) as response:
                    log(f"API响应状态码: {response.status}", "debug")
                    
                    if response.status == 200:
                        data = await response.json()
                        log(f"获取到原始数据库结构:\n{json.dumps(data, indent=2, ensure_ascii=False)}", "debug")
                        
                        # 处理每个属性，包括relation类型
                        properties = {}
                        for name, prop in data['properties'].items():
                            prop_type = prop['type']
                            log(f"处理属性 {name} (类型: {prop_type})", "debug")
                            
                            if prop_type == 'relation':
                                # 获取关联数据库的信息
                                relation_info = prop.get('relation', {})
                                if isinstance(relation_info, dict):
                                    db_id = relation_info.get('database_id')
                                    if db_id:
                                        properties[name] = f"relation (Database: {db_id})"
                                else:
                                    # 如果是数组类型的relation
                                    properties[name] = "relation (Multiple)"
                                log(f"处理relation属性 {name}: {properties[name]}", "debug")
                            elif prop_type == 'rollup':
                                # 处理rollup类型
                                properties[name] = "rollup"
                                log(f"处理rollup属性 {name}", "debug")
                            else:
                                properties[name] = prop_type
                                log(f"处理普通属性 {name}: {prop_type}", "debug")
                        
                        log(f"处理后的数据库结构:\n{json.dumps(properties, indent=2, ensure_ascii=False)}", "debug")
                        return properties
                    else:
                        error_text = await response.text()
                        log(f"获取数据库结构失败: HTTP {response.status}", "info")
                        log(f"错误响应: {error_text}", "debug")
                        return None
        except Exception as e:
            log(f"获取数据库结构时发生错误: {str(e)}", "info")
            import traceback
            log(f"错误堆栈:\n{traceback.format_exc()}", "debug")
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
        monitor.last_checked = datetime.utcnow().isoformat() + "Z"  # 添��初始检查时间
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
            # 检查是否启用了启动通知
            if not config.get('bot', {}).get('startup_notification', False):
                log("启动通知已禁用", "info")
                return

            # 获取启动消息模板
            startup_message = config.get('messages', {}).get('startup', "🤖 机器人已启动")
            
            # 获取所有工会
            guilds = self.bot.guilds
            log(f"机器人加入的工会数量: {len(guilds)}", "info")
            
            for guild in guilds:
                try:
                    log(f"正在处理工会: {guild.name} ({guild.id})", "debug")
                    
                    # 获取该工会的所有活动监控配置
                    monitors = self.db.query(models.NotionMonitorConfig).filter_by(
                        guild_id=guild.id,
                        is_active=True
                    ).all()
                    
                    if not monitors:
                        log(f"工会 {guild.name} 没有活动的监控配置", "debug")
                        continue
                    
                    log(f"工会 {guild.name} 有 {len(monitors)} 个活动监控", "debug")
                    
                    for monitor in monitors:
                        try:
                            channel = self.bot.get_channel(monitor.channel_id)
                            if channel:
                                embed = discord.Embed(
                                    title="系统通知",
                                    description=startup_message,
                                    color=discord.Color.green(),
                                    timestamp=datetime.utcnow()
                                )
                                
                                # 添加监控信息
                                embed.add_field(
                                    name="📊 监控数据库",
                                    value=f"`{monitor.database_id}`",
                                    inline=False
                                )
                                
                                embed.add_field(
                                    name="⏱️ 检查间隔",
                                    value=f"每 {monitor.interval} 分钟",
                                    inline=True
                                )
                                
                                try:
                                    display_columns = json.loads(monitor.display_columns)
                                    embed.add_field(
                                        name="📋 监控列",
                                        value=", ".join(display_columns) if display_columns else "无",
                                        inline=True
                                    )
                                except:
                                    pass

                                # 添加随机footer
                                footer_text = get_random_footer()
                                if footer_text:
                                    embed.set_footer(text=footer_text)
                                
                                await channel.send(embed=embed)
                                log(f"已发送启动通知到频道 {channel.name} ({channel.id})", "debug")
                            else:
                                log(f"无法找到频道 {monitor.channel_id}", "info")
                                
                        except Exception as e:
                            log(f"发送启动通知到频道 {monitor.channel_id} 时出错: {e}", "info")
                            
                except Exception as e:
                    log(f"处理工会 {guild.name} 时出错: {e}", "info")
                    
        except Exception as e:
            log(f"发送启动通知时出错: {e}", "info")
            import traceback
            log(f"错误堆栈:\n{traceback.format_exc()}", "debug")

    @send_startup_notification.before_loop
    async def before_startup_notification(self):
        """等待机器人准备就绪"""
        await self.bot.wait_until_ready()

    @commands.command(name="map_users", aliases=["mu"])
    @commands.has_permissions(administrator=True)
    async def map_users(self, ctx, notion_id: str = None):
        """映射Notion用户ID到Discord用户"""
        try:
            # 检查频道是否已设置
            monitor = self.db.query(models.NotionMonitorConfig).filter_by(
                guild_id=ctx.guild.id,
                channel_id=ctx.channel.id
            ).first()
            
            if not monitor:
                embed = discord.Embed(
                    description=f"请先运行 `{PREFIX}setup` 设此频道",
                    color=discord.Color.red()
                )
                await ctx.send(embed=embed)
                return

            # 如果没有参数或参数是"list"，显示当前映射
            if not notion_id or notion_id.lower() == "list":
                embed = discord.Embed(
                    title="用户映射",
                    description="当前频道的用户映射关系\n"
                               "使用以下格式添加映射：\n"
                               "`*mu <Notion用户ID> @Discord用户`\n"
                               "使用以下格式删除映射：\n"
                               "`*mu <Notion用户ID>`\n"
                               "Notion用户ID是形如'e79a0b74-3aba-4149-9f74-0bb5791a6ee6'的UUID",
                    color=discord.Color.blue()
                )
                # 显示当前映射
                all_mappings = self.db.query(models.NotionDiscordUserMap).filter_by(
                    guild_id=ctx.guild.id,
                    channel_id=ctx.channel.id
                ).all()
                if all_mappings:
                    mapping_text = []
                    for mapping in all_mappings:
                        mapping_text.append(
                            f"`{mapping.notion_user_id}` → {mapping.discord_mention}"
                        )
                    embed.add_field(
                        name="当前映射",
                        value="\n".join(mapping_text),
                        inline=False
                    )
                await ctx.send(embed=embed)
                return

            # 验证UUID格式
            if not len(notion_id) == 36:
                await ctx.send("❌ 无效的Notion用户ID格式")
                return

            # 如果没有提及用户，则删除映射
            if not ctx.message.mentions:
                # 删除映射
                mapping = self.db.query(models.NotionDiscordUserMap).filter_by(
                    guild_id=ctx.guild.id,
                    channel_id=ctx.channel.id,
                    notion_user_id=notion_id
                ).first()
                
                if mapping:
                    self.db.delete(mapping)
                    self.db.commit()
                    await ctx.send(f"✅ 已删除户ID `{notion_id}` 的射")
                else:
                    await ctx.send(f"❌ 未找到用户ID `{notion_id}` 的映射")
                return

            discord_user = ctx.message.mentions[0]
            discord_mention = discord_user.mention
            
            # 保存映射
            existing = self.db.query(models.NotionDiscordUserMap).filter_by(
                guild_id=ctx.guild.id,
                channel_id=ctx.channel.id,
                notion_user_id=notion_id
            ).first()

            if existing:
                existing.discord_mention = discord_mention
                print(f"更新映射: {notion_id} -> {discord_mention} (更新)")
            else:
                new_mapping = models.NotionDiscordUserMap(
                    guild_id=ctx.guild.id,
                    channel_id=ctx.channel.id,
                    notion_user_id=notion_id,
                    discord_mention=discord_mention
                )
                self.db.add(new_mapping)
                print(f"新增映射: {notion_id} -> {discord_mention} (新增)")

            self.db.commit()
            await ctx.send(f"✅ 已映射 `{notion_id}` → {discord_mention}")

        except Exception as e:
            print(f"映射用户时出错: {e}")
            import traceback
            traceback.print_exc()  # 添加详细的错误跟踪
            await ctx.send(f"❌ 设置失败: {str(e)}")

    def format_user_value(self, users_data, guild_id):
        """格式化用户属性值"""
        try:
            if not users_data:
                return None

            print(f"格式化用户数据: {json.dumps(users_data, indent=2)}")
            print(f"Guild ID: {guild_id}")

            # 获取该服务器的所有用户映射
            user_mappings = {
                m.notion_user_id: m.discord_mention 
                for m in self.db.query(models.NotionDiscordUserMap).filter_by(guild_id=guild_id).all()
            }
            print(f"用户映射: {json.dumps(user_mappings, indent=2)}")

            formatted_users = []
            for user in users_data:
                user_id = user.get("id")
                if not user_id:
                    print(f"跳过无效用户数: {json.dumps(user, indent=2)}")
                    continue
                    
                discord_mention = user_mappings.get(user_id)
                if discord_mention:
                    formatted_users.append(discord_mention)
                    print(f"用户 {user_id} 映射到 {discord_mention}")
                else:
                    formatted_users.append(f"`{user_id}`")
                    print(f"用户 {user_id} 未找到映射")

            result = ", ".join(formatted_users) if formatted_users else None
            print(f"最终格式化结果: {result}")
            return result

        except Exception as e:
            print(f"格式化用户值时出错: {e}")
            print(f"用户数据: {json.dumps(users_data, indent=2)}")
            return None

    async def create_initial_snapshots(self, monitor):
        """为数据库中的所有面创建初始快照"""
        try:
            print(f"正在为数据库 {monitor.database_id} 创建初始快照...")
            
            url = "https://api.notion.com/v1/databases/" + monitor.database_id + "/query"
            headers = {
                'Authorization': monitor.notion_api_key,
                'Notion-Version': '2021-08-16',
                'Content-Type': 'application/json'
            }
            
            # 查询所有页面
            has_more = True
            start_cursor = None
            total_pages = 0
            
            while has_more:
                query_data = {}
                if start_cursor:
                    query_data["start_cursor"] = start_cursor
                
                payload = json.dumps(query_data)
                response = requests.post(url, headers=headers, data=payload)
                
                if response.status_code == 200:
                    result = response.json()
                    pages = result.get("results", [])
                    
                    # 为每个页面创建快照
                    for page in pages:
                        # 检查是否已存在快照
                        existing = self.db.query(models.NotionPageSnapshot).filter_by(
                            monitor_id=monitor.id,
                            page_id=page["id"]
                        ).first()
                        
                        if not existing:
                            new_snapshot = models.NotionPageSnapshot(
                                monitor_id=monitor.id,
                                page_id=page["id"],
                                content=json.dumps(page),
                                last_updated=datetime.utcnow().isoformat() + "Z"
                            )
                            self.db.add(new_snapshot)
                            total_pages += 1
                    
                    self.db.commit()
                    
                    # 检查是否还有更多页面
                    has_more = result.get("has_more", False)
                    start_cursor = result.get("next_cursor")
                else:
                    print(f"获取页面失败: {response.text}")
                    break
            
            print(f"初始快照创建完，共处理 {total_pages} 个页面")
            
        except Exception as e:
            print(f"创建初始快照时出错: {e}")
            import traceback
            traceback.print_exc()

    def notion_color_to_discord(self, notion_color):
        """将Notion的颜色转换为Discord的颜色"""
        color_map = {
            "blue": discord.Color.blue(),
            "red": discord.Color.red(),
            "pink": discord.Color.magenta(),
            "yellow": discord.Color.gold(),
            "orange": discord.Color.orange(),
            "green": discord.Color.green(),
            "purple": discord.Color.purple(),
            "brown": discord.Color.dark_gold(),
            "gray": discord.Color.dark_gray(),
            "default": discord.Color.blue()
        }
        return color_map.get(notion_color, color_map["default"])

    @commands.command(name="set_title", aliases=["st"])
    @commands.has_permissions(administrator=True)
    async def set_title(self, ctx, *, column_name: str = None):
        """设置通知标题使用的数据列"""
        monitor = self.db.query(models.NotionMonitorConfig).filter_by(
            guild_id=ctx.guild.id,
            channel_id=ctx.channel.id
        ).first()
        
        if not monitor:
            await ctx.send("此频道未设置监控，请先使用 monitor_setup 命令设置")
            return

        if column_name is None:
            # 显示当前设置
            current_title = monitor.title_column or "默认"
            embed = discord.Embed(
                title="通知标题设置",
                description=f"当前标题来源: {current_title}\n\n"
                           f"使用 `{monitor.prefix}st <列名>` 设置标题来源\n"
                           f"使用 `{monitor.prefix}st default` 恢复默认标题",
                color=discord.Color.blue()
            )
            await ctx.send(embed=embed)
            return

        if column_name.lower() == "default":
            monitor.title_column = None
            self.db.commit()
            await ctx.send("✅ 已恢复默认标题")
            return

        # 验证列名是否存在
        db_structure = await self.get_database_structure_with_key(monitor.notion_api_key, monitor.database_id)
        if not db_structure or column_name not in db_structure:
            await ctx.send(f"❌ 列名 '{column_name}' 不存在\n可用的列: {', '.join(db_structure.keys())}")
            return

        monitor.title_column = column_name
        self.db.commit()
        await ctx.send(f"✅ 已设置标题来源为: {column_name}")

def setup(bot):
    bot.add_cog(NotionMonitor(bot)) 