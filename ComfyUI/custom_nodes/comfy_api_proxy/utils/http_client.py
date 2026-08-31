import time
from typing import Optional, Dict, Any
import requests
import urllib3
from requests.exceptions import RequestException

# 内网服务使用自签名证书，跳过校验后抑制对应的警告日志
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class HttpClient:
    """HTTP 客户端工具类，支持 GET 和 POST 请求，自动重试 3 次"""

    def __init__(self, timeout: int = 30, retry_delay: float = 1.0):
        """
        初始化 HTTP 客户端

        Args:
            timeout: 请求超时时间（秒）
            retry_delay: 重试间隔时间（秒）
        """
        self.timeout = timeout
        self.retry_delay = retry_delay
        self.max_retries = 3

    def get(
        self,
        url: str,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """
        发送 GET 请求，失败自动重试 3 次

        Args:
            url: 请求地址
            params: 查询参数
            headers: 请求头

        Returns:
            响应 JSON 数据

        Raises:
            RequestException: 重试 3 次后仍然失败
        """
        return self._request('GET', url, params=params, headers=headers)

    def post(
        self,
        url: str,
        data: Optional[Dict[str, Any]] = None,
        json: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """
        发送 POST 请求，失败自动重试 3 次

        Args:
            url: 请求地址
            data: 表单数据
            json: JSON 数据
            headers: 请求头

        Returns:
            响应 JSON 数据

        Raises:
            RequestException: 重试 3 次后仍然失败
        """
        return self._request('POST', url, data=data, json=json, headers=headers)

    def _request(
        self,
        method: str,
        url: str,
        **kwargs
    ) -> Dict[str, Any]:
        """
        执行 HTTP 请求，支持重试

        Args:
            method: 请求方法 (GET/POST)
            url: 请求地址
            **kwargs: requests 库的其他参数

        Returns:
            响应 JSON 数据

        Raises:
            RequestException: 重试 3 次后仍然失败
        """
        last_exception = None

        for attempt in range(self.max_retries):
            try:
                response = requests.request(
                    method=method,
                    url=url,
                    timeout=self.timeout,
                    verify=False,
                    **kwargs
                )
                response.raise_for_status()
                return response.json()

            except RequestException as e:
                last_exception = e
                if attempt < self.max_retries - 1:
                    time.sleep(self.retry_delay)
                continue

        raise RequestException(
            f"请求失败，已重试 {self.max_retries} 次: {url}, 原因: {last_exception}"
        ) from last_exception


# 全局单例
_default_client = None


def get_default_client() -> HttpClient:
    """获取默认的 HTTP 客户端实例"""
    global _default_client
    if _default_client is None:
        _default_client = HttpClient()
    return _default_client


def get(url: str, **kwargs) -> Dict[str, Any]:
    """便捷的 GET 请求方法"""
    return get_default_client().get(url, **kwargs)


def post(url: str, **kwargs) -> Dict[str, Any]:
    """便捷的 POST 请求方法"""
    return get_default_client().post(url, **kwargs)
