import os
import json
import numpy as np
from PIL import Image
from PIL.PngImagePlugin import PngInfo
import folder_paths
import pymysql
from comfy.cli_args import args

# 数据库配置
DB_CONFIG = {
    'host': 'localhost',
    'user': 'root',
    'password': '123456',
    'database': 'comfyui',
    'charset': 'utf8mb4',
}


class SaveImageUser:
    """
    按用户 ID 分目录保存图片，并写入 assets 表
    """
    def __init__(self):
        self.output_dir = folder_paths.get_output_directory()
        self.type = "output"
        self.compress_level = 4

    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "images": ("IMAGE", ),
                "filename_prefix": ("STRING", {"default": "ComfyUI"}),
            },
            "hidden": {
                "prompt": "PROMPT",
                "extra_pnginfo": "EXTRA_PNGINFO",
                "unique_id": "UNIQUE_ID"
            },
        }

    RETURN_TYPES = ()
    FUNCTION = "save_images"
    OUTPUT_NODE = True
    CATEGORY = "image"

    def save_images(self, images, filename_prefix="ComfyUI", prompt=None, extra_pnginfo=None, unique_id=None):
        # 从 extra_pnginfo 或 prompt 中获取 user_id
        user_id = None
        if extra_pnginfo and 'user_id' in extra_pnginfo:
            user_id = extra_pnginfo['user_id']
        elif prompt and isinstance(prompt, dict):
            # 尝试从 prompt 的 _meta 中获取
            for node_id, node_data in prompt.items():
                if isinstance(node_data, dict) and '_meta' in node_data:
                    user_id = node_data['_meta'].get('user_id')
                    if user_id:
                        break

        if not user_id:
            raise ValueError("user_id not found in prompt metadata")

        # 按用户 ID 创建子目录
        user_output_dir = os.path.join(self.output_dir, f"user_{user_id}")
        os.makedirs(user_output_dir, exist_ok=True)

        # 生成文件路径
        full_output_folder, filename, counter, subfolder, filename_prefix = \
            folder_paths.get_save_image_path(filename_prefix, user_output_dir, images[0].shape[1], images[0].shape[0])

        results = []
        for (batch_number, image) in enumerate(images):
            # 转换图片格式
            i = 255. * image.cpu().numpy()
            img = Image.fromarray(np.clip(i, 0, 255).astype(np.uint8))

            # 添加元数据
            metadata = None
            if not args.disable_metadata:
                metadata = PngInfo()
                if prompt is not None:
                    metadata.add_text("prompt", json.dumps(prompt))
                if extra_pnginfo is not None:
                    for x in extra_pnginfo:
                        metadata.add_text(x, json.dumps(extra_pnginfo[x]))

            # 生成文件名
            filename_with_batch_num = filename.replace("%batch_num%", str(batch_number))
            file = f"{filename_with_batch_num}_{counter:05}_.png"
            file_path = os.path.join(full_output_folder, file)

            # 保存图片
            img.save(file_path, pnginfo=metadata, compress_level=self.compress_level)

            # 相对路径（用于存数据库）
            relative_path = os.path.join(f"user_{user_id}", subfolder, file).replace("\\", "/") if subfolder else os.path.join(f"user_{user_id}", file).replace("\\", "/")

            # 写入数据库
            try:
                conn = pymysql.connect(**DB_CONFIG)
                with conn.cursor() as cursor:
                    cursor.execute(
                        "INSERT INTO assets (location, rfid) VALUES (%s, %s)",
                        (relative_path, user_id)
                    )
                    conn.commit()
                conn.close()
            except Exception as e:
                print(f"[SaveImageUser] Failed to insert asset: {e}")

            results.append({
                "filename": file,
                "subfolder": f"user_{user_id}/{subfolder}" if subfolder else f"user_{user_id}",
                "type": self.type
            })
            counter += 1

        return {"ui": {"images": results}}


NODE_CLASS_MAPPINGS = {
    "SaveImageUser": SaveImageUser
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "SaveImageUser": "Save Image (User)"
}
