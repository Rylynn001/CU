"""业务异常定义"""


class AppError(Exception):
    """应用基础异常"""

    def __init__(self, message: str, code: str = 'ERROR', detail: str = None):
        self.message = message
        self.code = code
        self.detail = detail  # 内部调试信息，不返回给用户
        super().__init__(message)


class ProviderError(AppError):
    """模型提供商相关错误"""

    def __init__(self, message: str, provider: str = None, detail: str = None):
        super().__init__(message, code='PROVIDER_ERROR', detail=detail)
        self.provider = provider
