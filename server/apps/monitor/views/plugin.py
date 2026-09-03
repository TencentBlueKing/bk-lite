from django.db import ProgrammingError
from django.db.models import Prefetch, Q
from rest_framework import status, viewsets
from rest_framework.decorators import action

from apps.core.decorators.api_permission import HasPermission
from apps.core.exceptions.base_app_exception import BaseAppException
from apps.core.utils.loader import LanguageLoader
from apps.core.utils.web_utils import WebUtils
from apps.monitor.constants.language import LanguageConstants
from apps.monitor.filters.plugin import MonitorPluginFilter
from apps.monitor.models import MonitorPlugin, MonitorPluginUITemplate
from apps.monitor.models.monitor_object import MonitorObject
from apps.monitor.serializers.plugin import MonitorPluginListSerializer, MonitorPluginSerializer
from apps.monitor.services.custom_snmp_plugin import CustomSnmpPluginService
from apps.monitor.services.plugin import MonitorPluginService
from apps.monitor.services.plugin_guide import PluginGuideService
from apps.monitor.services.template_access_guide import TemplateAccessGuideService
from apps.monitor.utils.pagination import parse_page_params
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

    def get_serializer_class(self):
        if self.action == "list":
            return MonitorPluginListSerializer
        return MonitorPluginSerializer

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

    @staticmethod
    def _entry_context_prefetch():
        # 一次 Prefetch 拉取插件关联对象及其父对象，既覆盖正常的根对象绑定，
        # 也兼容存量复合插件只绑定派生对象的情况。
        return Prefetch(
            "monitor_object",
            queryset=MonitorObject.objects.select_related("parent", "type", "parent__type"),
            to_attr="entry_context_objects",
        )

    @staticmethod
    def _filter_visible_entry_plugins(queryset):
        """隐藏入口对象时，不再向集成列表暴露对应插件。

        未绑定对象的存量插件保持原有可查询行为；已绑定插件只有在根对象可见时
        才能作为接入入口。额外校验关联对象自身可见性，兼容级联可见性落地前
        可能存在的父子状态不一致数据。
        """
        return queryset.filter(
            Q(monitor_object__isnull=True)
            | Q(
                monitor_object__is_visible=True,
                monitor_object__parent__isnull=True,
            )
            | Q(
                monitor_object__is_visible=True,
                monitor_object__parent__is_visible=True,
            )
        ).distinct()

    @staticmethod
    def _build_parent_obj_by_id(plugins) -> dict:
        parent_obj_by_id: dict = {}
        for plugin in plugins:
            parent = MonitorPluginSerializer.get_parent_monitor_object_instance(plugin)
            if parent is not None:
                parent_obj_by_id[parent.id] = parent
        return parent_obj_by_id

    @classmethod
    def _apply_keyword_coarse_filter(cls, queryset, kw: str, lan):
        """缩小 keyword 候选集后再做完整序列化。

        1) DB 粗筛:name / display_name / description / 父对象 name|display_name
           (description 仅扩候选;精筛仍用 display_description,避免 3Com MIB 误命中)
        2) 轻量 i18n 扫描:只读 id/name/display_name/description/template_type,
           用 lan.get 补中文翻译命中(DB 无中文时不会漏「华为」等)
        完整 DRF 序列化 + M2M prefetch 只对候选 id 执行。
        """
        if not kw:
            return queryset

        db_ids = set(
            queryset.filter(
                Q(name__icontains=kw)
                | Q(display_name__icontains=kw)
                | Q(description__icontains=kw)
                | Q(monitor_object__parent__isnull=True, monitor_object__display_name__icontains=kw)
                | Q(monitor_object__parent__isnull=True, monitor_object__name__icontains=kw)
                | Q(monitor_object__parent__display_name__icontains=kw)
                | Q(monitor_object__parent__name__icontains=kw)
            ).values_list("id", flat=True)
        )

        # i18n 可能未回写 DB:对剩余插件做轻量扫描(无 M2M / 无完整 serializer)
        for plugin in queryset.only("id", "name", "display_name", "description", "template_type").iterator(chunk_size=200):
            if plugin.id in db_ids:
                continue
            plugin_key = f"{LanguageConstants.MONITOR_OBJECT_PLUGIN}.{plugin.name}"
            if plugin.template_type in {"api", "pull"}:
                display_name = plugin.display_name or plugin.name
                display_description = lan.get(f"{plugin_key}.desc") or plugin.description or plugin.name
            else:
                display_name = lan.get(f"{plugin_key}.name") or plugin.display_name or plugin.name
                display_description = lan.get(f"{plugin_key}.desc") or plugin.description or plugin.name
            haystacks = (
                plugin.name or "",
                display_name or "",
                display_description or "",
            )
            if any(kw in value.lower() for value in haystacks):
                db_ids.add(plugin.id)

        if not db_ids:
            return queryset.none()
        return queryset.filter(id__in=db_ids)

    def _enrich_plugin_results(self, results, lan, parent_obj_by_id: dict):
        """补齐 display_* / is_custom / parent_object_display_name(原地修改)。"""
        for result in results:
            if result.get("template_type") in {"api", "pull"}:
                result["display_name"] = result.get("display_name") or result["name"]
                result["display_description"] = (
                    lan.get(f"{LanguageConstants.MONITOR_OBJECT_PLUGIN}.{result['name']}.desc") or result["description"] or result["name"]
                )
            else:
                plugin_key = f"{LanguageConstants.MONITOR_OBJECT_PLUGIN}.{result['name']}"
                result["display_name"] = lan.get(f"{plugin_key}.name") or result.get("display_name") or result["name"]
                result["display_description"] = lan.get(f"{plugin_key}.desc") or result["description"] or result["name"]
            result["is_custom"] = result.get("template_type") in {"api", "pull", "snmp"}

            parent_id = result.get("parent_monitor_object")
            parent_obj = parent_obj_by_id.get(parent_id) if parent_id is not None else None
            if parent_obj is not None:
                parent_display_name = parent_obj.display_name or parent_obj.name
                result["parent_monitor_object_name"] = parent_obj.name
                result["parent_monitor_object_display_name"] = parent_display_name
                result["parent_monitor_object_icon"] = parent_obj.icon
                result["parent_object_display_name"] = parent_display_name
            else:
                result["parent_monitor_object_name"] = ""
                result["parent_monitor_object_display_name"] = ""
                result["parent_monitor_object_icon"] = ""
                result["parent_object_display_name"] = ""
        return results

    def _serialize_and_enrich(self, queryset, lan):
        plugins = list(queryset.prefetch_related(self._entry_context_prefetch()))
        results = self.get_serializer(plugins, many=True).data
        parent_obj_by_id = self._build_parent_obj_by_id(plugins)
        return self._enrich_plugin_results(results, lan, parent_obj_by_id)

    def list(self, request, *args, **kwargs):
        queryset = self._filter_visible_entry_plugins(self.filter_queryset(self.get_queryset())).order_by("id")
        lan = LanguageLoader(app=LanguageConstants.APP, default_lang=request.user.locale)

        keyword = (request.query_params.get("keyword") or request.query_params.get("name") or "").strip()
        kw = keyword.lower()

        page_size_raw = request.query_params.get("page_size")
        use_pagination = page_size_raw not in (None, "", "0", "-1")

        if use_pagination and not kw:
            page, page_size = parse_page_params(
                request.query_params,
                default_page=1,
                default_page_size=20,
                allow_page_size_all=True,
            )
            if page_size != -1:
                page_size = min(page_size, CustomPageNumberPagination.max_page_size)
            count = queryset.count()
            start = (page - 1) * page_size
            end = start + page_size
            items = self._serialize_and_enrich(queryset[start:end], lan)
            return WebUtils.response_success({"count": count, "items": items})

        if kw:
            queryset = self._apply_keyword_coarse_filter(queryset, kw, lan)

        results = self._serialize_and_enrich(queryset, lan)

        if kw:
            results = [r for r in results if any(kw in (r.get(f) or "").lower() for f in self.KEYWORD_FIELDS)]

        if not use_pagination:
            return WebUtils.response_success(results)

        page, page_size = parse_page_params(
            request.query_params,
            default_page=1,
            default_page_size=20,
            allow_page_size_all=True,
        )
        if page_size != -1:
            page_size = min(page_size, CustomPageNumberPagination.max_page_size)
        count = len(results)
        start = (page - 1) * page_size
        end = start + page_size
        return WebUtils.response_success({"count": count, "items": results[start:end]})

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
        data = request.data.copy()
        data.pop("_mark_objects_builtin", None)
        MonitorPluginService.import_monitor_plugin(data)
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
        from apps.monitor.services.ui_form_field_overlay import overlay_form_field_help_from_plugin_files
        from apps.monitor.services.ui_template_locale import (
            enrich_ui_template_from_plugin_files,
            localize_ui_template,
            resolve_support_collect_detect,
        )

        plugin = self.get_object()
        locale = getattr(request.user, "locale", "zh-Hans") or "zh-Hans"

        try:
            ui_template = MonitorPluginUITemplate.objects.get(plugin=plugin)
            content = overlay_form_field_help_from_plugin_files(
                enrich_ui_template_from_plugin_files(ui_template.content, plugin),
                plugin,
            )
            return WebUtils.response_success(
                {
                    "ui_template": localize_ui_template(content, locale),
                    "node_selector": plugin.node_selector or {},
                    "support_collect_detect": resolve_support_collect_detect(plugin, fallback=plugin.support_collect_detect),
                }
            )
        except MonitorPluginUITemplate.DoesNotExist:
            return WebUtils.response_success(
                {
                    "ui_template": {},
                    "node_selector": plugin.node_selector or {},
                    "support_collect_detect": resolve_support_collect_detect(plugin, fallback=plugin.support_collect_detect),
                }
            )

    @action(methods=["get"], detail=False, url_path="ui_template_by_params")
    def get_ui_template_by_params(self, request):
        """根据采集器名称和采集类型以及监控对象获取插件的 UI 模板。"""
        from apps.monitor.services.ui_form_field_overlay import overlay_form_field_help_from_plugin_files
        from apps.monitor.services.ui_template_locale import (
            enrich_ui_template_from_plugin_files,
            localize_ui_template,
            resolve_support_collect_detect,
        )

        collector = request.query_params.get("collector")
        collect_type = request.query_params.get("collect_type")
        monitor_object_id = request.query_params.get("monitor_object_id")
        monitor_plugin_id = request.query_params.get("monitor_plugin_id")
        locale = getattr(request.user, "locale", "zh-Hans") or "zh-Hans"

        ui_template = MonitorPluginService.get_ui_template_by_params(collector, collect_type, monitor_object_id, monitor_plugin_id)
        plugin_qs = MonitorPlugin.objects.filter(
            monitor_object__id=monitor_object_id,
            collector=collector,
            collect_type=collect_type,
            template_type="builtin",
        )
        if monitor_plugin_id not in (None, ""):
            plugin = plugin_qs.filter(id=monitor_plugin_id).first()
        else:
            matches = list(plugin_qs[:2])
            plugin = matches[0] if len(matches) == 1 else None
        content = overlay_form_field_help_from_plugin_files(
            enrich_ui_template_from_plugin_files(ui_template.get("ui_template"), plugin),
            plugin,
        )
        ui_template["ui_template"] = localize_ui_template(content or {}, locale) if content else content
        ui_template["support_collect_detect"] = resolve_support_collect_detect(plugin, fallback=bool(ui_template.get("support_collect_detect")))
        return WebUtils.response_success(ui_template)

    @HasPermission("integration_collect-View,integration_configure-Add")
    def _get_collect_template(self, request, pk=None):
        plugin = self.get_object()
        if plugin.template_type != "snmp":
            return WebUtils.response_error(error_message="当前模板不是自建 SNMP 模板")

        data = CustomSnmpPluginService.get_collect_template(plugin)
        return WebUtils.response_success(data)

    @HasPermission("integration_configure-Add")
    def _update_collect_template(self, request, pk=None):
        plugin = self.get_object()
        if plugin.template_type != "snmp":
            return WebUtils.response_error(error_message="当前模板不是自建 SNMP 模板")

        data = CustomSnmpPluginService.update_collect_template(
            plugin,
            request.data.get("content", ""),
        )
        return WebUtils.response_success(data)

    @action(methods=["get", "put"], detail=True, url_path="collect_template")
    def collect_template(self, request, pk=None):
        method = request.method.lower()
        if method in {"get", "head"}:
            return self._get_collect_template(request, pk)
        if method == "put":
            return self._update_collect_template(request, pk)
        return WebUtils.response_error(
            error_message="不支持的请求方法",
            status_code=status.HTTP_405_METHOD_NOT_ALLOWED,
        )
