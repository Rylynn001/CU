import logging
from server import PromptServer
from ..repositories.asset_repo import save_output_asset

logger = logging.getLogger('comfy_api_proxy')


def setup_asset_hook(server: PromptServer):
    """监听 task_done，从 history 中提取图片信息并保存到数据库"""
    original_task_done = server.prompt_queue.task_done

    def wrapped_task_done(item_id, history_result, status, process_item=None):
        try:
            prompt_data = server.prompt_queue.currently_running.get(item_id)

            if not prompt_data:
                logger.warning(f'[asset] 未找到 item_id={item_id} 的 prompt_data')
            else:
                logger.info(f'[asset] task_done 已触发，item_id={item_id}')

                if len(prompt_data) > 3:
                    extra_data = prompt_data[3]
                    user_id = extra_data.get('user_id') if isinstance(extra_data, dict) else None
                    logger.info(f'[asset] 提取 user_id={user_id}')

                    if user_id and history_result:
                        outputs = history_result.get('outputs', {})
                        for node_id, node_output in outputs.items():
                            for img in node_output.get('images', []):
                                filename = img.get('filename')
                                subfolder = img.get('subfolder', '')
                                if filename:
                                    location = f"{subfolder}/{filename}" if subfolder else filename
                                    logger.info(f'[asset] 保存中: user_id={user_id}, location={location}')
                                    try:
                                        save_output_asset(location, int(user_id), 'picture')
                                    except Exception as e:
                                        logger.error(f'[asset] 保存失败: {e}')
                    else:
                        logger.warning(f'[asset] 未找到 user_id 或无 history_result')
                else:
                    logger.warning(f'[asset] prompt_data 长度不足: {len(prompt_data)}')

        except Exception as e:
            logger.error(f'[asset] hook 异常: {e}', exc_info=True)

        return original_task_done(item_id, history_result, status, process_item)

    server.prompt_queue.task_done = wrapped_task_done
    logger.info('[asset] hook 已安装到 task_done')
