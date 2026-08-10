from celery import shared_task

from apps.log.services.log_extractor.publication import publish_generation


@shared_task(
    acks_late=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
    max_retries=3,
)
def publish_system_vector_config(generation: int):
    return publish_generation(generation)
