#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""修复文件编码问题：将错误的 UTF-8 编码修复回来"""

import sys

def fix_file_encoding(file_path):
    """修复文件编码"""
    try:
        # 以二进制模式读取
        with open(file_path, 'rb') as f:
            content_bytes = f.read()

        # 尝试以 UTF-8 解码
        try:
            content = content_bytes.decode('utf-8')
            print(f"文件已经是正确的 UTF-8 编码")
            return True
        except UnicodeDecodeError:
            print(f"文件不是有效的 UTF-8 编码，尝试修复...")

        # 尝试其他编码
        for encoding in ['gbk', 'gb2312', 'gb18030', 'latin1']:
            try:
                content = content_bytes.decode(encoding)
                # 写回文件，使用 UTF-8 编码
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(content)
                print(f"成功修复：{encoding} -> UTF-8")
                return True
            except (UnicodeDecodeError, UnicodeEncodeError):
                continue

        print("无法修复文件编码")
        return False

    except Exception as e:
        print(f"错误: {e}")
        return False

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("用法: python fix_encoding.py <文件路径>")
        sys.exit(1)

    file_path = sys.argv[1]
    fix_file_encoding(file_path)
