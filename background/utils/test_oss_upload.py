"""OSS 上传测试脚本 - 用于排查签名问题"""
import os
import sys
import pathlib
import asyncio
import time
import logging
from io import BytesIO

# 添加项目路径
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

from config import settings

# 配置日志
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


def print_env_info():
    """打印环境信息"""
    print("\n" + "="*80)
    print("环境信息检查")
    print("="*80)

    # 系统信息
    import platform
    print(f"操作系统: {platform.system()} {platform.release()}")
    print(f"Python 版本: {platform.python_version()}")
    print(f"当前时间: {time.strftime('%Y-%m-%d %H:%M:%S %Z', time.localtime())}")
    print(f"UTC 时间: {time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime())} UTC")

    # OSS 配置
    print("\n" + "-"*80)
    print("OSS 配置读取")
    print("-"*80)
    print(f"OSS_ACCESS_KEY_ID: {settings.OSS_ACCESS_KEY_ID[:8]}...{settings.OSS_ACCESS_KEY_ID[-4:] if settings.OSS_ACCESS_KEY_ID else 'None'}")
    print(f"OSS_ACCESS_KEY_SECRET 长度: {len(settings.OSS_ACCESS_KEY_SECRET) if settings.OSS_ACCESS_KEY_SECRET else 0}")
    print(f"OSS_ACCESS_KEY_SECRET 开头: {settings.OSS_ACCESS_KEY_SECRET[:4] if settings.OSS_ACCESS_KEY_SECRET else 'None'}...")
    print(f"OSS_ACCESS_KEY_SECRET 结尾: ...{settings.OSS_ACCESS_KEY_SECRET[-4:] if settings.OSS_ACCESS_KEY_SECRET else 'None'}")
    print(f"OSS_ENDPOINT: {settings.OSS_ENDPOINT}")
    print(f"OSS_BUCKET_NAME: {settings.OSS_BUCKET_NAME}")

    # 检查是否有空格或特殊字符
    if settings.OSS_ACCESS_KEY_SECRET:
        has_space = ' ' in settings.OSS_ACCESS_KEY_SECRET
        has_newline = '\n' in settings.OSS_ACCESS_KEY_SECRET or '\r' in settings.OSS_ACCESS_KEY_SECRET
        print(f"密钥包含空格: {has_space}")
        print(f"密钥包含换行符: {has_newline}")

    # oss2 版本
    try:
        import oss2
        print(f"\noss2 版本: {oss2.__version__}")
    except Exception as e:
        print(f"\noss2 导入失败: {e}")

    print("="*80 + "\n")


def test_sync_upload():
    """测试1: 同步上传（原始方式）"""
    print("\n" + "="*80)
    print("测试1: 同步上传")
    print("="*80)

    try:
        import oss2

        # 创建测试数据
        test_data = b"Test image data from sync upload"
        object_name = f"seedance/test_sync_{int(time.time())}.png"

        logger.info(f"开始同步上传: {object_name}")
        logger.debug(f"创建 Auth 对象...")
        auth = oss2.Auth(settings.OSS_ACCESS_KEY_ID, settings.OSS_ACCESS_KEY_SECRET)

        logger.debug(f"创建 Bucket 对象...")
        bucket = oss2.Bucket(auth, settings.OSS_ENDPOINT, settings.OSS_BUCKET_NAME)

        logger.debug(f"调用 put_object...")
        result = bucket.put_object(object_name, test_data)

        file_url = f"https://{settings.OSS_BUCKET_NAME}.{settings.OSS_ENDPOINT.replace('https://', '').replace('http://', '')}/{object_name}"

        logger.info(f"✓ 同步上传成功!")
        logger.info(f"  RequestId: {result.request_id}")
        logger.info(f"  Status: {result.status}")
        logger.info(f"  URL: {file_url}")

        return True, file_url

    except Exception as e:
        logger.error(f"✗ 同步上传失败!")
        logger.error(f"  错误类型: {type(e).__name__}")
        logger.error(f"  错误信息: {str(e)}")
        if hasattr(e, 'details'):
            logger.error(f"  详细信息: {e.details}")
        return False, str(e)


