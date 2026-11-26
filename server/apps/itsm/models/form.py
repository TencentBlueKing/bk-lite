from django.db import models

from apps.itsm.models.base import ItsmModel


class FormModel(ItsmModel):
    name = models.CharField(max_length=128)
    key = models.CharField(max_length=64)
    description = models.CharField(max_length=500, blank=True, default="")
    current_version = models.ForeignKey(
        "itsm.FormVersion",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )

    class Meta:
        db_table = "itsm_form_model"
        unique_together = (("domain", "key"),)


class FormVersion(ItsmModel):
    form = models.ForeignKey(FormModel, on_delete=models.CASCADE, related_name="versions")
    version_no = models.PositiveIntegerField()
    schema = models.JSONField(default=dict)
    is_published = models.BooleanField(default=False)

    class Meta:
        db_table = "itsm_form_version"
        unique_together = (("form", "version_no"),)


class FormViewTemplate(ItsmModel):
    form = models.ForeignKey(FormModel, on_delete=models.CASCADE, related_name="view_templates")
    name = models.CharField(max_length=128)
    layout = models.JSONField(default=dict)
    match_rules = models.JSONField(default=dict)
    is_enabled = models.BooleanField(default=True)

    class Meta:
        db_table = "itsm_form_view_template"


class DataTable(ItsmModel):
    name = models.CharField(max_length=128)
    key = models.CharField(max_length=64)

    class Meta:
        db_table = "itsm_data_table"
        unique_together = (("domain", "key"),)


class DataTableField(ItsmModel):
    label = models.CharField(max_length=128, blank=True, default="")
    table = models.ForeignKey(DataTable, on_delete=models.CASCADE, related_name="fields")
    key = models.CharField(max_length=64)
    field_type = models.CharField(max_length=32, default="string")

    class Meta:
        db_table = "itsm_data_table_field"
        unique_together = (("table", "key"),)


class DataTableRow(ItsmModel):
    table = models.ForeignKey(DataTable, on_delete=models.CASCADE, related_name="rows")
    data = models.JSONField(default=dict)

    class Meta:
        db_table = "itsm_data_table_row"


class DataDictionary(ItsmModel):
    key = models.CharField(max_length=64)
    name = models.CharField(max_length=128)

    class Meta:
        db_table = "itsm_data_dictionary"
        unique_together = (("domain", "key"),)


class DataDictionaryItem(ItsmModel):
    dictionary = models.ForeignKey(DataDictionary, on_delete=models.CASCADE, related_name="items")
    key = models.CharField(max_length=64)
    label = models.CharField(max_length=128)
    parent = models.ForeignKey("self", null=True, blank=True, on_delete=models.CASCADE, related_name="children")
    order = models.PositiveIntegerField(default=0)
    is_enabled = models.BooleanField(default=True)

    class Meta:
        db_table = "itsm_data_dictionary_item"
        unique_together = (("dictionary", "key"),)
