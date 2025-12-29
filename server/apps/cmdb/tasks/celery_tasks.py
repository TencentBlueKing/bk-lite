# -- coding: utf-8 --
# @File: tasks.py
# @Time: 2025/3/3 15:34
# @Author: windyzhao
from datetime import datetime, timedelta

from celery import shared_task

from apps.cmdb.collection.collect_tasks import JobCollect
from apps.cmdb.collection.collect_tasks import ProtocolCollect
from apps.core.logger import cmdb_logger as logger
from apps.cmdb.models.collect_model import CollectModels
from apps.cmdb.constants.constants import CollectRunStatusType


@shared_task
def sync_collect_task(instance_id):
    """
    同步采集任务
    """
    logger.info("开始采集任务 task_id={}".format(instance_id))
    instance = CollectModels.objects.filter(id=instance_id).first()
    if not instance:
        return
    if instance.exec_status == CollectRunStatusType.NOT_START:
        CollectModels.objects.filter(id=instance_id).update(exec_status=CollectRunStatusType.RUNNING)
    exec_error_message = ''
    try:
        if instance.is_job:
            # 脚本采集
            collect = JobCollect(task=instance)
            result, format_data = collect.main()
        else:
            # 协议采集
            collect = ProtocolCollect(task=instance)
            result, format_data = collect.main()
        task_exec_status = CollectRunStatusType.EXAMINE if instance.input_method else CollectRunStatusType.SUCCESS
        instance.exec_status = task_exec_status

    except Exception as err:
        import traceback
        logger.error("同步数据失败 task_id={}, error={}".format(instance_id, traceback.format_exc()))
        exec_error_message = "同步数据失败, error={}".format(err)
        result = {}
        format_data = {}
        instance.exec_status = CollectRunStatusType.ERROR
        task_exec_status = CollectRunStatusType.ERROR

    try:
        instance.collect_data = result
        instance.format_data = format_data
        collect_digest = {
            "add": len(format_data.get("add", [])),
            "add_error": len([i for i in format_data.get('add',[]) if i.get('_status') != "success"]),
            "update": len(format_data.get("update", [])),
            "update_error": len([i for i in format_data.get('update', []) if i.get('_status') != "success"]),
            "delete": len(format_data.get("delete", [])),
            "delete_error": len([i for i in format_data.get('delete', []) if i.get('_status') != "success"]),
            "association": len(format_data.get("association", [])),
            "association_error": len([i for i in format_data.get('association', []) if i.get('_status') != "success"]),
            "all": format_data.get('all', 0) # 总数是发现的正常数据总数，例如：扫描了10个ip，其中6个是真的ip，4个ip不存在，总数为6
        }
        # add是需要新增的数据，add_success是实际新增成功的数据（实际到cmdb的数据），add_error是新增失败的数据，其他以此类推
        collect_digest['add_success'] = collect_digest['add'] - collect_digest['add_error']
        collect_digest['update_success'] = collect_digest['update'] - collect_digest['update_error']
        collect_digest['delete_success'] = collect_digest['delete'] - collect_digest['delete_error']
        collect_digest['association_success'] = collect_digest['association'] - collect_digest['association_error']
        # 如果任务执行失败，添加错误信息提示
        if task_exec_status == CollectRunStatusType.ERROR:
            collect_digest['message'] = exec_error_message
        elif format_data.get('__raw_data__',[]).__len__() == 0:
            collect_digest['message'] = "没有发现任何有效数据!"
            instance.exec_status = CollectRunStatusType.ERROR
        else:
            # 计算最后数据的最后上报时间
            last_time = ''
            for i in format_data['__raw_data__']:
                if i.get('__time__'):
                    if i['__time__'] > last_time:
                        last_time = i['__time__']
            collect_digest['last_time'] = last_time
        instance.collect_digest = collect_digest
        instance.save()
    except Exception as err:
        import traceback
        logger.error("保存采集结果失败 task_id={}, error={}".format(instance_id, traceback.format_exc()))
        CollectModels.objects.filter(id=instance_id).update(
            exec_status=CollectRunStatusType.ERROR,
            collect_digest={"message": "保存采集结果失败: {}".format(err)}
        )

    logger.info("采集任务执行结束 task_id={}".format(instance_id))


@shared_task
def sync_periodic_update_task_status():
    """
    执行脚本5分钟更新一次脚本结果
    :param :
    :return:
    """
    logger.info("==开始周期执行修改采集状态==")
    five_minutes_ago = datetime.now() - timedelta(minutes=5)
    rows = CollectModels.objects.filter(exec_status=CollectRunStatusType.RUNNING,
                                        exec_time__lt=five_minutes_ago).update(
        exec_status=CollectRunStatusType.ERROR)
    logger.info("开始周期执行修改采集状态完成, rows={}".format(rows))
