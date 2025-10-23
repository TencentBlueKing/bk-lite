from typing import Dict, Any, TYPE_CHECKING

if TYPE_CHECKING:
    from neco.llm.rag.naive_rag_entity import DocumentListRequest


class QueryBuilder:
    """SQL查询构建器 - 职责分离"""

    @staticmethod
    def build_metadata_filter(metadata_filter: dict, params: Dict[str, Any]) -> str:
        """构建元数据过滤条件"""
        if not metadata_filter:
            return ""

        conditions = []
        for key, value in metadata_filter.items():
            condition = QueryBuilder._build_single_filter_condition(
                key, value, params)
            if condition:
                conditions.append(condition)

        return "(" + " AND ".join(conditions) + ")" if conditions else ""

    @staticmethod
    def _build_single_filter_condition(key: str, value: Any, params: Dict[str, Any]) -> str:
        """构建单个过滤条件"""
        param_key = f"metadata_{key}".replace(".", "_")

        if key.endswith("__exists"):
            field_key = key.replace("__exists", "")
            params[f"metadata_{field_key}_exists"] = field_key
            return f"e.cmetadata ? %(metadata_{field_key}_exists)s"
        elif key.endswith("__missing"):
            field_key = key.replace("__missing", "")
            params[f"metadata_{field_key}_missing"] = field_key
            return f"NOT (e.cmetadata ? %(metadata_{field_key}_missing)s)"
        elif key.endswith("__like"):
            field_key = key.replace("__like", "")
            params[f"{param_key}_field"] = field_key
            params[f"{param_key}_value"] = str(value)
            return f"e.cmetadata->>%({param_key}_field)s LIKE %({param_key}_value)s"
        elif key.endswith("__ilike"):
            field_key = key.replace("__ilike", "")
            params[f"{param_key}_field"] = field_key
            params[f"{param_key}_value"] = str(value)
            return f"e.cmetadata->>%({param_key}_field)s ILIKE %({param_key}_value)s"
        elif key.endswith("__not_blank"):
            field_key = key.replace("__not_blank", "")
            params[f"metadata_{field_key}_not_blank_exists"] = field_key
            params[f"metadata_{field_key}_not_blank_field"] = field_key
            return f"(e.cmetadata ? %(metadata_{field_key}_not_blank_exists)s AND TRIM(e.cmetadata->>%(metadata_{field_key}_not_blank_field)s) != '')"
        elif key.endswith("__in"):
            field_key = key.replace("__in", "")
            if isinstance(value, list) and value:
                params[f"{param_key}_field"] = field_key
                params[f"{param_key}_value"] = value
                return f"e.cmetadata->>%({param_key}_field)s = ANY(%({param_key}_value)s)"
        else:
            params[f"{param_key}_field"] = key
            params[f"{param_key}_value"] = str(value)
            return f"e.cmetadata->>%({param_key}_field)s = %({param_key}_value)s"

        return ""

    @staticmethod
    def build_document_list_query(req: 'DocumentListRequest', where_clause: str, params: Dict[str, Any]) -> str:
        """构建文档列表查询SQL - 安全的参数化查询"""
        # 构建排序子句 - 防止SQL注入
        sort_order = req.sort_order.upper() if req.sort_order else "DESC"
        if sort_order not in ["ASC", "DESC"]:
            sort_order = "DESC"

        # 白名单验证排序字段，防止SQL注入
        allowed_sort_fields = ['created_time',
                               'updated_time', 'knowledge_id', 'chunk_id']
        sort_field = req.sort_field if req.sort_field in allowed_sort_fields else 'created_time'

        # 使用参数化查询构建ORDER BY子句
        params['sort_field'] = sort_field
        order_clause = f"ORDER BY (e.cmetadata->>%(sort_field)s)::timestamp {sort_order}"

        # 分页参数
        limit_clause = ""
        if req.page > 0 and req.size > 0:
            offset = (req.page - 1) * req.size
            params['limit'] = req.size
            params['offset'] = offset
            limit_clause = "LIMIT %(limit)s OFFSET %(offset)s"

        # 构建完整查询 - 使用参数占位符而非字符串拼接
        base_query = """
        SELECT e.id, e.document, e.cmetadata,
               COALESCE(qa_stats.qa_count, 0) as qa_count
        FROM langchain_pg_embedding e
        JOIN langchain_pg_collection c ON e.collection_id = c.uuid
        LEFT JOIN (
            SELECT qa.cmetadata->>'base_chunk_id' as base_chunk_id,
                   COUNT(*) as qa_count
            FROM langchain_pg_embedding qa
            WHERE qa.cmetadata->>'base_chunk_id' IS NOT NULL 
              AND qa.cmetadata->>'base_chunk_id' != ''
              AND qa.cmetadata ? 'qa_answer'
            GROUP BY qa.cmetadata->>'base_chunk_id'
        ) qa_stats ON qa_stats.base_chunk_id = e.id::text
        WHERE """

        # 安全地组装完整查询
        full_query = base_query + where_clause
        if order_clause:
            full_query += f" {order_clause}"
        if limit_clause:
            full_query += f" {limit_clause}"

        return full_query
