from django.urls import path
from rest_framework import routers

from apps.rum.views import (
    RumAlertEventViewSet,
    RumAnalyticsApplicationsView,
    RumApplicationViewSet,
    RumComplianceViewSet,
    RumErrorViewSet,
    RumFunnelViewSet,
    RumHealthView,
    RumMetaView,
    RumMonitorViewSet,
    RumReleaseViewSet,
    RumReplayGrantView,
    RumReplayManifestView,
    RumReplaySegmentView,
    RumSavedViewViewSet,
    RumSessionViewSet,
    RumSnippetsView,
    RumSourcemapCredentialRotateView,
    RumSourcemapIngestView,
    RumSourcemapRestoreView,
    RumSourcemapView,
    RumViewViewSet,
)

router = routers.DefaultRouter()
router.register(r"applications", RumApplicationViewSet, basename="rum-application")
router.register(r"sessions", RumSessionViewSet, basename="rum-session")
router.register(r"errors", RumErrorViewSet, basename="rum-error")
router.register(r"views", RumViewViewSet, basename="rum-view")
router.register(r"saved-views", RumSavedViewViewSet, basename="rum-saved-view")
router.register(r"funnels", RumFunnelViewSet, basename="rum-funnel")
router.register(r"releases", RumReleaseViewSet, basename="rum-release")
router.register(r"monitors", RumMonitorViewSet, basename="rum-monitor")
router.register(r"alert-events", RumAlertEventViewSet, basename="rum-alert-event")
router.register(r"compliance/erase", RumComplianceViewSet, basename="rum-compliance-erase")

urlpatterns = [
    path("meta/", RumMetaView.as_view(), name="rum-meta"),
    path("health/", RumHealthView.as_view(), name="rum-health"),
    path("snippets/", RumSnippetsView.as_view(), name="rum-snippets"),
    path(
        "analytics/applications/",
        RumAnalyticsApplicationsView.as_view(),
        name="rum-analytics-applications",
    ),
    path("replay/manifest/", RumReplayManifestView.as_view(), name="rum-replay-manifest"),
    path("replay/grants/", RumReplayGrantView.as_view(), name="rum-replay-grants"),
    path(
        "replay/segments/<str:token>/",
        RumReplaySegmentView.as_view(),
        name="rum-replay-segments",
    ),
    path("sourcemaps/", RumSourcemapView.as_view(), name="rum-sourcemaps"),
    path("sourcemaps/restore/", RumSourcemapRestoreView.as_view(), name="rum-sourcemap-restore"),
    path("sourcemaps/ingest/", RumSourcemapIngestView.as_view(), name="rum-sourcemap-ingest"),
    path(
        "sourcemaps/credentials/<str:application>/rotate/",
        RumSourcemapCredentialRotateView.as_view(),
        name="rum-sourcemap-credential-rotate",
    ),
    *router.urls,
]