async def test_async_to_thread():
    """测试2: asyncio.to_thread 上传（问题复现）"""
    print("\n" + "="*80)
    print("测试2: asyncio.to_thread 上传（复现问题场景）")
    print("="*80)

    try:
        import oss2

        # 在主线程创建对象
        logger.debug(f"在主线程创建 Auth 和 Bucket...")
        auth = oss2.Auth(settings.OSS_ACCESS_KEY_ID, settings.OSS_ACCESS_KEY_SECRET)
        bucket = oss2.Bucket(auth, settings.OSS_ENDPOINT, settings.OSS_BUCKET_NAME)

        test_data = b"Test image data from async to_thread"
        object_name = f"seedance/test_async_{int(time.time())}.png"

        logger.info(f"开始 asyncio.to_thread 上传: {object_name}")
        logger.debug(f"调用 asyncio.to_thread(bucket.put_object, ...)...")

        result = await asyncio.to_thread(bucket.put_object, object_name, test_data)

        file_url = f"https://{settings.OSS_BUCKET_NAME}.{settings.OSS_ENDPOINT.replace('https://', '').replace('http://', '')}/{object_name}"

        logger.info(f"✓ asyncio.to_thread 上传成功!")
        logger.info(f"  RequestId: {result.request_id}")
        logger.info(f"  Status: {result.status}")
        logger.info(f"  URL: {file_url}")

        return True, file_url

    except Exception as e:
        logger.error(f"✗ asyncio.to_thread 上传失败!")
        logger.error(f"  错误类型: {type(e).__name__}")
        logger.error(f"  错误信息: {str(e)}")
        if hasattr(e, 'details'):
            logger.error(f"  详细信息: {e.details}")
        return False, str(e)


async def test_async_recreate_in_thread():
    """测试3: 在线程中重新创建 bucket（修复方案）"""
    print("\n" + "="*80)
    print("测试3: 在线程中重新创建 bucket（修复方案）")
    print("="*80)

    def _upload_in_thread(access_key_id, access_key_secret, endpoint, bucket_name, object_name, file_data):
        """在线程中重新创建 bucket 并上传"""
        import oss2
        logger.debug(f"线程内创建 Auth 和 Bucket...")
        auth = oss2.Auth(access_key_id, access_key_secret)
        bucket = oss2.Bucket(auth, endpoint, bucket_name)
        logger.debug(f"线程内调用 put_object...")
        return bucket.put_object(object_name, file_data)

    try:
        test_data = b"Test image data from recreate in thread"
        object_name = f"seedance/test_recreate_{int(time.time())}.png"

        logger.info(f"开始在线程中重新创建上传: {object_name}")

        result = await asyncio.to_thread(
            _upload_in_thread,
            settings.OSS_ACCESS_KEY_ID,
            settings.OSS_ACCESS_KEY_SECRET,
            settings.OSS_ENDPOINT,
            settings.OSS_BUCKET_NAME,
            object_name,
            test_data
        )

        file_url = f"https://{settings.OSS_BUCKET_NAME}.{settings.OSS_ENDPOINT.replace('https://', '').replace('http://', '')}/{object_name}"

        logger.info(f"✓ 线程内重建上传成功!")
        logger.info(f"  RequestId: {result.request_id}")
        logger.info(f"  Status: {result.status}")
        logger.info(f"  URL: {file_url}")

        return True, file_url

    except Exception as e:
        logger.error(f"✗ 线程内重建上传失败!")
        logger.error(f"  错误类型: {type(e).__name__}")
        logger.error(f"  错误信息: {str(e)}")
        if hasattr(e, 'details'):
            logger.error(f"  详细信息: {e.details}")
        return False, str(e)


async def main():
    """运行所有测试"""
    print("\n" + "█"*80)
    print("OSS 上传测试工具")
    print("█"*80)

    # 打印环境信息
    print_env_info()

    # 测试结果汇总
    results = []

    # 测试1: 同步上传
    success1, result1 = test_sync_upload()
    results.append(("同步上传", success1, result1))

    # 测试2: asyncio.to_thread（问题场景）
    success2, result2 = await test_async_to_thread()
    results.append(("asyncio.to_thread", success2, result2))

    # 测试3: 线程内重建（修复方案）
    success3, result3 = await test_async_recreate_in_thread()
    results.append(("线程内重建", success3, result3))

    # 打印汇总
    print("\n" + "="*80)
    print("测试结果汇总")
    print("="*80)
    for test_name, success, result in results:
        status = "✓ 成功" if success else "✗ 失败"
        print(f"{test_name:20} {status}")
        if not success:
            print(f"  错误: {result[:100]}...")
    print("="*80 + "\n")

    # 返回结果
    all_success = all(r[1] for r in results)
    if all_success:
        print("✓ 所有测试通过")
        return 0
    else:
        print("✗ 部分测试失败")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
