"""
MLOps Model Mixins

Shared mixin classes for mlops models to reduce code duplication.
"""


class TrainDataFileCleanupMixin:
    """
    Mixin for TrainData models that automatically cleans up old training data files
    when the train_data field is updated.

    Usage:
        class MyTrainData(TrainDataFileCleanupMixin, MaintainerInfo, TimeInfo):
            train_data = models.FileField(...)

            # TrainDataFileCleanupMixin must come BEFORE other base classes
            # to ensure its save() is called first in the MRO.
    """

    # Subclasses can override this to use a different file field name
    _file_field_name = "train_data"

    def save(self, *args, **kwargs):
        """
        Automatically clean up old training data file when it's being replaced.

        This method:
        1. Detects if we're updating an existing record (pk exists)
        2. Compares old and new file paths
        3. Deletes the old file from storage if path changed
        4. Calls the parent save() method
        """
        from django.db import transaction
        from apps.core.logger import mlops_logger as logger

        file_field_name = self._file_field_name

        # Only perform cleanup on updates (not on new records)
        if self.pk:
            with transaction.atomic():
                try:
                    # Use select_for_update to prevent race conditions
                    old_instance = self.__class__.objects.select_for_update().get(pk=self.pk)
                    old_file = getattr(old_instance, file_field_name)
                    new_file = getattr(self, file_field_name)

                    # Extract file paths (handle FieldFile objects and None)
                    old_path = old_file.name if old_file else None
                    new_path = new_file.name if new_file else None

                    # Delete old file if it exists and path has changed (including when cleared)
                    if old_path and old_path != new_path:
                        try:
                            old_file.delete(save=False)
                            logger.info(
                                f"Deleted old {file_field_name} file for {self.__class__.__name__} {self.pk}: "
                                f"old={old_path}, new={new_path or 'None'}"
                            )
                        except Exception as delete_err:
                            logger.warning(
                                f"Failed to delete old file '{old_path}': {delete_err}"
                            )

                except self.__class__.DoesNotExist:
                    pass
                except Exception as e:
                    logger.warning(f"Failed to check old {file_field_name} file: {e}")

        super().save(*args, **kwargs)
