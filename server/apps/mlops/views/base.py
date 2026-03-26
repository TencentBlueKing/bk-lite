from apps.core.utils.viewset_utils import AuthViewSet


class TeamModelViewSet(AuthViewSet):
    """``AuthViewSet`` with ``team`` ownership for root MLOps resources.

    Subclasses must define ``queryset`` on a model that exposes a
    ``team`` JSONField directly.
    """

    ORGANIZATION_FIELD = "team"
