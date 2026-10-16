from django.urls import path
from rest_framework import routers

from apps.rum.views import (
    RumAlertAssignView,
    RumAlertClaimView,
    RumAlertCloseView,
    RumAlertDeliveryRetryView,
    RumAlertEventViewSet,
    RumAlertReassignView,
    RumAnalyticsApplicationsView,
    RumApplicationViewSet,
    RumComplianceViewSet,
    RumErrorViewSet,
    RumFunnelViewSet,
    RumHealthView,
    RumMetaView,
    RumMonitorViewSet,
    RumNotificationChannelView,
    RumNotificationRecipientView,
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
urlpatterns_notifications = [
    path("notification-channels/", RumNotificationChannelView.as_view(), name="rum-notification-channels"),
    path("notification-recipients/", RumNotificationRecipientView.as_view(), name="rum-notification-recipients"),
]
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
    *urlpatterns_notifications,
    path("alert-events/<str:pk>/claim/", RumAlertClaimView.as_view(), name="rum-alert-claim"),
    path("alert-events/<str:pk>/assign/", RumAlertAssignView.as_view(), name="rum-alert-assign"),
    path("alert-events/<str:pk>/reassign/", RumAlertReassignView.as_view(), name="rum-alert-reassign"),
    path("alert-events/<str:pk>/close/", RumAlertCloseView.as_view(), name="rum-alert-close"),
    path(
        "alert-events/<str:pk>/deliveries/<str:delivery_id>/retry/",
        RumAlertDeliveryRetryView.as_view(),
        name="rum-alert-delivery-retry",
    ),
    *router.urls,
]
