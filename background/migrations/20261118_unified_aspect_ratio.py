"""统一已有模型比例配置。运行：python migrations/20261118_unified_aspect_ratio.py"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.aspect_ratios import model_parameter_config
from database import get_db


def migrate():
    with get_db() as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT id, name, type, parameters FROM api_models WHERE type IN ('image', 'video') FOR UPDATE")
            models = cursor.fetchall()
            changed = 0
            for model in models:
                previous = model['parameters']
                if isinstance(previous, str):
                    previous = json.loads(previous)
                config = model_parameter_config(model['type'], previous)
                if config != previous:
                    cursor.execute('UPDATE api_models SET parameters = %s WHERE id = %s',
                                   (json.dumps(config, ensure_ascii=False), model['id']))
                    changed += 1
                print(f'{model["id"]}: {model["name"]} 比例字段 1 个，选项 {len(config["fields"][0]["options"])} 个')
        connection.commit()
    print(f'已检查 {len(models)} 个模型，更新 {changed} 个；其他参数保持原值。')


if __name__ == '__main__':
    migrate()
