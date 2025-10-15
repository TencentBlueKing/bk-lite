from rest_framework import mixins
from rest_framework.decorators import action
from rest_framework.viewsets import GenericViewSet

from apps.core.utils.web_utils import WebUtils
from apps.node_mgmt.filters.package import PackageVersionFilter
from apps.node_mgmt.models.package import PackageVersion
from apps.node_mgmt.serializers.package import PackageVersionSerializer
from apps.node_mgmt.services.package import PackageService
from config.drf.pagination import CustomPageNumberPagination


class PackageMgmtView(
    mixins.CreateModelMixin,
    mixins.DestroyModelMixin,
    mixins.ListModelMixin,
    GenericViewSet):
    queryset = PackageVersion.objects.all()
    serializer_class = PackageVersionSerializer
    filterset_class = PackageVersionFilter
    pagination_class = CustomPageNumberPagination

    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        # 删除文件，成功了再删除数据
        obj = self.get_object()
        PackageService.delete_file(obj)
        return super().destroy(request, *args, **kwargs)

    def create(self, request, *args, **kwargs):
        uploaded_file = request.FILES.get('file')
        if not uploaded_file:
            return WebUtils.response_error("请上传文件")

        data = dict(
            os=request.data['os'],
            type=request.data['type'],
            object=request.data['object'],
            version=request.data['version'],
            name=uploaded_file.name,
            description=request.data.get('description', ''),
            created_by=request.user.username,
            updated_by=request.user.username,
        )
        serializer = self.get_serializer(data=data)
        serializer.is_valid(raise_exception=True)

        # 上传文件，成功了再保存数据
        PackageService.upload_file(uploaded_file, data)
        self.perform_create(serializer)
        return WebUtils.response_success(serializer.data)

    @action(detail=False, methods=["get"], url_path="download/(?P<pk>.+?)")
    def download(self, request, pk=None):
        obj = PackageVersion.objects.get(pk=pk)
        file, name = PackageService.download_file(obj)
        return WebUtils.response_file(file, name)
