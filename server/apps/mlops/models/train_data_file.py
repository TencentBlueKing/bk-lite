from django.db import models


class TrainDataFileReferenceStatus(models.TextChoices):
    ACTIVE = "active", "Active"
    DELETING = "deleting", "Deleting"
    DELETED = "deleted", "Deleted"


class TrainDataFileReferenceGuard(models.Model):
    """Serializes reference writes and cleanup for one stored training file."""

    lock_key = models.CharField(max_length=64, primary_key=True)
    status = models.CharField(
        max_length=16,
        choices=TrainDataFileReferenceStatus.choices,
        default=TrainDataFileReferenceStatus.ACTIVE,
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "mlops_train_data_file_reference_guard"
