import hashlib

from django.apps import apps
from django.db import transaction

from apps.core.logger import mlops_logger as logger


class TrainDataFileReferenceUnavailable(ValueError):
    """Raised when a row references a training file being deleted or gone."""


def _storage_namespace(storage):
    """Return a comparable identity for independently constructed storages."""
    try:
        return storage.deconstruct()
    except (AttributeError, TypeError, ValueError):
        return None


def _file_reference_guard_key(path):
    return hashlib.sha256(path.encode()).hexdigest()


def _lock_file_reference_guards(*, paths, using):
    from apps.mlops.models.train_data_file import TrainDataFileReferenceGuard

    manager = TrainDataFileReferenceGuard.objects.using(using)
    guards = {}
    keyed_paths = {
        _file_reference_guard_key(path): path
        for path in paths
        if path
    }
    for lock_key in sorted(keyed_paths):
        manager.get_or_create(lock_key=lock_key)
        guard = manager.select_for_update().get(lock_key=lock_key)
        guards[keyed_paths[lock_key]] = guard
    return guards


def _assert_file_reference_available(*, field_file, guard, using):
    from apps.mlops.models.train_data_file import TrainDataFileReferenceStatus

    if (
        guard is None
        or guard.status == TrainDataFileReferenceStatus.ACTIVE
        or not field_file._committed
    ):
        return
    if (
        guard.status == TrainDataFileReferenceStatus.DELETED
        and field_file.storage.exists(field_file.name)
    ):
        guard.status = TrainDataFileReferenceStatus.ACTIVE
        guard.save(update_fields=["status", "updated_at"], using=using)
        return
    raise TrainDataFileReferenceUnavailable(
        f"Training data file '{field_file.name}' is being deleted or has already been deleted"
    )


def _mark_file_reference_active(*, path, using, guards):
    from apps.mlops.models.train_data_file import TrainDataFileReferenceStatus

    if not path:
        return
    guard = guards.get(path)
    if guard is None:
        guard = _lock_file_reference_guards(
            paths=[path],
            using=using,
        )[path]
        guards[path] = guard
    if guard.status != TrainDataFileReferenceStatus.ACTIVE:
        guard.status = TrainDataFileReferenceStatus.ACTIVE
        guard.save(update_fields=["status", "updated_at"], using=using)


def _find_train_data_file_reference(
    *,
    model_class,
    file_field_name,
    old_path,
    using,
):
    """Find any train-data row that still points at the same stored object."""
    from apps.mlops.models.mixins import TrainDataFileCleanupMixin

    source_storage = model_class._meta.get_field(file_field_name).storage
    source_namespace = _storage_namespace(source_storage)

    for candidate_model in apps.get_models():
        if not issubclass(candidate_model, TrainDataFileCleanupMixin):
            continue

        candidate_field_name = candidate_model._file_field_name
        candidate_storage = candidate_model._meta.get_field(candidate_field_name).storage
        candidate_namespace = _storage_namespace(candidate_storage)
        shares_storage_namespace = (
            source_namespace == candidate_namespace
            if source_namespace is not None and candidate_namespace is not None
            else True
        )
        if not shares_storage_namespace:
            continue

        referencing_pk = (
            candidate_model.objects.using(using)
            .filter(**{candidate_field_name: old_path})
            .values_list("pk", flat=True)
            .first()
        )
        if referencing_pk is not None:
            return candidate_model, referencing_pk

    return None


def delete_unreferenced_train_data_file(
    *,
    model_label,
    instance_pk,
    file_field_name,
    old_path,
    using="default",
):
    """Delete an old training file only when the database no longer references it."""
    from apps.mlops.models.train_data_file import TrainDataFileReferenceStatus

    model_class = apps.get_model(model_label)
    storage = model_class._meta.get_field(file_field_name).storage

    # Persist the fence before touching object storage. If the later delete or
    # tombstone write fails, committed string references remain blocked while
    # the idempotent cleanup task retries.
    with transaction.atomic(using=using):
        guard = _lock_file_reference_guards(
            paths=[old_path],
            using=using,
        )[old_path]
        reference = _find_train_data_file_reference(
            model_class=model_class,
            file_field_name=file_field_name,
            old_path=old_path,
            using=using,
        )
        if reference is not None:
            referencing_model, referencing_pk = reference
            logger.info(
                "Skipped deleting referenced %s file for %s %s: %s (referenced by %s %s)",
                file_field_name,
                model_class.__name__,
                instance_pk,
                old_path,
                referencing_model.__name__,
                referencing_pk,
            )
            return "referenced"

        if guard.status == TrainDataFileReferenceStatus.DELETED:
            logger.info(
                "Skipped repeated deletion of %s file for %s %s: %s",
                file_field_name,
                model_class.__name__,
                instance_pk,
                old_path,
            )
            return "deleted"

        if guard.status != TrainDataFileReferenceStatus.DELETING:
            guard.status = TrainDataFileReferenceStatus.DELETING
            guard.save(update_fields=["status", "updated_at"], using=using)

    # Re-lock and recheck because an uploaded replacement may have recreated
    # the path between the durable fence and this physical delete phase.
    with transaction.atomic(using=using):
        guard = _lock_file_reference_guards(
            paths=[old_path],
            using=using,
        )[old_path]
        reference = _find_train_data_file_reference(
            model_class=model_class,
            file_field_name=file_field_name,
            old_path=old_path,
            using=using,
        )
        if reference is not None:
            referencing_model, referencing_pk = reference
            logger.info(
                "Skipped deleting referenced %s file for %s %s: %s (referenced by %s %s)",
                file_field_name,
                model_class.__name__,
                instance_pk,
                old_path,
                referencing_model.__name__,
                referencing_pk,
            )
            return "referenced"

        if guard.status == TrainDataFileReferenceStatus.DELETED:
            logger.info(
                "Skipped repeated deletion of %s file for %s %s: %s",
                file_field_name,
                model_class.__name__,
                instance_pk,
                old_path,
            )
            return "deleted"

        storage.delete(old_path)
        guard.status = TrainDataFileReferenceStatus.DELETED
        guard.save(update_fields=["status", "updated_at"], using=using)
        logger.info(
            "Deleted old %s file for %s %s: %s",
            file_field_name,
            model_class.__name__,
            instance_pk,
            old_path,
        )
        return "deleted"


def delete_train_data_file_with_retry(**cleanup_kwargs):
    """Run cleanup now and publish the idempotent task after a transient failure."""
    old_path = cleanup_kwargs["old_path"]
    try:
        return delete_unreferenced_train_data_file(**cleanup_kwargs)
    except Exception as delete_err:
        logger.warning(
            "Failed to delete old file '%s'; scheduling retry: %s",
            old_path,
            delete_err,
        )
        try:
            from apps.mlops.tasks.file_cleanup import cleanup_train_data_file

            cleanup_train_data_file.apply_async(
                kwargs=cleanup_kwargs,
                delivery_mode=2,
                retry=True,
                retry_policy={
                    "max_retries": 3,
                    "interval_start": 0,
                    "interval_step": 1,
                    "interval_max": 3,
                },
            )
        except Exception as publish_err:
            logger.error(
                "Failed to publish cleanup retry for '%s': %s",
                old_path,
                publish_err,
            )
            return "retry_publish_failed"
        return "retry_scheduled"
