#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""修复 TextToVideo.vue 中的编码错误"""

def fix_mojibake(text):
    """修复 mojibake（乱码）"""
    try:
        # 尝试将错误的字符编码回原始字节，再用正确的编码解码
        # 这些字符是 UTF-8 字节被当成 GB18030/GBK 解码的结果
        fixed = text.encode('gb18030').decode('utf-8')
        return fixed
    except (UnicodeDecodeError, UnicodeEncodeError):
        try:
            fixed = text.encode('gbk').decode('utf-8')
            return fixed
        except:
            return text

# 读取文件
input_file = 'comfy-web/src/views/TextToVideo.vue'
with open(input_file, 'r', encoding='utf-8') as f:
    content = f.read()

# 修复乱码
fixed_content = fix_mojibake(content)

# 写回文件
with open(input_file, 'w', encoding='utf-8') as f:
    f.write(fixed_content)

print("文件编码已修复")
