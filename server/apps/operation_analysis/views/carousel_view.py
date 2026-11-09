from django.db.models import Count
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.decorators.api_permission import HasPermission
from apps.core.utils.viewset_utils import AuthViewSet
from apps.operation_analysis.common.audit_log import get_response_name, log_ops_analysis_success
from apps.operation_analysis.models.carousel import CanvasCarousel
from apps.operation_analysis.serializers.carousel_serializers import (
    CanvasCarouselAppendSerializer,
    CanvasCarouselListSerializer,
    CanvasCarouselWriteSerializer,
)
from apps.operation_analysis.services.carousel import append_carousel_item, create_carousel, describe_carousel, playable_item_stats, update_carousel
from apps.operation_analysis.views.view import BuiltinVisibleMixin
from config.drf.pagination import CustomPageNumberPagination


class CanvasCarouselViewSet(BuiltinVisibleMixin, AuthViewSet):
    """轮播列表。可见性按所属组织与当前组织的交集过滤。"""

    queryset = CanvasCarousel.objects.all()
    serializer_class = CanvasCarouselListSerializer
    ordering_fields = ["id"]
    ordering = ["-id"]
    pagination_class = CustomPageNumberPagination
    ORGANIZATION_FIELD = "groups"
    ORDERING_FIELD = "-id"

    def get_queryset(self):
        queryset = CanvasCarousel.objects.all()
        name = (self.request.query_params.get("name") or "").strip()
        if name:
            queryset = queryset.filter(name__icontains=name[:128])
        if self.action == "list":
            queryset = queryset.annotate(item_count=Count("items")).prefetch_related("items")
        else:
            queryset = queryset.prefetch_related("items")
        _current_team, _include_children, _org_field, org_query = self.filter_by_group(
            queryset,
            self.request,
            self.request.user,
        )
        return queryset.filter(org_query)

    def _detail_payload(self, carousel):
        carousel = CanvasCarousel.objects.prefetch_related("items").get(pk=carousel.pk)
        return describe_carousel(carousel, self.request)

    @HasPermission("view-View")
    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        carousels = page if page is not None else list(queryset)
        context = self.get_serializer_context()
        context["playback_stats"] = playable_item_stats(request, carousels)
        serializer = self.get_serializer(carousels, many=True, context=context)
        if page is not None:
            return self.get_paginated_response(serializer.data)
        return Response(serializer.data)

    @HasPermission("view-View")
    def retrieve(self, request, *args, **kwargs):
        carousel = self.get_object()
        return Response(self._detail_payload(carousel))

    @HasPermission("view-AddChart")
    def create(self, request, *args, **kwargs):
        serializer = CanvasCarouselWriteSerializer(data=request.data, context=self.get_serializer_context())
        serializer.is_valid(raise_exception=True)
        groups = serializer.validated_data.get("groups") or []
        self._validate_org_field_permission(request, groups)
        carousel = create_carousel(request, serializer.validated_data)
        response = Response(self._detail_payload(carousel), status=201)
        log_ops_analysis_success(
            request,
            response,
            "create",
            f"新增轮播列表: {get_response_name(response, carousel.name)}",
        )
        return response

    @HasPermission("view-EditChart")
    def update(self, request, *args, **kwargs):
        return self._save_update(request, partial=False)

    @HasPermission("view-EditChart")
    def partial_update(self, request, *args, **kwargs):
        return self._save_update(request, partial=True)

    def _save_update(self, request, *, partial: bool):
        carousel = self.get_object()
        serializer = CanvasCarouselWriteSerializer(
            instance=carousel,
            data=request.data,
            partial=partial,
            context=self.get_serializer_context(),
        )
        serializer.is_valid(raise_exception=True)
        if "groups" in serializer.validated_data:
            self._validate_org_field_permission(request, serializer.validated_data["groups"])
        updated = update_carousel(request, carousel, serializer.validated_data)
        response = Response(self._detail_payload(updated))
        log_ops_analysis_success(
            request,
            response,
            "update",
            f"编辑轮播列表: {get_response_name(response, updated.name)}",
        )
        return response

    @HasPermission("view-DeleteChart")
    def destroy(self, request, *args, **kwargs):
        carousel = self.get_object()
        name = carousel.name
        response = super().destroy(request, *args, **kwargs)
        log_ops_analysis_success(request, response, "delete", f"删除轮播列表: {name}")
        return response

    @HasPermission("view-EditChart")
    @action(detail=True, methods=["post"])
    def append(self, request, *args, **kwargs):
        carousel = self.get_object()
        serializer = CanvasCarouselAppendSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        append_carousel_item(request, carousel, serializer.validated_data)
        response = Response(self._detail_payload(carousel))
        log_ops_analysis_success(request, response, "update", f"编辑轮播列表: {carousel.name}")
        return response
