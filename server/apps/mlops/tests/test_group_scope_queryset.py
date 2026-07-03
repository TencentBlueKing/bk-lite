import pydantic.root_model  # noqa

from types import SimpleNamespace

import pytest
from rest_framework.test import APIRequestFactory

from apps.mlops.models.classification import (
    ClassificationDataset,
    ClassificationTrainData,
)
from apps.mlops.utils import group_scope as gs

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


def _req(team=None, superuser=False):
    request = APIRequestFactory().get("/")
    if team is not None:
        request._api_current_team = team
    request.user = SimpleNamespace(is_superuser=superuser)
    return request


def test_filter_queryset_by_parent_team_superuser_returns_all():
    ds1 = ClassificationDataset.objects.create(name="ds1", description="", team=[1])
    ds2 = ClassificationDataset.objects.create(name="ds2", description="", team=[2])
    ClassificationTrainData.objects.create(name="a", dataset=ds1, is_train_data=True)
    ClassificationTrainData.objects.create(name="b", dataset=ds2, is_train_data=True)

    qs = ClassificationTrainData.objects.all()
    filtered = gs.filter_queryset_by_parent_team(qs, _req(superuser=True), "dataset__team")
    assert filtered.count() == 2


def test_filter_queryset_by_parent_team_scopes_to_current_team():
    ds1 = ClassificationDataset.objects.create(name="ds-a", description="", team=[1])
    ds2 = ClassificationDataset.objects.create(name="ds-b", description="", team=[2])
    keep = ClassificationTrainData.objects.create(name="keep", dataset=ds1, is_train_data=True)
    ClassificationTrainData.objects.create(name="drop", dataset=ds2, is_train_data=True)

    qs = ClassificationTrainData.objects.all()
    filtered = gs.filter_queryset_by_parent_team(qs, _req(team="1"), "dataset__team")
    ids = list(filtered.values_list("id", flat=True))
    assert ids == [keep.id]


def test_filter_queryset_by_parent_team_root_team_lookup():
    ClassificationDataset.objects.create(name="root1", description="", team=[1])
    ClassificationDataset.objects.create(name="root2", description="", team=[2])
    qs = ClassificationDataset.objects.all()
    filtered = gs.filter_queryset_by_parent_team(qs, _req(team="2"), "team")
    names = list(filtered.values_list("name", flat=True))
    assert names == ["root2"]
