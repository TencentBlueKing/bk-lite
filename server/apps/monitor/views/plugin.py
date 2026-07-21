from django.db import ProgrammingError
from django.db.models import Prefetch
from rest_framework import viewsets
from rest_framework.decorators import action

from apps.core.decorators.api_permission import HasPermission
from apps.core.exceptions.base_app_exception import BaseAppException
from apps.core.utils.loader import LanguageLoader
from apps.core.utils.web_utils import WebUtils
from apps.monitor.constants.language import LanguageConstants
from apps.monitor.filters.plugin import MonitorPluginFilter
from apps.monitor.models import MonitorPlugin, MonitorPluginUITemplate
from apps.monitor.models.monitor_object import MonitorObject
from apps.monitor.serializers.plugin import MonitorPluginSerializer
from apps.monitor.services.custom_snmp_plugin import CustomSnmpPluginService
from apps.monitor.services.plugin import MonitorPluginService
from apps.monitor.services.plugin_guide import PluginGuideService
from apps.monitor.services.template_access_guide import TemplateAccessGuideService
from config.drf.pagination import CustomPageNumberPagination


class MonitorPluginViewSet(viewsets.ModelViewSet):
    queryset = MonitorPlugin._default_manager.all()
    serializer_class = MonitorPluginSerializer
    filterset_class = MonitorPluginFilter
    pagination_class = CustomPageNumberPagination

    # BL-NEW-005：MonitorPlugin 为全局资源，历史实现仅依赖全局 IsAuthenticated，
    # 标准 CRUD 与 import/export 等自定义 Action 均未配置业务权限，任意登录用户即可
    # 增删改 / 导入全局监控插件（功能级授权缺失、垂直越权）。下方为写操作补齐明确
    # 权限校验，并将内置插件（is_pre）置为只读。
    @staticmethod
    def _ensure_modifiable(plugin):
        """内置插件只读，禁止修改 / 删除（BL-NEW-005）。"""
        if getattr(plugin, "is_pre", False):
            raise BaseAppException("内置插件为只读，禁止修改或删除")

    @HasPermission("integration_configure-Add")
    def create(self, request, *args, **kwargs):
        return super().create(request, *args, **kwargs)

    @HasPermission("integration_list-Setting")
    def update(self, request, *args, **kwargs):
        self._ensure_modifiable(self.get_object())
        return super().update(request, *args, **kwargs)

    @HasPermission("integration_list-Setting")
    def partial_update(self, request, *args, **kwargs):
        self._ensure_modifiable(self.get_object())
        return super().partial_update(request, *args, **kwargs)

    # 关键字搜索命中的展示字段(必须与前端 page.tsx / 卡片可见字段一致)
    # 1) plugin.name — 技术标识,兼容老用法
    # 2) display_name — i18n 翻译(用户实际看到的标题)
    # 3) display_description — i18n 翻译(用户实际看到的描述,fallback 到 DB description)
    # 4) parent_object_display_name — 卡片 tag(关联父监控对象的 display_name)
    # 注意:不搜 DB 字段 description。
    # 原因:description 是后端技术细节(含 OID / MIB / 企业号 等),
    # 即使 i18n display_description 是用户可见的短版,DB description 仍可能含历史技术引用
    # (例如 3Com 的 A3COM-HUAWEI-LswDEVM-MIB),搜「huawei」会误中 3Com 插件。
    # i18n 缺失场景由 display_description 的 fallback 链覆盖,不会丢命中。
    KEYWORD_FIELDS = (
        "name",
        "display_name",
        "display_description",
        "parent_object_display_name",
    )

    def list(self, request, *args, **kwargs):
        # 一次 Prefetch 把「父监控对象」(parent__isnull=True) 全部拉到内存,
        # 缓存到 plugin.parent_objects(to_attr),供下面两个消费者复用:
        #   1. serializer.get_parent_monitor_object  — 取第一个父对象 id
        #   2. 本视图 — 拼 id -> obj 字典,供 result['parent_object_display_name'] 用
        # 必须用 to_attr 而不是普通 prefetch_related('monitor_object'),
        # 因为 serializer 内部是 .filter(parent__isnull=True),该 filter 不在普通 prefetch 缓存里,
        # 会绕过缓存重新发 SQL(每个 plugin 一次 N+1)。
        parent_prefetch = Prefetch(
            "monitor_object",
            queryset=MonitorObject.objects.filter(parent__isnull=True),
            to_attr="parent_objects",
        )
        # 同时预取默认关联 + 父对象子集:
        # - "monitor_object"  填充 obj.monitor_object 默认缓存,供 DRF __all__ 序列化用
        #                   (ManyToMany 关系,DRF 会调 .all() 取 PK 列表,否则每条 plugin 一次 SQL)
        # - parent_prefetch  填充 obj.parent_objects(to_attr),供 get_parent_monitor_object 与本视图用
        # 两个 prefetch 在 Django 层是独立查询,但都是单次 SQL,
        # 整 list 视图稳定 3 次 SQL:1 主查询 + 2 预取,与插件数无关。
        queryset = self.filter_queryset(self.get_queryset()).prefetch_related(
            "monitor_object",
            parent_prefetch,
        )
        serializer = self.get_serializer(queryset, many=True)
        results = serializer.data

        lan = LanguageLoader(app=LanguageConstants.APP, default_lang=request.user.locale)

        # 把 prefetch 出的父对象拼成 id -> obj 字典,后续 O(1) 查表
        # 直接读 to_attr 缓存,不再发 SQL
        parent_obj_by_id: dict = {}
        for plugin in queryset:
            for obj in getattr(plugin, "parent_objects", []):
                parent_obj_by_id[obj.id] = obj

        # keyword 优先;name 作为兼容 alias(老调用方可能还在用 ?name=xxx)
        # 两者走完全相同的翻译后内存搜索逻辑,行为对齐
        keyword = (request.query_params.get("keyword") or request.query_params.get("name") or "").strip()
        kw = keyword.lower()

        for result in results:
            if result.get("template_type") in {"api", "pull"}:
                result["display_name"] = result.get("display_name") or result["name"]
                # 优先 i18n 翻译,fallback DB 字段(避免强制覆盖)
                result["display_description"] = (
                    lan.get(f"{LanguageConstants.MONITOR_OBJECT_PLUGIN}.{result['name']}.desc") or result["description"] or result["name"]
                )
            else:
                plugin_key = f"{LanguageConstants.MONITOR_OBJECT_PLUGIN}.{result['name']}"
                # 始终优先使用 i18n 翻译,DB 字段只作为最终 fallback
                result["display_name"] = lan.get(f"{plugin_key}.name") or result.get("display_name") or result["name"]
                # 同 display_name:优先 i18n 翻译,fallback DB 字段(可能多语言混合),最后 fallback 到 name
                result["display_description"] = lan.get(f"{plugin_key}.desc") or result["description"] or result["name"]
            result["is_custom"] = result.get("template_type") in {"api", "pull", "snmp"}

            # 父监控对象 display_name(用于关键字搜索覆盖卡片上的「交换机/路由器」tag)
            parent_id = result.get("parent_monitor_object")
            parent_obj = parent_obj_by_id.get(parent_id) if parent_id is not None else None
            if parent_obj is not None:
                # MonitorObject.display_name 是 DB 字段,无需 i18n
                result["parent_object_display_name"] = parent_obj.display_name or parent_obj.name
            else:
                result["parent_object_display_name"] = ""

        # 「所见即所搜」:在 i18n 翻译完成后再做内存过滤,覆盖所有卡片可见字段
        # 必须放在 i18n 之后,否则 DB 侧裁掉的就再也回不来了
        if kw:
            results = [r for r in results if any(kw in (r.get(f) or "").lower() for f in self.KEYWORD_FIELDS)]

        return WebUtils.response_success(results)

    @HasPermission("integration_list-Setting")
    def destroy(self, request, *args, **kwargs):
        plugin = self.get_object()
        self._ensure_modifiable(plugin)
        if plugin.template_type in {"api", "pull", "snmp"}:
            try:
                plugin.delete()
            except ProgrammingError as exc:
                if "monitor_plugin_id" in str(exc):
                    raise BaseAppException("当前数据库缺少 monitor_collectconfig.monitor_plugin_id 字段，请先执行 monitor 应用最新迁移") from exc
                raise
            return WebUtils.response_success()
        return super().destroy(request, *args, **kwargs)

    @action(methods=["get"], detail=True, url_path="access_guide")
    def get_access_guide(self, request, pk=None):
        plugin = self.get_object()
        if plugin.template_type != "api":
            return WebUtils.response_error(error_message="当前模板不是自建API模板")

        organization_id = TemplateAccessGuideService.resolve_required_int(request.query_params.get("organization_id"), "organization_id")
        cloud_region_id = TemplateAccessGuideService.resolve_required_int(request.query_params.get("cloud_region_id"), "cloud_region_id")
        data = TemplateAccessGuideService.get_template_document(
            plugin,
            organization_id=organization_id,
            cloud_region_id=cloud_region_id,
        )
        return WebUtils.response_success(data)

    @action(methods=["get"], detail=True, url_path="guide")
    def get_plugin_guide(self, request, pk=None):
        """返回插件目录 Markdown 指引；无文档时 has_guide=false。"""
        plugin = self.get_object()
        locale = getattr(request.user, "locale", None) or request.query_params.get("locale")
        data = PluginGuideService.get_guide(plugin, locale=locale)
        return WebUtils.response_success(data)

    @action(methods=["post"], detail=False, url_path="import")
    @HasPermission("integration_configure-Add")
    def import_monitor_object(self, request):
        MonitorPluginService.import_monitor_plugin(request.data)
        return WebUtils.response_success()

    @action(methods=["get"], detail=False, url_path="export/(?P<pk>[^/.]+)")
    @HasPermission("integration_list-View")
    def export_monitor_object(self, request, pk):
        data = MonitorPluginService.export_monitor_plugin(pk)
        return WebUtils.response_success(data)

    @action(methods=["get"], detail=True, url_path="ui_template")
    def get_ui_template(self, request, pk=None):
        """
        获取插件的 UI 模板。

        :param pk: 插件 ID
        :return: UI 模板内容（JSON 格式）。form_fields/table_columns 内
            的 label 字段已按 request.user.locale 自动选 label/label_en。
        """
        from apps.monitor.services.ui_template_locale import localize_ui_template

        plugin = self.get_object()
        locale = getattr(request.user, "locale", "zh-Hans") or "zh-Hans"

        try:
            ui_template = MonitorPluginUITemplate.objects.get(plugin=plugin)
            return WebUtils.response_success(
                {
                    "ui_template": localize_ui_template(ui_template.content, locale),
                    "node_selector": plugin.node_selector or {},
                    "support_collect_detect": plugin.support_collect_detect,
                }
            )
        except MonitorPluginUITemplate.DoesNotExist:
            return WebUtils.response_success(
                {
                    "ui_template": {},
                    "node_selector": plugin.node_selector or {},
                    "support_collect_detect": plugin.support_collect_detect,
                }
            )

    @action(methods=["get"], detail=False, url_path="ui_template_by_params")
    def get_ui_template_by_params(self, request):
        """根据采集器名称和采集类型以及监控对象获取插件的 UI 模板。"""
        collector = request.query_params.get("collector")
        collect_type = request.query_params.get("collect_type")
        monitor_object_id = request.query_params.get("monitor_object_id")

        ui_template = MonitorPluginService.get_ui_template_by_params(collector, collect_type, monitor_object_id)
        return WebUtils.response_success(ui_template)

    @action(methods=["get", "put"], detail=True, url_path="collect_template")
    @HasPermission("integration_collect-View,integration_configure-Add")
    def collect_template(self, request, pk=None):
        plugin = self.get_object()
        if plugin.template_type != "snmp":
            return WebUtils.response_error(error_message="当前模板不是自建 SNMP 模板")

        if request.method.lower() == "get":
            data = CustomSnmpPluginService.get_collect_template(plugin)
            return WebUtils.response_success(data)

        data = CustomSnmpPluginService.update_collect_template(
            plugin,
            request.data.get("content", ""),
        )
        return WebUtils.response_success(data)
