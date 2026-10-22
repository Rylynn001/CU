"""
初始化工作流数据库表
"""
import pymysql
from dotenv import load_dotenv
import os

load_dotenv()


def init_workflow_tables():
    """初始化工作流表"""
    conn = pymysql.connect(
        host=os.getenv("DB_HOST"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        database=os.getenv("DB_NAME"),
        charset="utf8mb4"
    )

    try:
        with conn.cursor() as cursor:
            # 读取 SQL 文件
            with open("migrations/create_workflow_tables.sql", "r", encoding="utf-8") as f:
                sql_script = f.read()

            # 分割并执行 SQL 语句
            statements = sql_script.split(";")
            for statement in statements:
                statement = statement.strip()
                if statement:
                    print(f"执行: {statement[:50]}...")
                    cursor.execute(statement)

        conn.commit()
        print("\n工作流表创建成功！")

        # 验证表是否存在
        with conn.cursor() as cursor:
            cursor.execute("SHOW TABLES LIKE 'workflow_%'")
            tables = cursor.fetchall()
            print(f"\n已创建的表：")
            for table in tables:
                print(f"  - {table[0]}")

    except Exception as e:
        print(f"\n错误: {e}")
        conn.rollback()
    finally:
        conn.close()


if __name__ == "__main__":
    init_workflow_tables()
