from django.apps import apps

from apps.core.logger import mlops_logger as logger


def delete_unreferenced_train_data_file(
    *,
    model_label,
    instance_pk,
    file_field_name,
    old_path,
    using="default",
):
    """Delete an old training file only when the database no longer references it."""
    model_class = apps.get_model(model_label)
    current_path = (
        model_class.objects.using(using)
        .filter(pk=instance_pk)
        .values_list(file_field_name, flat=True)
        .first()
    )
    if current_path == old_path:
        logger.info(
            "Skipped deleting referenced %s file for %s %s: %s",
            file_field_name,
            model_class.__name__,
            instance_pk,
            old_path,
        )
        return "referenced"

    storage = model_class._meta.get_field(file_field_name).storage
    storage.delete(old_path)
    logger.info(
        "Deleted old %s file for %s %s: %s",
        file_field_name,
        model_class.__name__,
        instance_pk,
        old_path,
    )
    return "deleted"
