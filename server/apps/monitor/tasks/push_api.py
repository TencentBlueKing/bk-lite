from celery import shared_task

from apps.core.logger import celery_logger as logger
from apps.monitor.services.push_api import PushAPIService


@shared_task
def publish_push_api_metrics(payload: dict, token_team: int):
    request_id = PushAPIService.build_request_id(payload)
    template_id = payload.get("template_id")
    instance_count = len(payload.get("instances") or [])
    logger.info(
        "Start push-api async processing",
        extra={
            "request_id": request_id,
            "template_id": template_id,
            "token_team": token_team,
            "instance_count": instance_count,
        },
    )

    try:
        result = PushAPIService.process_report_async(payload, token_team)
        lines = result["accepted_lines"]
        if not lines:
            logger.info(
                "No push-api metrics accepted",
                extra={
                    "request_id": request_id,
                    "template_id": template_id,
                    "token_team": token_team,
                    "instance_count": instance_count,
                    "accepted_count": result["accepted_count"],
                    "accepted_metric_count": result["accepted_metric_count"],
                    "filtered_count": result["filtered_count"],
                },
            )
            return {
                "success": True,
                "count": 0,
                "filtered_count": result["filtered_count"],
                "request_id": request_id,
            }

        subject = PushAPIService.build_publish_subject(result["template_id"])
        PushAPIService.publish_lines_sync(subject, lines)
        logger.info(
            "Published push-api metrics",
            extra={
                "request_id": request_id,
                "template_id": result["template_id"],
                "token_team": token_team,
                "instance_count": instance_count,
                "accepted_count": result["accepted_count"],
                "accepted_metric_count": result["accepted_metric_count"],
                "filtered_count": result["filtered_count"],
                "subject": subject,
            },
        )
        return {
            "success": True,
            "count": len(lines),
            "subject": subject,
            "accepted_count": result["accepted_count"],
            "accepted_metric_count": result["accepted_metric_count"],
            "filtered_count": result["filtered_count"],
            "request_id": request_id,
        }
    except Exception:
        logger.exception(
            "Push-api async processing failed",
            extra={
                "request_id": request_id,
                "template_id": template_id,
                "token_team": token_team,
                "instance_count": instance_count,
            },
        )
        raise
