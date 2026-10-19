"""第三方 API 错误转换器"""
import re
import logging
from .errors import ProviderError

logger = logging.getLogger(__name__)


def parse_ark_response_error(error_code: str, error_message: str) -> str:
    """解析 Ark API 响应中的错误码和错误信息，返回用户友好提示

    Args:
        error_code: Ark 返回的 error.code
        error_message: Ark 返回的 error.message

    Returns:
        用户友好的错误提示
    """
    # 版权/侵权相关
    if 'copyright' in error_code.lower() or 'copyright' in error_message.lower():
        return '内容可能涉及版权问题，请修改提示词后重试'

    # 敏感内容/违规
    if 'sensitive' in error_code.lower() or 'policy' in error_code.lower():
        return '内容不符合安全规范，请修改提示词后重试'

    # 配额/余额
    if 'quota' in error_code.lower() or 'insufficient' in error_message.lower():
        return '账户配额不足，请充值后重试'

    # 认证
    if 'auth' in error_code.lower() or 'unauthorized' in error_message.lower():
        return 'API Key 无效或已过期，请检查配置'

    # 参数错误
    if 'invalid' in error_code.lower() or 'parameter' in error_message.lower():
        return '请求参数不符合要求，请检查输入'

    # 超时
    if 'timeout' in error_code.lower() or 'timeout' in error_message.lower():
        return '请求超时，请稍后重试'

    # 服务不可用
    if 'unavailable' in error_code.lower() or 'service' in error_message.lower():
        return '服务暂时不可用，请稍后重试'

    # 未识别的错误，返回原始消息（已经比较清晰）
    logger.warning(f'未识别的 Ark 错误码: {error_code}')
    return error_message or '视频生成失败，请稍后重试'


def parse_openai_error(exc: Exception, provider: str = 'openai') -> ProviderError:
    """解析 OpenAI SDK 错误，提取用户可理解的信息"""
    error_str = str(exc)

    # API Key 错误
    if 'authentication' in error_str.lower() or 'api key' in error_str.lower() or '401' in error_str:
        return ProviderError(
            message='API Key 无效或已过期，请检查配置',
            provider=provider,
            detail=error_str
        )

    # 余额不足
    if 'insufficient' in error_str.lower() or 'quota' in error_str.lower() or 'balance' in error_str.lower():
        return ProviderError(
            message='账户余额不足，请充值后重试',
            provider=provider,
            detail=error_str
        )

    # 超时
    if 'timeout' in error_str.lower() or 'timed out' in error_str.lower():
        return ProviderError(
            message='请求超时，请稍后重试',
            provider=provider,
            detail=error_str
        )

    # 速率限制
    if 'rate limit' in error_str.lower() or '429' in error_str:
        return ProviderError(
            message='请求过于频繁，请稍后再试',
            provider=provider,
            detail=error_str
        )

    # 内容违规
    if 'content_policy' in error_str.lower() or 'safety' in error_str.lower():
        return ProviderError(
            message='内容不符合安全规范，请修改后重试',
            provider=provider,
            detail=error_str
        )

    # 参数错误
    if 'invalid' in error_str.lower() or '400' in error_str:
        # 尝试提取具体参数名
        match = re.search(r'parameter[:\s]+["\']?(\w+)["\']?', error_str, re.IGNORECASE)
        if match:
            param_name = match.group(1)
            return ProviderError(
                message=f'参数 {param_name} 不符合要求，请检查输入',
                provider=provider,
                detail=error_str
            )
        return ProviderError(
            message='请求参数不符合要求，请检查输入',
            provider=provider,
            detail=error_str
        )

    # 模型不存在
    if 'model not found' in error_str.lower() or 'does not exist' in error_str.lower():
        return ProviderError(
            message='模型不存在，请检查模型名称',
            provider=provider,
            detail=error_str
        )

    # 服务端错误
    if '500' in error_str or '502' in error_str or '503' in error_str:
        return ProviderError(
            message='模型服务暂时不可用，请稍后重试',
            provider=provider,
            detail=error_str
        )

    # 未匹配到具体错误，返回通用提示
    logger.warning(f'未识别的 {provider} 错误类型: {error_str}')
    return ProviderError(
        message='模型调用失败，请稍后重试或联系管理员',
        provider=provider,
        detail=error_str
    )


def parse_ark_error(exc: Exception) -> ProviderError:
    """解析火山引擎 Ark 错误"""
    return parse_openai_error(exc, provider='ark')


def parse_provider_error(exc: Exception, provider: str) -> ProviderError:
    """统一入口，根据 provider 类型解析错误"""
    if provider in ('openai', 'gpt'):
        return parse_openai_error(exc, provider='openai')
    elif provider == 'ark':
        return parse_ark_error(exc)
    else:
        # 默认使用通用解析
        return parse_openai_error(exc, provider=provider)
