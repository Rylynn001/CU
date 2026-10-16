"""认证相关数据库操作"""
from typing import Optional
from database import execute_query


def get_user_by_username(username: str) -> Optional[dict]:
    """根据用户名获取用户信息"""
    return execute_query(
        'SELECT id, user_name, password, real_name FROM sys_user WHERE user_name = %s',
        (username,),
        fetch_one=True
    )
