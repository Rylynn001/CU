"""认证相关路由"""
import bcrypt
import jwt
from datetime import datetime, timedelta
from fastapi import APIRouter, HTTPException, Depends, Header
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel

from config import settings
from repositories import auth_repo

security = HTTPBearer()

router = APIRouter()


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    token: str
    user: dict


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """验证密码"""
    if isinstance(hashed_password, bytes):
        hashed_password = hashed_password.decode('utf-8')
    return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password.encode('utf-8'))


def create_access_token(user_id: int, username: str) -> str:
    """创建 JWT token"""
    expire = datetime.utcnow() + timedelta(days=settings.TOKEN_EXPIRE_DAYS)
    payload = {'user_id': user_id, 'username': username, 'exp': expire}
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_token(token: str) -> dict | None:
    """解码 JWT token"""
    try:
        return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
        return None


async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """依赖注入：获取当前用户"""
    token = credentials.credentials
    payload = decode_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="token 无效或已过期")

    return {'user_id': payload['user_id'], 'username': payload['username'], 'id': payload['user_id']}


@router.post("/login", response_model=LoginResponse)
async def login(req: LoginRequest):
    """用户登录"""
    if not req.username or not req.password:
        raise HTTPException(status_code=400, detail="用户名和密码不能为空")

    user = auth_repo.get_user_by_username(req.username)

    if not user or not verify_password(req.password, user['password']):
        raise HTTPException(status_code=401, detail="用户名或密码错误")

    token = create_access_token(user['id'], user['user_name'])
    return {
        'token': token,
        'user': {
            'id': user['id'],
            'username': user['user_name'],
            'real_name': user['real_name']
        }
    }


@router.get("/verify")
async def verify_token(current_user: dict = Depends(get_current_user)):
    """验证 token"""
    return {'user': current_user}
