from apps.operation_analysis.models.datasource_models import DataSourceAPIModel
from apps.operation_analysis.services.datasource_preview.base import BaseConnectorExecutor, ConnectorError
from apps.operation_analysis.services.datasource_preview.database import DatabaseConnectorExecutor
from apps.operation_analysis.services.datasource_preview.excel import ExcelConnectorExecutor
from apps.operation_analysis.services.datasource_preview.rest_api import RestApiConnectorExecutor


def get_preview_executor(source_type: str) -> BaseConnectorExecutor:
    if source_type == DataSourceAPIModel.SOURCE_TYPE_REST_API:
        return RestApiConnectorExecutor()
    if source_type == DataSourceAPIModel.SOURCE_TYPE_EXCEL:
        return ExcelConnectorExecutor()
    if source_type in {
        DataSourceAPIModel.SOURCE_TYPE_MYSQL,
        DataSourceAPIModel.SOURCE_TYPE_POSTGRESQL,
    }:
        return DatabaseConnectorExecutor(source_type)

    raise ConnectorError(f"{source_type or 'unknown'} 暂不支持快速预览", code="preview_type_not_supported", status_code=400)
