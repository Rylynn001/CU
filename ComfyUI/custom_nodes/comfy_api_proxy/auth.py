import bcrypt
import jwt
import pymysql
from datetime import datetime, timedelta
from aiohttp import web
from . import config as cfg

# JWT 配置
SECRET_KEY = 'your-secret-key-change-this-in-production'  # 生产环境请改成随机字符串
ALGORITHM = 'HS256'
TOKEN_EXPIRE_HOURS = 24


def get_db_connection():
    """获取数据库连接"""
    return pymysql.connect(**cfg.get_db_config())


def verify_password(plain_password: str, hashed_password: str | bytes) -> bool:
    """验证密码"""
    # 如果数据库存的是 bytes，先转成 str
    if isinstance(hashed_password, bytes):
        hashed_password = hashed_password.decode('utf-8')
    return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password.encode('utf-8'))


def create_access_token(user_id: int, username: str) -> str:
    """生成 JWT token"""
    expire = datetime.utcnow() + timedelta(hours=TOKEN_EXPIRE_HOURS)
    payload = {
        'user_id': user_id,
        'username': username,
        'exp': expire
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> dict | None:
    """解析 JWT token"""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None


async def login_handler(request: web.Request):
    """登录接口"""
    try:
        body = await request.json()
        username = body.get('username', '').strip()
        password = body.get('password', '').strip()

        if not username or not password:
            raise web.HTTPBadRequest(reason='用户名和密码不能为空')

        # 查询用户
        conn = get_db_connection()
        try:
            with conn.cursor(pymysql.cursors.DictCursor) as cursor:
                cursor.execute(
                    'SELECT id, user_name, password FROM sys_user WHERE user_name = %s',
                    (username,)
                )
                user = cursor.fetchone()

            if not user:
                raise web.HTTPUnauthorized(reason='用户名或密码错误')

            # 验证密码
            if not verify_password(password, user['password']):
                raise web.HTTPUnauthorized(reason='用户名或密码错误')

            # 生成 token
            token = create_access_token(user['id'], user['user_name'])

            return web.json_response({
                'token': token,
                'user': {
                    'id': user['id'],
                    'username': user['user_name']
                }
            })

        finally:
            conn.close()

    except web.HTTPException:
        raise
    except Exception as e:
        raise web.HTTPInternalServerError(reason=f'登录失败: {str(e)}')


async def verify_token_handler(request: web.Request):
    """验证 token 接口"""
    auth_header = request.headers.get('Authorization', '')
    if not auth_header.startswith('Bearer '):
        raise web.HTTPUnauthorized(reason='缺少 token')

    token = auth_header[7:]
    payload = decode_token(token)

    if not payload:
        raise web.HTTPUnauthorized(reason='token 无效或已过期')

    return web.json_response({
        'user': {
            'id': payload['user_id'],
            'username': payload['username']
        }
    })


def add_auth_routes(routes):
    """注册认证路由"""
    routes.post('/auth/login')(login_handler)
    routes.get('/auth/verify')(verify_token_handler)
