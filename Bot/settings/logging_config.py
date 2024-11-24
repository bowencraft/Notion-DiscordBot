import yaml
import os
import random

# 获取配置文件路径
config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'settings.yml')

# 加载配置
try:
    with open(config_path, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)
    LOG_LEVEL = config.get('logging', {}).get('level', 'info').lower()
except Exception as e:
    print(f"加载配置文件失败: {e}")
    LOG_LEVEL = "info"  # 默认值
    config = {}

def should_log(level):
    """检查是否应该记录日志"""
    log_levels = {
        "none": 0,
        "info": 1,
        "debug": 2
    }
    
    current_level = log_levels.get(LOG_LEVEL, 1)  # 默认为info
    required_level = log_levels.get(level.lower(), 1)
    
    return current_level >= required_level

def log(message, level="info"):
    """记录日志"""
    if should_log(level):
        # 添加时间戳
        from datetime import datetime
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{timestamp}] [{level.upper()}] {message}")

def get_random_footer():
    """获取随机的footer文本"""
    try:
        footers = config.get('messages', {}).get('footers', [])
        return random.choice(footers) if footers else None
    except Exception as e:
        log(f"获取随机footer失败: {e}", "info")
        return None