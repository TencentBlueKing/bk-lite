"""Utilities for managing Celery beat tasks for scheduled workflows."""

import json

from django.utils import timezone
from django_celery_beat.models import CrontabSchedule, PeriodicTask

from apps.core.logger import opspilot_logger as logger
from apps.opspilot.utils.schedule_utils import CrontabGenerator, ScheduleConfigValidator, convert_legacy_config


def create_celery_task(bot_id, work_data):
    """
    Create Celery beat tasks for scheduled workflow nodes.

    Supports flexible scheduling with daily (multi-time), weekly, monthly,
    and custom crontab expressions.

    Config format (in node.data.config):
        {
            "frequency": "daily"|"weekly"|"monthly"|"crontab",
            "time": ["09:00", "18:00"],        # For daily/weekly/monthly
            "weekdays": [1, 3, 5],             # For weekly (0=Sunday)
            "days": [1, 15],                   # For monthly
            "crontab_expression": "30 9 * * 1-5",  # For crontab
            "message": "触发消息",
            ...
        }

    Args:
        bot_id: The bot ID
        work_data: Workflow data containing nodes configuration
    """
    # Delete existing tasks for this bot first
    delete_celery_task(bot_id)

    # Phase 1: Collect all task data and crontab configs
    task_data_list = []  # [(task_name, crontab_dict, task_kwargs), ...]

    celery_nodes = [i for i in work_data["nodes"] if i.get("type") == "celery"]
    for node in celery_nodes:
        node_id = node["id"]
        raw_config = node["data"]["config"]

        # Convert legacy format if needed (time string -> time list)
        config = convert_legacy_config(raw_config)

        # Check if frequency exists
        if not config.get("frequency"):
            logger.warning(f"Node {node_id} has no frequency, skipping. bot_id={bot_id}")
            continue

        message = config.get("message", "")

        # Validate configuration
        try:
            ScheduleConfigValidator.validate(config)
        except ValueError as e:
            logger.error("Invalid schedule config for node %s: %r. bot_id=%s", node_id, e, bot_id)
            continue

        # Generate crontab entries
        try:
            crontab_entries = CrontabGenerator.generate(config)
        except ValueError as e:
            logger.error("Failed to generate crontab for node %s: %r. bot_id=%s", node_id, e, bot_id)
            continue

        # Collect task data
        for task_suffix, crontab_dict in crontab_entries:
            task_name = f"chat_flow_celery_task_{bot_id}_{node_id}_{task_suffix}"
            task_kwargs = {"bot_id": bot_id, "node_id": node_id, "message": message}
            task_data_list.append((task_name, crontab_dict, task_kwargs))

    if not task_data_list:
        return

    # Phase 2: Batch get or create CrontabSchedules
    crontab_cache = _get_or_create_crontab_schedules(task_data_list)

    # Phase 3: Batch create PeriodicTasks
    _bulk_create_periodic_tasks(task_data_list, crontab_cache)

    logger.info(f"Created {len(task_data_list)} periodic tasks for bot {bot_id}")


def _get_or_create_crontab_schedules(task_data_list):
    """
    Batch get or create CrontabSchedule objects.

    Uses bulk query + bulk create to minimize DB operations:
    - 1 query to find existing schedules
    - 1 bulk_create for missing schedules (if any)

    Args:
        task_data_list: List of (task_name, crontab_dict, task_kwargs)

    Returns:
        dict: Mapping from crontab_key to CrontabSchedule instance
    """
    from django.db.models import Q

    current_tz = timezone.get_current_timezone()

    # Step 1: Collect unique crontab configs
    unique_crontabs = {}  # crontab_key -> crontab_dict
    for _, crontab_dict, _ in task_data_list:
        key = _crontab_dict_to_key(crontab_dict)
        if key not in unique_crontabs:
            unique_crontabs[key] = crontab_dict

    if not unique_crontabs:
        return {}

    # Step 2: Build Q filter for batch query of existing schedules
    q_filter = Q()
    for crontab_dict in unique_crontabs.values():
        q_filter |= Q(
            minute=crontab_dict["minute"],
            hour=crontab_dict["hour"],
            day_of_week=crontab_dict["day_of_week"],
            day_of_month=crontab_dict["day_of_month"],
            month_of_year=crontab_dict["month_of_year"],
            timezone=current_tz,
        )

    # Step 3: Single query to get all existing schedules
    existing_schedules = CrontabSchedule.objects.filter(q_filter)

    # Build cache from existing schedules
    crontab_cache = {}
    for schedule in existing_schedules:
        key = (
            schedule.minute,
            schedule.hour,
            schedule.day_of_week,
            schedule.day_of_month,
            schedule.month_of_year,
        )
        crontab_cache[key] = schedule

    # Step 4: Find missing schedules and bulk create
    missing_schedules = []
    for key, crontab_dict in unique_crontabs.items():
        if key not in crontab_cache:
            missing_schedules.append(
                CrontabSchedule(
                    minute=crontab_dict["minute"],
                    hour=crontab_dict["hour"],
                    day_of_week=crontab_dict["day_of_week"],
                    day_of_month=crontab_dict["day_of_month"],
                    month_of_year=crontab_dict["month_of_year"],
                    timezone=current_tz,
                )
            )

    if missing_schedules:
        # bulk_create returns the created objects with IDs
        created_schedules = CrontabSchedule.objects.bulk_create(missing_schedules)
        for schedule in created_schedules:
            key = (
                schedule.minute,
                schedule.hour,
                schedule.day_of_week,
                schedule.day_of_month,
                schedule.month_of_year,
            )
            crontab_cache[key] = schedule

    return crontab_cache


def _crontab_dict_to_key(crontab_dict):
    """Convert crontab dict to a hashable key."""
    return (
        crontab_dict["minute"],
        crontab_dict["hour"],
        crontab_dict["day_of_week"],
        crontab_dict["day_of_month"],
        crontab_dict["month_of_year"],
    )


def _bulk_create_periodic_tasks(task_data_list, crontab_cache):
    """
    Bulk create PeriodicTask objects.

    Args:
        task_data_list: List of (task_name, crontab_dict, task_kwargs)
        crontab_cache: Mapping from crontab_key to CrontabSchedule instance
    """
    tasks_to_create = []
    for task_name, crontab_dict, task_kwargs in task_data_list:
        crontab_key = _crontab_dict_to_key(crontab_dict)
        crontab_schedule = crontab_cache[crontab_key]

        task = PeriodicTask(
            name=task_name,
            task="apps.opspilot.tasks.chat_flow_celery_task",
            enabled=True,
            crontab=crontab_schedule,
            kwargs=json.dumps(task_kwargs),
            args="[]",
        )
        tasks_to_create.append(task)

    if tasks_to_create:
        PeriodicTask.objects.bulk_create(tasks_to_create)


def delete_celery_task(bot_id):
    """
    Delete all Celery beat tasks for a bot.

    Args:
        bot_id: The bot ID
    """
    task_name_prefix = f"chat_flow_celery_task_{bot_id}_"
    deleted_count, _ = PeriodicTask.objects.filter(name__startswith=task_name_prefix).delete()

    if deleted_count > 0:
        logger.info(f"Deleted {deleted_count} periodic tasks for bot {bot_id}")
