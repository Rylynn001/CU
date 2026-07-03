#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
迁移脚本：将 history.input_file 字段迁移到 history_input_assets_rel 关联表
运行方式：cd ComfyUI && python custom_nodes/comfy_api_proxy/migrate_to_input_rel.py
"""
import sys
import os

# 将 ComfyUI 根目录加入 sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from custom_nodes.comfy_api_proxy.repositories.database import get_db_connection


def create_table():
    """创建 history_input_assets_rel 表"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS history_input_assets_rel (
                history_id BIGINT NOT NULL,
                asset_id BIGINT NOT NULL,
                INDEX idx_history_id (history_id),
                INDEX idx_asset_id (asset_id)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)
        conn.commit()
        print("[√] 已创建 history_input_assets_rel 表（如不存在）")


def migrate_data():
    """将 history.input_file 逗号分隔的 ID 拆到关联表"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, input_file FROM history WHERE input_file IS NOT NULL AND input_file != ''")
        rows = cursor.fetchall()

        total = len(rows)
        if total == 0:
            print("[√] 无需迁移，input_file 全为空")
            return

        print(f"[→] 共 {total} 条历史记录待迁移")

        insert_values = []
        for row in rows:
            history_id = row['id']
            ids = [x.strip() for x in row['input_file'].split(',') if x.strip()]
            for asset_id_str in ids:
                try:
                    asset_id = int(asset_id_str)
                    insert_values.append((history_id, asset_id))
                except ValueError:
                    print(f"[!] history_id={history_id} input_file 包含非法值: {asset_id_str}")

        if insert_values:
            cursor.executemany(
                "INSERT IGNORE INTO history_input_assets_rel (history_id, asset_id) VALUES (%s, %s)",
                insert_values
            )
            conn.commit()
            print(f"[√] 已迁移 {len(insert_values)} 条输入资产关联记录")
        else:
            print("[√] 无有效数据可迁移")


def verify():
    """验证迁移结果"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) AS cnt FROM history WHERE input_file IS NOT NULL AND input_file != ''")
        old_count = cursor.fetchone()['cnt']
        cursor.execute("SELECT COUNT(*) AS cnt FROM history_input_assets_rel")
        new_count = cursor.fetchone()['cnt']
        print(f"[i] history.input_file 非空记录数: {old_count}")
        print(f"[i] history_input_assets_rel 关联记录数: {new_count}")
        if new_count > 0:
            print("[√] 迁移成功，关联表已有数据")
        else:
            print("[!] 关联表为空，请检查是否有历史数据")


if __name__ == '__main__':
    try:
        print("=== 迁移 history.input_file → history_input_assets_rel ===")
        create_table()
        migrate_data()
        verify()
        print("\n[√] 迁移完成！现在可以重启 ComfyUI 后端")
        print("[!] 注意：旧字段 input_file/output_file 暂未删除，建议验证无误后手动删除")
    except Exception as e:
        import traceback
        print(f"\n[✗] 迁移失败: {e}", file=sys.stderr)
        traceback.print_exc()
        sys.exit(1)
