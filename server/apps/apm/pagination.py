from config.drf.pagination import CustomPageNumberPagination


class ApmCatalogPagination(CustomPageNumberPagination):
    """目录分页仅在调用方显式请求时启用，并限制单页资源消耗。"""

    max_page_size = 100
