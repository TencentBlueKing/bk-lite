from rest_framework.pagination import PageNumberPagination

from config.drf.pagination import CustomPageNumberPagination


class ApmCatalogPagination(CustomPageNumberPagination):
    """目录分页仅在调用方显式请求时启用，并限制单页资源消耗。"""

    max_page_size = 100


class ApmDeploymentPagination(ApmCatalogPagination):
    """部署列表始终分页，未传 page_size 时使用默认页长，拒绝无界拉取。"""

    page_size = 20

    def paginate_queryset(self, queryset, request, view=None):
        return PageNumberPagination.paginate_queryset(self, queryset, request, view)
