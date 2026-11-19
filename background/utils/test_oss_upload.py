"""只做一次同步上传，失败时对比双方签名；不读取项目配置或 .env。"""
import base64
import hashlib
import hmac
import os
import platform
import time
import uuid

import oss2

# 只需在这里填写凭据，Windows 和 Linux 使用同一份文件。
ACCESS_KEY_ID = ""
ACCESS_KEY_SECRET = ""
ENDPOINT = "https://oss-cn-beijing.aliyuncs.com"
BUCKET_NAME = "fengyuanbo-ai"


class DiagnosticAuth(oss2.Auth):
    """保留 SDK 本次实际使用的签名原文，不改变签名算法。"""

    def _sign_request(self, req, bucket_name, key):
        super()._sign_request(req, bucket_name, key)
        # 项目固定使用 oss2==2.19.1；直接取 SDK 原文，避免另写一套规范化逻辑。
        self.sign_bytes = self._ProviderAuth__get_bytes_to_sign(req, bucket_name, key)
        self.signature = req.headers['authorization'].split(':', 1)[1]


def diagnose_signature(error, auth, secret):
    details = error.details
    server_signature = details.get('SignatureProvided')
    server_id = details.get('OSSAccessKeyId')
    if server_id and server_id != ACCESS_KEY_ID.strip():
        print('结论：OSS 收到的 AccessKey ID 与脚本使用的不同，请检查代理或请求拦截。')
        return
    if server_signature and server_signature != auth.signature:
        print('结论：签名生成后发生了变化，OSS 收到的签名与 SDK 发出的不同。')
        print('请检查 HTTP 代理、网关或请求拦截代码。')
        return

    server_hex = details.get('StringToSignBytes')
    server_text = details.get('StringToSign')
    if server_hex:
        try:
            server_bytes = bytes.fromhex(server_hex)
        except ValueError:
            print('结论：OSS 返回的签名字节无法解析，暂时不能判断根因。')
            return
    elif server_text is not None:
        server_bytes = server_text.encode('utf-8')
    else:
        print('结论：OSS 未返回签名原文，无法区分密钥错误和请求内容变化。')
        return

    local_signature = base64.b64encode(
        hmac.new(secret.encode('utf-8'), auth.sign_bytes, hashlib.sha1).digest()
    ).decode('ascii')
    if local_signature != auth.signature:
        print('结论：SDK 签名与独立 HMAC-SHA1 计算结果不同，请检查 SDK 安装或运行时修改。')
    elif server_bytes != auth.sign_bytes:
        print('结论：客户端与 OSS 使用的签名原文不同。以下差异是直接证据：')
        local_lines = auth.sign_bytes.decode('utf-8').split('\n')
        server_lines = server_bytes.decode('utf-8').split('\n')
        fields = ['请求方法', 'Content-MD5', 'Content-Type', '日期', 'OSS 请求头或资源路径']
        for index in range(max(len(local_lines), len(server_lines))):
            local = local_lines[index] if index < len(local_lines) else None
            remote = server_lines[index] if index < len(server_lines) else None
            if local != remote:
                field = fields[min(index, len(fields) - 1)]
                print(f'  {field}：客户端={local!r}；OSS={remote!r}')
        print('请检查代理、网关是否改写上述字段，以及 SDK 的版本是否一致。')
    elif server_signature:
        print('结论：双方签名原文相同、签名传输未变，且本地 HMAC-SHA1 计算正确。')
        print('故障定位在凭据配对：此 Secret 与 OSS 当前保存的该 AccessKey ID 不匹配。')
        print('请确认 ID 和 Secret 来自同一对有效密钥，而不是混用或复制了旧 Secret。')
    else:
        print('结论：双方签名原文相同，但 OSS 未返回收到的签名，尚不能排除签名被改写。')


def main():
    key_id, secret = ACCESS_KEY_ID.strip(), ACCESS_KEY_SECRET.strip()
    if not key_id or not secret:
        print('请先填写文件顶部的 ACCESS_KEY_ID 和 ACCESS_KEY_SECRET。')
        return 1
    if any(c.isspace() or not c.isascii() or c in "\"'" for c in key_id + secret):
        print('结论：凭据中混入了空白、引号或非 ASCII 字符，请重新粘贴。')
        return 1

    print(f'环境：{platform.system()}，Python {platform.python_version()}，oss2 {oss2.__version__}')
    print(f'UTC 时间：{time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime())}')
    print(f'密钥指纹：{hashlib.sha256((key_id + ":" + secret).encode()).hexdigest()[:12]}（两端应一致）')
    proxy_names = [name for name in os.environ if name.lower() in ('http_proxy', 'https_proxy', 'all_proxy')]
    print(f'代理环境变量：{", ".join(sorted(proxy_names)) or "无"}')
    auth = DiagnosticAuth(key_id, secret)
    object_name = f'seedance/oss_diagnostic_{uuid.uuid4().hex}.png'
    # 有效的 1×1 PNG，保留与实际上传相同的 Content-Type。
    data = base64.b64decode(
        'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII='
    )
    try:
        bucket = oss2.Bucket(auth, ENDPOINT, BUCKET_NAME, connect_timeout=20)
        result = bucket.put_object(object_name, data, headers={'Content-Type': 'image/png'})
    except oss2.exceptions.ServerError as error:
        print(f'上传失败：HTTP {error.status}，{error.code}，请求编号 {error.request_id}')
        if error.code == 'SignatureDoesNotMatch':
            diagnose_signature(error, auth, secret)
        else:
            reasons = {
                'InvalidAccessKeyId': 'AccessKey ID 不存在或已失效，请检查填写的 ID。',
                'RequestTimeTooSkewed': '服务器时钟偏差过大，请在 Linux 宿主机同步系统时间。',
                'AccessDenied': 'OSS 拒绝访问，请检查 RAM 上传权限、Bucket 策略及来源 IP 限制。',
                'NoSuchBucket': 'Bucket 名称不存在，请检查 BUCKET_NAME。',
                'PermanentRedirect': '访问的 Endpoint 与 Bucket 所在地域不匹配。',
                'InvalidSecurityToken': '安全令牌无效，临时凭据不能只填写 ID 和 Secret。',
                'SecurityTokenExpired': '临时凭据的安全令牌已过期。',
            }
            print('结论：' + reasons.get(error.code, '当前错误不是签名不匹配，需要结合 OSS 错误信息继续排查。'))
            print(f'OSS 信息：{error.message}')
        return 1
    except oss2.exceptions.RequestError as error:
        print(f'结论：请求未正常获得 OSS 响应，属于网络、DNS、证书或代理问题（{type(error.exception).__name__}）。')
        return 1
    finally:
        if 'bucket' in locals():
            bucket.session.session.close()

    print(f'上传成功，请求编号：{result.request_id}')
    print(f'测试对象：{object_name}（保留在 OSS 中）')
    print('结论：本次手填凭据和同步上传有效；若业务仍失败，应检查业务进程实际读取的凭据和请求。')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
