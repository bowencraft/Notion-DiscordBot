from database import SessionLocal, engine
import models
import os

# 删除现有的数据库文件
db_path = 'database/clients.sqlite'
if os.path.exists(db_path):
    os.remove(db_path)
    print(f"Removed existing database: {db_path}")

# 创建新的数据库和表
models.Base.metadata.create_all(bind=engine)
print("Created new database with updated schema")