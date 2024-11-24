# Notion Discord Monitor Bot

![img](https://camo.githubusercontent.com/460820b5010c49d3a8ca74427778ffeb604ac7b6571d46db37c753a9c28476d4/68747470733a2f2f692e696d6775722e636f6d2f735371547535362e706e67)

一个专注于监控 Notion 数据库更新并发送通知到 Discord 的机器人。



## 功能特点

- 监控多个 Notion 数据库的更新
- 支持多频道独立配置
- 自定义通知显示内容
- Discord 用户与 Notion 用户映射
- 详细的更新变更记录
- 美观的消息卡片展示



## 安装步骤

1. **克隆仓库**

```bash
git clone https://github.com/bowencraft/Notion-DiscordBot.git
cd notion-discord-monitor
```

2. **安装依赖**

```bash
pip install -r requirements.txt
```

3. **创建 Discord Bot**

- 访问 [Discord Developer Portal](https://discord.com/developers/applications)

- 创建新的应用程序

- 在 Bot 页面创建机器人

- 复制机器人令牌

- 在 OAuth2 页面生成邀请链接（需要的权限：发送消息、嵌入链接、附加文件）

4. **设置 Notion Integration**

- 访问 [Notion Integrations](https://www.notion.so/my-integrations)
- 创建新的Integration
- 复制Integration令牌
- 将需要监控的数据库添加到Integration中
  - Click on the three dots and press Open as page
  - Then press share and copy the URL. The URL will look something like this: https://www.notion.so/XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX?v=YYYYYYYYYYYYYYYYYYYYYYYYY
  - Note down the X part of the url, this is your database id
  - Also press share again, press "Connect to" and then click on the integration you made earlier (You need to have the permission)

5. **配置机器人**

- Export the Discord 机器人令牌 as an environment variable: `export TOKEN=<OAUTH TOKEN>`
- Generate a secret key which will be used for encrypting the database and keep it safe. Export this key as an environment variable => `export SECRET_KEY=<SECRET_KEY>`
- 修改 `settings.yml` 中的配置（可选）



## 使用方法

### 基础命令

- `*setup` - 设置频道的 Notion API 密钥`*help` - 查看所有可用指令
- `*ms` - 配置数据库监控（选择数据库、监控间隔、显示列）

- `*mc` - 查看/修改监控配置

- `*mc interval <分钟>` - 设置检查间隔

- `*mc task_name <列名>` - 设置通知标题来源

- `*mstart` - 启动监控

- `*mstop` - 停止监控

- `*mu <Notion用户ID> @Discord用户` - 映射 Notion 用户到 Discord 用户

### 设置流程

1. 邀请机器人到服务器
2. 在需要接收通知的频道中：

  - 运行 `*setup` 设置 Notion API 密钥

  - 运行 `*ms` 配置要监控的数据库

  - 选择要显示的数据库列

  - 设置检查间隔

3. 使用 `*mstart` 启动监控
4. （可选）使用 `*mu` 设置用户映射

### 配置文件

`settings.yml` 支持以下配置：

```yaml
# 日志设置
logging:
  level: debug  # 可选值: none, info, debug

# 机器人设置
bot:
  prefix: "*"  # 默认前缀 
  startup_notification: true  # 是否在启动时发送通知

# 消息设置
messages:
  footers: # 在通知消息embedded位置显示的内容
    - "GAPD小助手提醒你：享福时间到 ✨"
    - "该休息了，博士 🤝"
    - "保持专注，持续前进 🎯"
    - "Spiritfarer Clone"
  startup: "🤖 机器人已启动并开始监控\n使用 `*help` 查看可用命令"  # 启动消息模板
```



## 注意事项

1. 建议将检查间隔设置为不小于 2 分钟，以避免触发 Notion API 限制
2. 确保机器人具有发送消息和嵌入链接的权限
3. Notion 集成需要被添加到要监控的数据库中
4. 用户映射功能需要 Notion 用户的 UUID



## 常见问题

Q: 如何找到 Notion 用户 ID？

A: 在数据库中分配用户后，可以从调试日志中看到用户 ID。

Q: 如何修改通知样式？

A: 目前支持通过 `mc task_name` 设置标题来源。

Q: 支持哪些 Notion 属性类型？

A: 支持大多数常用类型，包括文本、选择、多选、用户、日期、关联等。



## 许可证

本仓库是基于 [Servatom/Notion-DiscordBot](https://github.com/Servatom/Notion-DiscordBot) 进行的二次开发。

许可证：[MIT License](LICENSE)