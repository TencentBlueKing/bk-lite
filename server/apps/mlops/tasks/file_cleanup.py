from celery import shared_task

from apps.mlops.services.train_data_file_cleanup import (
    delete_unreferenced_train_data_file,
)


@shared_task(
    acks_late=True,
    reject_on_worker_lost=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
    max_retries=5,
)
def cleanup_train_data_file(
    *,
    model_label,
    instance_pk,
    file_field_name,
    old_path,
    using="default",
):
    """Retry an idempotent old-file cleanup after a transient storage failure."""
    return delete_unreferenced_train_data_file(
        model_label=model_label,
        instance_pk=instance_pk,
        file_field_name=file_field_name,
        old_path=old_path,
        using=using,
    )
