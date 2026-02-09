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


class TrainJobConfigSyncMixin:
    """
    Mixin for TrainJob models that automatically syncs hyperopt_config to MinIO
    when the model is saved.

    Usage:
        class MyTrainJob(TrainJobConfigSyncMixin, MaintainerInfo, TimeInfo):
            _model_prefix = "MyModel"  # e.g., "AnomalyDetection", "Classification"

            algorithm = models.CharField(...)
            hyperopt_config = models.JSONField(...)
            config_url = models.FileField(...)
            max_evals = models.IntegerField(...)

            # TrainJobConfigSyncMixin must come BEFORE other base classes
            # to ensure its save() is called first in the MRO.

    Required model fields:
        - algorithm: CharField
        - hyperopt_config: JSONField
        - config_url: FileField (MinIO storage)
        - max_evals: IntegerField
    """

    # Subclasses MUST override this to set the model identifier prefix
    _model_prefix: str = ""

    # Fields that trigger config sync when updated
    _config_related_fields = {
        "hyperopt_config",
        "config_url",
        "algorithm",
        "dataset_version",
    }

    def save(self, *args, **kwargs):
        """
        Save with automatic config sync to MinIO.

        This method:
        1. Checks if config-related fields are being updated
        2. Saves to database first to get pk
        3. Syncs config to MinIO if needed
        4. Updates config_url in database without triggering recursive save
        """
        from apps.core.logger import mlops_logger as logger

        # If only updating non-config fields, skip file sync
        update_fields = kwargs.get("update_fields")

        if update_fields and not any(
            field in self._config_related_fields for field in update_fields
        ):
            super().save(*args, **kwargs)
            return

        # 1. Save to database first to get pk
        super().save(*args, **kwargs)

        # 2. Sync file to MinIO based on pk
        config_updated = False

        if self.hyperopt_config:
            # Has config → complete and upload to MinIO
            self._sync_config_to_minio()
            config_updated = True
        elif self.config_url:
            # Config is empty → delete MinIO file
            try:
                self.config_url.delete(save=False)
                logger.info(
                    f"Deleted config file (empty config) for TrainJob {self.pk}"
                )
                self.config_url = None
                config_updated = True
            except Exception as e:
                logger.warning(f"Failed to delete config file: {e}")

        # 3. If config_url changed, update database (use queryset.update to avoid recursive save)
        if config_updated:
            self.__class__.objects.filter(pk=self.pk).update(config_url=self.config_url)

    def _sync_config_to_minio(self):
        """Sync hyperopt_config to MinIO (auto-complete model and mlflow config)."""
        from django.core.files.base import ContentFile
        import json
        import uuid
        from apps.core.logger import mlops_logger as logger

        # Delete old file
        if self.config_url:
            try:
                self.config_url.delete(save=False)
                logger.info(f"Deleted old config file for TrainJob {self.pk}")
            except Exception as e:
                logger.warning(f"Failed to delete old config file: {e}")

        # Complete and upload config
        try:
            complete_config = self._build_complete_config()

            # Upload new file
            content = json.dumps(complete_config, ensure_ascii=False, indent=2)
            filename = f"config_{self.pk or 'new'}_{uuid.uuid4().hex[:8]}.json"
            self.config_url.save(
                filename,
                ContentFile(content.encode("utf-8")),
                save=False,  # Important: avoid recursive save()
            )
            logger.info(f"Synced config to MinIO for TrainJob {self.pk}: {filename}")
        except Exception as e:
            logger.error(f"Failed to sync config to MinIO: {e}", exc_info=True)

    def _build_complete_config(self):
        """Build complete config file (add model, mlflow, and max_evals sections)."""
        # Base config (from frontend)
        config = dict(self.hyperopt_config) if self.hyperopt_config else {}

        # Generate model identifier: {prefix}_{algorithm}_{id} (pk exists at this point)
        model_identifier = f"{self._model_prefix}_{self.algorithm}_{self.pk}"

        # Ensure hyperparams exists
        if "hyperparams" not in config:
            config["hyperparams"] = {}

        # Force sync max_evals (use dedicated field as source of truth)
        config["hyperparams"]["max_evals"] = self.max_evals

        # Add model config
        config["model"] = {"type": self.algorithm, "name": model_identifier}

        # Add mlflow config
        config["mlflow"] = {"experiment_name": model_identifier}

        return config
