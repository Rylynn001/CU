"""创建用户脚本"""
import bcrypt
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def create_user(username: str, password: str = '123456'):
    from ..config import get_db_config
    import pymysql

    hashed = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    config = get_db_config()

    try:
        conn = pymysql.connect(**config)
        with conn.cursor() as cursor:
            cursor.execute(
                "INSERT INTO sys_user (user_name, password) VALUES (%s, %s)",
                (username, hashed)
            )
            conn.commit()
        conn.close()
        print(f"用户 '{username}' 创建成功")
    except Exception as e:
        print(f"错误: {e}")


if __name__ == '__main__':
    username = sys.argv[1] if len(sys.argv) > 1 else 'admin'
    password = sys.argv[2] if len(sys.argv) > 2 else '123456'
    create_user(username, password)
