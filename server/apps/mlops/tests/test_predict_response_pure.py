import pytest
from rest_framework import status

from apps.mlops.predict_response import map_predict_upstream_status

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "upstream_status",
    [
        status.HTTP_400_BAD_REQUEST,
        status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
        status.HTTP_422_UNPROCESSABLE_ENTITY,
    ],
)
def test_map_predict_upstream_status_preserves_registered_input_errors(upstream_status):
    assert map_predict_upstream_status(upstream_status) == upstream_status


@pytest.mark.parametrize(
    "upstream_status",
    [
        status.HTTP_401_UNAUTHORIZED,
        status.HTTP_404_NOT_FOUND,
        status.HTTP_429_TOO_MANY_REQUESTS,
        status.HTTP_500_INTERNAL_SERVER_ERROR,
        status.HTTP_503_SERVICE_UNAVAILABLE,
    ],
)
def test_map_predict_upstream_status_keeps_unregistered_failures_internal(upstream_status):
    assert map_predict_upstream_status(upstream_status) == status.HTTP_500_INTERNAL_SERVER_ERROR
