from celery import shared_task

from apps.core.logger import opspilot_logger as logger
from apps.opspilot.models import Bot, BotWorkFlow
from apps.opspilot.utils.chat_flow_utils.engine.factory import create_chat_flow_engine

from apps.opspilot.tasks._common import _run_in_native_thread

@shared_task(name="apps.opspilot.tasks.chat_flow_celery_task")
def chat_flow_celery_task(bot_id, node_id, message):
    """ChatFlow周期性任务"""

    def _execute():
        logger.info(f"开始执行ChatFlow周期任务: bot_id={bot_id}, node_id={node_id}")
        bot_obj = Bot.objects.filter(id=bot_id, online=True).first()
        if not bot_obj:
            logger.error(f"Bot {bot_id} 不存在或已下线")
            return
        bot_chat_flow = BotWorkFlow.objects.filter(bot_id=bot_obj.id).first()
        if not bot_chat_flow:
            logger.error(f"Bot {bot_id} 没有配置ChatFlow")
            return
        try:
            engine = create_chat_flow_engine(bot_chat_flow, node_id, entry_type="celery")
            input_data = {
                "last_message": message,
                "user_id": bot_obj.created_by,
                "bot_id": bot_id,
                "node_id": node_id,
                "entry_type": "celery",
            }
            result = engine.execute(input_data)
            logger.info(f"ChatFlow周期任务执行完成: bot_id={bot_id}, node_id={node_id}, 执行结果为{result}")
        except Exception as e:
            logger.exception(f"ChatFlow周期任务执行失败: bot_id={bot_id}, node_id={node_id}, error={str(e)}")

    return _run_in_native_thread(_execute)


@shared_task(name="apps.opspilot.tasks.chat_flow_test_execute_task")
def chat_flow_test_execute_task(workflow_id, node_id, input_data, entry_type, execution_id):
    """ChatFlow测试异步任务"""

    def _execute():
        logger.info(f"开始执行ChatFlow测试异步任务: workflow_id={workflow_id}, node_id={node_id}, execution_id={execution_id}")
        workflow = BotWorkFlow.objects.filter(id=workflow_id).first()
        if not workflow:
            logger.error(f"ChatFlow测试异步任务失败: workflow_id={workflow_id} 不存在")
            return

        try:
            engine = create_chat_flow_engine(workflow, node_id, entry_type=entry_type, execution_id=execution_id)
            if entry_type:
                engine.entry_type = entry_type
            # 来自配置页"测试"的执行，标记 is_test，便于与真实对话执行区分
            engine.is_test = True
            engine.execute(input_data)
            logger.info(f"ChatFlow测试异步任务完成: workflow_id={workflow_id}, node_id={node_id}, execution_id={execution_id}")
        except Exception as e:
            logger.exception(f"ChatFlow测试异步任务失败: workflow_id={workflow_id}, node_id={node_id}, execution_id={execution_id}, error={str(e)}")

    return _run_in_native_thread(_execute)
