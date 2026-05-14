import logging
import pymysql
from server import PromptServer
from . import config as cfg

logger = logging.getLogger('comfy_api_proxy')


def save_asset_to_db(user_id: int, location: str):
    """保存资产到数据库"""
    try:
        conn = pymysql.connect(**cfg.get_db_config())
        with conn.cursor() as cursor:
            cursor.execute(
                "INSERT INTO assets (location, rfid) VALUES (%s, %s)",
                (location, user_id)
            )
            conn.commit()
        conn.close()
        logger.info(f'[asset] saved: user_id={user_id}, location={location}')
    except Exception as e:
        logger.error(f'[asset] save failed: {e}')


def setup_asset_hook(server: PromptServer):
    """
    监听 task_done，从 history 中提取图片信息并保存到数据库
    """
    original_task_done = server.prompt_queue.task_done

    def wrapped_task_done(item_id, history_result, status, process_item=None):
        try:
            # 在原始方法调用之前获取 prompt_data（因为原始方法会 pop 掉）
            prompt_data = server.prompt_queue.currently_running.get(item_id)

            if not prompt_data:
                logger.warning(f'[asset] prompt_data not found for item_id={item_id}')
            else:
                logger.info(f'[asset] task_done triggered for item_id={item_id}')

                # prompt_data 结构：[client_id, prompt_id, prompt, extra_data, outputs_to_execute, ...]
                if len(prompt_data) > 3:
                    extra_data = prompt_data[3]
                    user_id = extra_data.get('user_id') if isinstance(extra_data, dict) else None
                    logger.info(f'[asset] extracted user_id={user_id} from extra_data={extra_data}')

                    if user_id and history_result:
                        # 从 history_result 中提取图片信息
                        outputs = history_result.get('outputs', {})
                        logger.info(f'[asset] outputs={outputs}')

                        for node_id, node_output in outputs.items():
                            images = node_output.get('images', [])
                            for img in images:
                                filename = img.get('filename')
                                subfolder = img.get('subfolder', '')
                                if filename:
                                    if subfolder:
                                        location = f"{subfolder}/{filename}"
                                    else:
                                        location = filename
                                    logger.info(f'[asset] saving: user_id={user_id}, location={location}')
                                    save_asset_to_db(user_id, location)
                    else:
                        logger.warning(f'[asset] user_id not found or no history_result')
                else:
                    logger.warning(f'[asset] prompt_data too short: {len(prompt_data)}')

        except Exception as e:
            logger.error(f'[asset] hook error: {e}', exc_info=True)

        # 调用原始方法（在获取数据之后）
        return original_task_done(item_id, history_result, status, process_item)

    # 替换原方法
    server.prompt_queue.task_done = wrapped_task_done
    logger.info('[asset] hook installed on task_done')
