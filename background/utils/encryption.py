from cryptography.fernet import Fernet


def encrypt(key: bytes, plaintext: str) -> str:
    return Fernet(key).encrypt(plaintext.encode()).decode()


def decrypt(key: bytes, token: str) -> str:
    return Fernet(key).decrypt(token.encode()).decode()


def decrypt_api_key(token: str) -> str:
    """用 .env 中的 ENCRYPTION_KEY 解密数据库里存的 api_key"""
    from .. import config as cfg
    key = cfg.get_encryption_key()
    if not key:
        raise RuntimeError("ENCRYPTION_KEY 未配置")
    return decrypt(key.encode(), token)


if __name__ == "__main__":
    key = Fernet.generate_key()
    api_key = "sk-xxxxx"
    encrypted = encrypt('6-7IoCKOYES4j3va1auuTGlwmCJnX-TQve1EH3CeLrk=', api_key)
    result = decrypt('6-7IoCKOYES4j3va1auuTGlwmCJnX-TQve1EH3CeLrk=', encrypted)
    print(f"密钥:{'6-7IoCKOYES4j3va1auuTGlwmCJnX-TQve1EH3CeLrk='}")
    print(f"加密后:{encrypted}")
    print(f"解密后:{result}")
