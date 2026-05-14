import bcrypt
import pymysql
#生成用户的脚本
# 生成密码哈希

def createUser(username:str):
    password = "123456"
    hashed = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
    hashed_str = hashed.decode('utf-8')  # 转成字符串

    print(f"Password: {password}")
    print(f"Hash: {hashed_str}")
    print()

    # 直接插入数据库
    DB_CONFIG = {
        'host': 'localhost',
        'user': 'root',
        'password': '123456',
        'database': 'comfyui',
        'charset': 'utf8mb4',
    }

    try:
        conn = pymysql.connect(**DB_CONFIG)
        with conn.cursor() as cursor:
            # 先删除旧数据
            # cursor.execute("DELETE FROM sys_user WHERE user_name IN ('admin', 'zhang''san', 'lisi')")

            # 插入新用户
            cursor.execute(
                "INSERT INTO sys_user (user_name, password) VALUES (%s, %s)",
                (username, hashed_str)
            )
            conn.commit()
            # print("User 'admin' created successfully!")
        conn.close()
    except Exception as e:
        print(f"Error: {e}")

if __name__ == '__main__':
    createUser('wangwu')



