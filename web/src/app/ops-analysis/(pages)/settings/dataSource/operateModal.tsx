"use client";

/**
 * 数据源抽屉协调器：只负责打开/关闭、回填、预览、保存、提取到连接库。
 * 源类型表单在 *Fields；回填/payload/预览字段在 operateModalUtils。
 */
import React, { useEffect } from "react";
import { v4 as uuidv4 } from "uuid";
import { getChartTypeList } from "@/app/ops-analysis/constants/common";
import { QuestionCircleOutlined } from "@ant-design/icons";
import { useDataSourceApi } from "@/app/ops-analysis/api/dataSource";
import { useDataConnectionApi } from "@/app/ops-analysis/api/dataConnection";
import { useOpsAnalysis } from "@/app/ops-analysis/context/common";
import { useNamespaceApi } from "@/app/ops-analysis/api/namespace";
import { useUserInfoContext } from "@/context/userInfo";
import { useTranslation } from "@/utils/i18n";
import useUnsavedConfirm from "@/hooks/useUnsavedConfirm";
import {
  DataSourcePreviewResult,
  DataSourceSourceType,
  OperateModalProps,
  ParamItem,
} from "@/app/ops-analysis/types/dataSource";
import { DataConnectionItem } from "@/app/ops-analysis/types/dataConnection";
import { TagItem } from "@/app/ops-analysis/types/namespace";
import { Drawer, Form, Button, message, Tooltip } from "antd";
import type { UploadFile } from "antd/es/upload/interface";
import ParamTable, { ParamTableRef } from "./paramTable";
import FieldSchemaTable, { FieldSchemaTableRef } from "./fieldSchemaTable";
import PreviewPanel from "./previewPanel";
import TransformScriptPanel from "@/app/ops-analysis/components/ops-analysis-transform-script-panel";
import { ExcelMaterializationState } from "@/app/ops-analysis/components/ops-analysis-excel-materialization-status";
import {
  buildBuiltinGroupsPayload,
  buildConnectorPayload,
  buildConnectionLibraryCreateFromDatasourceForm,
  buildHydratedDatasourceFormState,
  canEditBuiltinDatasourceGroups,
  canExtractConnectionFromDatasourceForm,
  canSaveExcelWithoutNewFile,
  isBuiltinDatasource,
  isDatasourceDefinitionReadOnly,
  shouldCreateLibraryConnectionFromForm,
  createDefaultParam,
  createDefaultSchemaField,
  createDefaultTransformConfig,
  createPrometheusDefaultParams,
  getDatasourceSourceFlags,
  getPreviewFieldNames,
  normalizeFieldSchema,
  normalizeParams,
  normalizeTransformConfig,
  PASSWORD_PLACEHOLDER,
  PROMETHEUS_DEFAULT_CHART_TYPES,
  SchemaField,
  SOURCE_TYPE_EXCEL,
  SOURCE_TYPE_MYSQL,
  SOURCE_TYPE_NATS,
  SOURCE_TYPE_POSTGRESQL,
  SOURCE_TYPE_PROMETHEUS,
  SOURCE_TYPE_REST_API,
  TABLE_CHART_TYPE,
} from "./operateModalUtils";
import {
  FormSection,
  FormSubsection,
  fieldDomId,
  resolveSectionForFieldName,
  resolveSubsectionForFieldName,
  type FormSectionId,
  type FormSubsectionId,
} from "./operateModalFormLayout";
import { DatasourceBasicFields } from "./datasourceBasicFields";
import { RestApiConnectFields } from "./restApiConnectFields";
import { DatabaseConnectFields } from "./databaseConnectFields";
import { PrometheusConnectFields } from "./prometheusConnectFields";
import { ExcelConnectFields } from "./excelConnectFields";
import { ExtractConnectionModal } from "./extractConnectionModal";

const OperateModal: React.FC<OperateModalProps> = ({
  open,
  mode,
  currentRow,
  onClose,
  onSuccess,
}) => {
  const { t } = useTranslation();
  const guardClose = useUnsavedConfirm();
  const [form] = Form.useForm();
  const readOnly = mode === "view";
  const handleClose = () =>
    readOnly ? onClose() : guardClose(form.isFieldsTouched(), onClose);
  const { selectedGroup, isSuperUser } = useUserInfoContext();
  const definitionReadOnly = isDatasourceDefinitionReadOnly(mode, currentRow);
  const groupsReadOnly =
    mode === "view" ||
    (isBuiltinDatasource(currentRow)
      ? !canEditBuiltinDatasourceGroups(isSuperUser, currentRow)
      : false);
  const canSaveDatasource =
    mode !== "view" &&
    (!isBuiltinDatasource(currentRow) ||
      canEditBuiltinDatasourceGroups(isSuperUser, currentRow));
  const [params, setParams] = React.useState<ParamItem[]>([]);
  const [loading, setLoading] = React.useState(false);
  const [schemaFields, setSchemaFields] = React.useState<SchemaField[]>([]);
  const [showSchemaConfig, setShowSchemaConfig] = React.useState(true);
  const [tagList, setTagList] = React.useState<TagItem[]>([]);
  const [tagsLoading, setTagsLoading] = React.useState(false);
  const [previewLoading, setPreviewLoading] = React.useState(false);
  const [testConnectionLoading, setTestConnectionLoading] =
    React.useState(false);
  const [previewData, setPreviewData] =
    React.useState<DataSourcePreviewResult | null>(null);
  const [rawPreviewData, setRawPreviewData] =
    React.useState<DataSourcePreviewResult | null>(null);
  const [transformPreviewError, setTransformPreviewError] = React.useState<
    string | null
  >(null);
  const [sourceInlineError, setSourceInlineError] = React.useState<string | null>(
    null,
  );
  const [previewInlineError, setPreviewInlineError] = React.useState<
    string | null
  >(null);
  const [excelMaterialization, setExcelMaterialization] =
    React.useState<ExcelMaterializationState | null>(null);
  const [excelRetryLoading, setExcelRetryLoading] = React.useState(false);
  const [excelFile, setExcelFile] = React.useState<File | null>(null);
  const [excelFileList, setExcelFileList] = React.useState<UploadFile[]>([]);
  const [extractLoading, setExtractLoading] = React.useState(false);
  const [extractModalOpen, setExtractModalOpen] = React.useState(false);
  const [extractForm] = Form.useForm();
  const previousSourceTypeRef = React.useRef<DataSourceSourceType | undefined>(
    undefined,
  );
  // 打开弹窗回填期间跳过 source_type 切换副作用，避免清空刚回显的 transform_config
  const hydratingSourceTypeRef = React.useRef(false);
  const paramTableRef = React.useRef<ParamTableRef>(null);
  const fieldSchemaTableRef = React.useRef<FieldSchemaTableRef>(null);
  const formScrollRef = React.useRef<HTMLDivElement>(null);
  const { namespaceList, namespacesLoading, refreshNamespaces } =
    useOpsAnalysis();
  const {
    createDataSource,
    updateDataSource,
    patchDataSource,
    deleteDataSource,
    previewDataSource,
    previewDataSourceConfig,
    submitExcelMaterialization,
    retryExcelMaterialization,
    getDataSourceDetail,
    testDataSourceConnection,
    testDataSourceConnectionConfig,
    extractDataSourceConnection,
  } = useDataSourceApi();
  const { getDataConnectionList, createDataConnection } = useDataConnectionApi();
  const { getTagList } = useNamespaceApi();
  const [connectionList, setConnectionList] = React.useState<DataConnectionItem[]>(
    [],
  );
  const sourceType =
    (Form.useWatch("source_type", form) as DataSourceSourceType | undefined) ||
    SOURCE_TYPE_NATS;
  const connectionMode =
    (Form.useWatch("connection_mode", form) as string | undefined) || "connection";
  const watchedConnectionConfig = Form.useWatch("connection_config", form);
  const transformEnabled = Boolean(
    Form.useWatch(["transform_config", "enabled"], form),
  );
  const sourceTypeOptions = [
    { label: t("dataSource.sourceTypes.nats"), value: SOURCE_TYPE_NATS },
    { label: "MySQL", value: SOURCE_TYPE_MYSQL },
    { label: "PostgreSQL", value: SOURCE_TYPE_POSTGRESQL },
    { label: "REST API", value: SOURCE_TYPE_REST_API },
    { label: "Excel", value: SOURCE_TYPE_EXCEL },
    { label: t("dataSource.sourceTypes.prometheus"), value: SOURCE_TYPE_PROMETHEUS },
  ];
  const {
    isNatsSource,
    isRestApiSource,
    isPrometheusSource,
    isDatabaseSource,
    isExcelSource,
    supportsTransform,
    supportsSharedConnection,
  } = getDatasourceSourceFlags(sourceType);
  const useSharedConnection =
    supportsSharedConnection && connectionMode !== "inline";
  const connectSubsectionTitle = isExcelSource
    ? t("dataSource.sections.file")
    : isNatsSource
      ? t("dataSource.queryParams")
      : t("dataSource.sections.connect");
  const previewSubsectionTitle = supportsTransform
    ? t("dataSource.sections.preview")
    : t("dataSource.sections.dataPreview");
  const clearPreviewState = React.useCallback(() => {
    setPreviewData(null);
    setRawPreviewData(null);
    setTransformPreviewError(null);
    setPreviewInlineError(null);
  }, []);

  const clearProcessInlineErrors = React.useCallback(() => {
    setSourceInlineError(null);
    setPreviewInlineError(null);
  }, []);

  const refreshExcelMaterialization = React.useCallback(
    async (datasourceId: number) => {
      try {
        const detail = await getDataSourceDetail(datasourceId);
        setExcelMaterialization(detail?.excel_materialization || null);
        return detail?.excel_materialization || null;
      } catch (error) {
        console.error("刷新 Excel 处理状态失败:", error);
        return null;
      }
    },
    [getDataSourceDetail],
  );

  const reloadConnectionOptions = React.useCallback(async () => {
    if (!supportsSharedConnection) {
      setConnectionList([]);
      return;
    }
    try {
      const response = await getDataConnectionList({
        page_size: -1,
        connection_type: sourceType,
        is_active: true,
      });
      const items = Array.isArray(response?.items)
        ? response.items
        : Array.isArray(response)
          ? response
          : [];
      setConnectionList(items);
    } catch (error) {
      console.error("刷新连接库列表失败:", error);
    }
  }, [getDataConnectionList, sourceType, supportsSharedConnection]);

  const openExtractConnectionModal = React.useCallback(async () => {
    const connectionFields = isRestApiSource
      ? [["connection_config", "url"]]
      : [
        ["connection_config", "host"],
        ["connection_config", "port"],
        ["connection_config", "database"],
        ["connection_config", "username"],
        ["connection_config", "password"],
      ];

    try {
      await form.validateFields(connectionFields);
    } catch {
      return;
    }

    const values = form.getFieldsValue(true);
    if (!canExtractConnectionFromDatasourceForm(values)) {
      message.error(t("common.inputMsg"));
      return;
    }

    extractForm.resetFields();
    setExtractModalOpen(true);
  }, [extractForm, form, isRestApiSource, t]);

  const handleExtractToConnectionLibrary = React.useCallback(async () => {
    let meta: { name: string; description?: string };
    try {
      meta = await extractForm.validateFields();
    } catch {
      return;
    }

    const connectionName = String(meta.name || "").trim();
    if (!connectionName) {
      return;
    }
    const connectionDescription = String(meta.description || "").trim();

    try {
      setExtractLoading(true);
      const values = form.getFieldsValue(true);
      if (!canExtractConnectionFromDatasourceForm(values)) {
        throw new Error(t("common.inputMsg"));
      }
      const createFromForm = shouldCreateLibraryConnectionFromForm(
        currentRow,
        values.source_type,
      );
      if (
        createFromForm &&
        (isDatabaseSource || isRestApiSource) &&
        values.connection_config?.password === PASSWORD_PLACEHOLDER
      ) {
        throw new Error(t("dataConnection.reenterPassword"));
      }
      const built = buildConnectionLibraryCreateFromDatasourceForm(values, {
        t,
        name: connectionName,
        description: connectionDescription,
      });
      let connectionId: number | undefined;
      let nextOverrides = built.connectionOverrides;
      let nextConnectionConfig: Record<string, unknown> = isRestApiSource
        ? {
          method: values.connection_config?.method || "GET",
          timeout: values.connection_config?.timeout || 10,
        }
        : {};

      if (currentRow?.id && !createFromForm) {
        const result = await extractDataSourceConnection(currentRow.id, {
          name: built.createPayload.name,
          description: built.createPayload.description,
          connection_config: built.inlineConnectionConfig,
        });
        connectionId =
          result?.connection?.id ||
          result?.data?.connection?.id ||
          result?.datasource?.connection_id;
        const datasource = result?.datasource || result?.data?.datasource;
        if (datasource?.connection_overrides) {
          nextOverrides = datasource.connection_overrides;
        }
        if (
          isRestApiSource &&
          datasource?.connection_config &&
          typeof datasource.connection_config === "object"
        ) {
          nextConnectionConfig = {
            method: datasource.connection_config.method || "GET",
            timeout: datasource.connection_config.timeout || 10,
          };
        }
        onSuccess?.();
      } else {
        const created = await createDataConnection(built.createPayload);
        connectionId = created?.id || created?.data?.id;
      }

      if (!connectionId) {
        throw new Error(t("dataConnection.operationFailed"));
      }

      await reloadConnectionOptions();
      form.setFieldsValue({
        connection_mode: "connection",
        connection: connectionId,
        connection_overrides: nextOverrides,
        connection_config: nextConnectionConfig,
      });
      setExtractModalOpen(false);
      extractForm.resetFields();
      message.success(t("dataConnection.createSuccess"));
    } catch (error: any) {
      message.error(error?.message || t("dataConnection.operationFailed"));
    } finally {
      setExtractLoading(false);
    }
  }, [
    createDataConnection,
    currentRow,
    extractDataSourceConnection,
    extractForm,
    form,
    isDatabaseSource,
    isRestApiSource,
    onSuccess,
    reloadConnectionOptions,
    t,
  ]);

  const canExtractToConnectionLibrary = canExtractConnectionFromDatasourceForm({
    source_type: sourceType,
    connection_config: watchedConnectionConfig,
  });

  const extractToConnectionLibraryButton =
    !useSharedConnection && !definitionReadOnly ? (
      <Button
        className="mb-2"
        disabled={!canExtractToConnectionLibrary}
        onClick={() => {
          void openExtractConnectionModal();
        }}
      >
        {t("dataConnection.extractConnection")}
      </Button>
    ) : null;

  const scrollToFormError = React.useCallback(
    (
      errorFields?: Array<{ name: string | number | (string | number)[] }>,
      fallbackSection?: FormSectionId,
      fallbackSubsection?: FormSubsectionId,
    ) => {
      const firstName = errorFields?.[0]?.name;
      const subsection = firstName
        ? resolveSubsectionForFieldName(firstName)
        : fallbackSubsection || null;
      const section = firstName
        ? resolveSectionForFieldName(firstName)
        : fallbackSection || "basic";

      const container = formScrollRef.current;
      if (!container) return;

      if (firstName) {
        try {
          form.scrollToField(firstName, {
            behavior: "smooth",
            block: "center",
          });
        } catch {
          // ignore — below backs up with container scroll
        }
      }

      window.requestAnimationFrame(() => {
        let target: HTMLElement | null = null;
        if (firstName) {
          const id = fieldDomId(firstName);
          const byId = container.querySelector(`#${CSS.escape(id)}`);
          target =
            (byId?.closest(".ant-form-item") as HTMLElement | null) ||
            (byId as HTMLElement | null);
        }
        if (!target) {
          target = container.querySelector(
            ".ant-form-item-has-error, .ant-form-item-explain-error",
          ) as HTMLElement | null;
          if (target?.classList.contains("ant-form-item-explain-error")) {
            target = target.closest(".ant-form-item") as HTMLElement | null;
          }
        }
        if (!target && subsection) {
          target = document.getElementById(`ds-form-subsection-${subsection}`);
        }
        if (!target) {
          target = document.getElementById(`ds-form-section-${section}`);
        }
        if (!target) return;
        const containerTop = container.getBoundingClientRect().top;
        const targetTop = target.getBoundingClientRect().top;
        container.scrollTo({
          top: container.scrollTop + targetTop - containerTop - 24,
          behavior: "smooth",
        });
      });
    },
    [form],
  );

  useEffect(() => {
    if (!open) return;

    const frame = window.requestAnimationFrame(() => {
      formScrollRef.current?.scrollTo({ top: 0 });
    });
    return () => window.cancelAnimationFrame(frame);
  }, [open, currentRow?.id]);
  const prometheusAuthType =
    Form.useWatch(["connection_config", "auth_type"], form) || "none";
  const prometheusQueryType =
    Form.useWatch(["query_config", "query_type"], form) || "range";
  const chartTypeOptions = getChartTypeList()
    .filter((item) => {
      if (isNatsSource) return true;
      if (isPrometheusSource) {
        return PROMETHEUS_DEFAULT_CHART_TYPES.includes(
          item.value as (typeof PROMETHEUS_DEFAULT_CHART_TYPES)[number],
        );
      }
      return item.value === TABLE_CHART_TYPE;
    })
    .map((item) => ({
      label: t(item.label),
      value: item.value,
    }));

  useEffect(() => {
    if (!open) {
      hydratingSourceTypeRef.current = false;
      return;
    }

    let cancelled = false;

    const fetchTags = async () => {
      try {
        setTagsLoading(true);
        const response = await getTagList({ page_size: -1 });
        if (cancelled) return;
        setTagList(Array.isArray(response) ? response : []);
      } catch (error) {
        console.error("获取标签列表失败:", error);
        if (!cancelled) setTagList([]);
      } finally {
        if (!cancelled) setTagsLoading(false);
      }
    };

    const hydrateForm = (row: typeof currentRow) => {
      if (cancelled) return;

      form.resetFields();
      paramTableRef.current?.clearValidation();
      fieldSchemaTableRef.current?.clearValidation();
      setShowSchemaConfig(true);
      clearPreviewState();
      clearProcessInlineErrors();
      setExcelFile(null);
      setExcelFileList([]);
      setExcelMaterialization(row?.excel_materialization || null);

      const targetSourceType = row?.source_type || SOURCE_TYPE_NATS;
      hydratingSourceTypeRef.current = true;
      previousSourceTypeRef.current = targetSourceType;

      const hydrated = buildHydratedDatasourceFormState(row, {
        selectedGroupId: selectedGroup?.id,
        t,
      });
      form.setFieldsValue(hydrated.formValues);
      setParams(hydrated.params);
      setSchemaFields(hydrated.schemaFields);
      if (hydrated.excelPreview) {
        setPreviewData(hydrated.excelPreview);
      }
    };

    void refreshNamespaces();
    void fetchTags();

    const load = async () => {
      if (!currentRow?.id) {
        hydrateForm(undefined);
        return;
      }
      // 编辑/查看始终拉详情，避免列表摘要缺 transform_config 等字段
      try {
        const detail = await getDataSourceDetail(currentRow.id);
        if (cancelled) return;
        hydrateForm({ ...currentRow, ...detail });
      } catch (error) {
        console.error("加载数据源详情失败，回退列表行:", error);
        if (!cancelled) hydrateForm(currentRow);
      }
    };
    void load();

    return () => {
      cancelled = true;
    };
  }, [
    open,
    currentRow,
    form,
    selectedGroup,
    refreshNamespaces,
    getTagList,
    getDataSourceDetail,
    clearPreviewState,
    t,
  ]);

  useEffect(() => {
    if (!open || !supportsSharedConnection) {
      setConnectionList([]);
      return;
    }
    const loadConnections = async () => {
      try {
        const response = await getDataConnectionList({
          page_size: -1,
          connection_type: sourceType,
          is_active: true,
        });
        const items = Array.isArray(response?.items)
          ? response.items
          : Array.isArray(response)
            ? response
            : [];
        setConnectionList(items);
      } catch (error) {
        console.error("获取数据连接失败:", error);
        setConnectionList([]);
      }
    };
    void loadConnections();
  }, [open, supportsSharedConnection, sourceType, getDataConnectionList]);

  useEffect(() => {
    if (!open || !!currentRow || namespaceList.length === 0) {
      return;
    }

    const currentNamespaceValues = form.getFieldValue("namespaces");
    if (
      Array.isArray(currentNamespaceValues) &&
      currentNamespaceValues.length > 0
    ) {
      return;
    }

    form.setFieldsValue({ namespaces: [namespaceList[0].id] });
  }, [open, currentRow, namespaceList, form]);

  useEffect(() => {
    if (!open) {
      previousSourceTypeRef.current = undefined;
      hydratingSourceTypeRef.current = false;
      return;
    }

    // 回填中：等 useWatch 的 source_type 追上目标值后再放开，避免误判为「用户切换类型」
    if (hydratingSourceTypeRef.current) {
      if (sourceType === previousSourceTypeRef.current) {
        hydratingSourceTypeRef.current = false;
      }
      return;
    }

    const previousSourceType = previousSourceTypeRef.current;
    if (!previousSourceType) {
      previousSourceTypeRef.current = sourceType;
      return;
    }

    if (previousSourceType !== sourceType) {
      form.setFieldsValue({
        connection: undefined,
        connection_overrides: {},
        connection_mode:
          sourceType === SOURCE_TYPE_MYSQL ||
          sourceType === SOURCE_TYPE_POSTGRESQL ||
          sourceType === SOURCE_TYPE_REST_API
            ? "inline"
            : form.getFieldValue("connection_mode"),
      });
      if (sourceType === SOURCE_TYPE_PROMETHEUS) {
        form.setFieldsValue({
          chart_type: [...PROMETHEUS_DEFAULT_CHART_TYPES],
          connection_config: {
            auth_type: "none",
            timeout_seconds: 30,
          },
          query_config: {
            query: "up",
            query_type: "range",
            time_range: 60,
            step: "1m",
            max_series: 20,
          },
        });
        setParams(createPrometheusDefaultParams(t));
      } else if (sourceType !== SOURCE_TYPE_NATS) {
        form.setFieldValue("chart_type", [TABLE_CHART_TYPE]);
        setParams([]);
        form.setFieldValue(
          "connection_config",
          sourceType === SOURCE_TYPE_MYSQL
            ? { port: 3306 }
            : sourceType === SOURCE_TYPE_POSTGRESQL
              ? { port: 5432 }
              : sourceType === SOURCE_TYPE_REST_API
                ? { method: "GET", timeout: 10 }
                : {},
        );
      }
      if (sourceType === SOURCE_TYPE_REST_API || sourceType === SOURCE_TYPE_EXCEL) {
        form.setFieldValue(
          "transform_config",
          createDefaultTransformConfig(),
        );
      } else {
        form.setFieldValue(
          "transform_config",
          createDefaultTransformConfig({ enabled: false }),
        );
      }
      clearPreviewState();
      clearProcessInlineErrors();
      setExcelFile(null);
      setExcelFileList([]);
      setExcelMaterialization(null);
      setSchemaFields([]);
      fieldSchemaTableRef.current?.clearValidation();
      previousSourceTypeRef.current = sourceType;
    }
  }, [open, sourceType, form, clearPreviewState, clearProcessInlineErrors]);

  const handlePreview = async () => {
    if (isNatsSource) return;

    try {
      setPreviewLoading(true);
      setTransformPreviewError(null);
      const previewFields = getPreviewFieldNames({
        sourceType,
        useSharedConnection,
        prometheusQueryType,
      });
      if (supportsTransform && transformEnabled) {
        previewFields.push(["transform_config", "script"]);
      }
      await form.validateFields(previewFields);
      const values = form.getFieldsValue(true);
      let response: DataSourcePreviewResult;

      const applyPreviewResponse = (result: DataSourcePreviewResult) => {
        if (result.raw_items) {
          setRawPreviewData({
            items: result.raw_items,
            count: result.raw_count ?? result.raw_items.length,
            fields: result.raw_fields || [],
            warnings: result.warnings,
          });
        } else {
          setRawPreviewData(null);
        }
        if (result.transform_error?.message) {
          setTransformPreviewError(result.transform_error.message);
          setPreviewData({
            items: result.raw_items || result.items || [],
            count: result.raw_count ?? result.count,
            fields: result.raw_fields || result.fields || [],
            warnings: result.warnings,
          });
        } else {
          setTransformPreviewError(null);
          setPreviewData(result);
        }
      };

      if (isExcelSource) {
        const transformConfig = normalizeTransformConfig(values.transform_config);
        if (excelFile) {
          const formData = new FormData();
          formData.append("source_type", SOURCE_TYPE_EXCEL);
          formData.append("limit", "50");
          formData.append("file", excelFile);
          formData.append(
            "transform_config",
            JSON.stringify({
              ...transformConfig,
              enabled: transformEnabled,
            }),
          );
          response = await previewDataSourceConfig(formData);
          applyPreviewResponse(response);
        } else if (
          excelMaterialization?.status === "needs_upload" ||
          (!excelMaterialization?.success_slot_id &&
            !excelMaterialization?.candidate_slot_id)
        ) {
          setSourceInlineError(
            t("dataSource.excelStatus.needsUploadPreviewHint"),
          );
          setPreviewInlineError(null);
          scrollToFormError(undefined, "process", "connect");
          return;
        } else if (currentRow) {
          response = await previewDataSource(currentRow.id, {
            source_type: SOURCE_TYPE_EXCEL,
            limit: 50,
            transform_config: transformEnabled
              ? transformConfig
              : { ...transformConfig, enabled: false },
          });
          applyPreviewResponse(response);
        } else {
          setSourceInlineError(t("dataSource.excelFileRequired"));
          setPreviewInlineError(null);
          scrollToFormError(undefined, "process", "connect");
          return;
        }
      } else {
        const transformConfig = normalizeTransformConfig(values.transform_config);
        const basePayload = {
          ...buildConnectorPayload(values, {
            excelFileName: excelFile?.name,
            hasNewExcelFile: Boolean(excelFile),
            previewData,
            t,
          }),
          groups: values.groups || [],
          limit: 50,
          transform_config: isRestApiSource
            ? {
              ...transformConfig,
              enabled: transformEnabled,
            }
            : undefined,
        };
        response = currentRow
          ? await previewDataSource(currentRow.id, basePayload)
          : await previewDataSourceConfig(basePayload);
        applyPreviewResponse(response);
      }

      setSourceInlineError(null);
      setPreviewInlineError(null);
    } catch (error: any) {
      if (error?.errorFields) {
        scrollToFormError(error.errorFields);
        return;
      }
      setPreviewInlineError(error?.message || t("dataSource.previewFailed"));
      scrollToFormError(undefined, "process", "preview");
    } finally {
      setPreviewLoading(false);
    }
  };

  const handleRetryExcelMaterialization = async () => {
    if (!currentRow || definitionReadOnly) return;
    if (!excelMaterialization?.can_retry) {
      setSourceInlineError(t("dataSource.excelStatus.failedHintReupload"));
      scrollToFormError(undefined, "process", "connect");
      return;
    }
    try {
      setExcelRetryLoading(true);
      const values = form.getFieldsValue(true);
      await retryExcelMaterialization(currentRow.id, {
        transform_config: normalizeTransformConfig(values.transform_config),
        sync: true,
      });
      message.success(t("dataSource.excelStatus.retrySuccess"));
      await refreshExcelMaterialization(currentRow.id);
    } catch (error: any) {
      try {
        await refreshExcelMaterialization(currentRow.id);
      } catch {
        /* ignore refresh errors */
      }
      // 400 已由请求拦截器提示
      if (!error?.status || error.status >= 500) {
        message.error(error?.message || t("dataSource.operationFailed"));
      }
    } finally {
      setExcelRetryLoading(false);
    }
  };

  const handleApplyPreviewFields = () => {
    const fields = previewData?.fields || [];
    if (!fields.length) return;
    setSchemaFields(
      fields.map((field) => ({
        ...field,
        id: uuidv4(),
      })),
    );
    setShowSchemaConfig(true);
    fieldSchemaTableRef.current?.clearValidation();
  };

  const handleSecretFocus = (
    fieldPath: (string | number)[],
    event: React.FocusEvent<HTMLInputElement>,
  ) => {
    if (!currentRow) return;
    if (event.target.value === PASSWORD_PLACEHOLDER) {
      form.setFieldValue(fieldPath, "");
    }
  };

  const handleSecretBlur = (
    fieldPath: (string | number)[],
    event: React.FocusEvent<HTMLInputElement>,
  ) => {
    if (!currentRow) return;
    if (!event.target.value?.trim()) {
      form.setFieldValue(fieldPath, PASSWORD_PLACEHOLDER);
    }
  };

  const handlePasswordFocus = (event: React.FocusEvent<HTMLInputElement>) => {
    handleSecretFocus(["connection_config", "password"], event);
  };

  const handlePasswordBlur = (event: React.FocusEvent<HTMLInputElement>) => {
    handleSecretBlur(["connection_config", "password"], event);
  };

  const handleTestConnection = async () => {
    if (definitionReadOnly || !isPrometheusSource) return;

    try {
      setTestConnectionLoading(true);
      const validateFields: (string | (string | number)[])[] = [
        "source_type",
        ["connection_config", "url"],
      ];
      if (prometheusAuthType === "basic") {
        validateFields.push(
          ["connection_config", "username"],
          ["connection_config", "password"],
        );
      }
      if (prometheusAuthType === "bearer") {
        validateFields.push(["connection_config", "token"]);
      }
      await form.validateFields(validateFields);
      const values = form.getFieldsValue(true);
      const payload = buildConnectorPayload(values, {
        excelFileName: excelFile?.name,
        previewData,
        t,
      });

      if (currentRow) {
        await testDataSourceConnection(currentRow.id, {
          source_type: SOURCE_TYPE_PROMETHEUS,
          connection_config: payload.connection_config,
        });
      } else {
        await testDataSourceConnectionConfig({
          source_type: SOURCE_TYPE_PROMETHEUS,
          connection_config: payload.connection_config,
        });
      }
      message.success(t("dataSource.testConnectionSuccess"));
    } catch (error: any) {
      if (error?.errorFields) {
        scrollToFormError(error.errorFields, "process", "connect");
        return;
      }
      message.error(error?.message || t("dataSource.testConnectionFailed"));
    } finally {
      setTestConnectionLoading(false);
    }
  };

  const handleSourceTypeRadioChange = (nextSourceType: DataSourceSourceType) => {
    if (nextSourceType === SOURCE_TYPE_MYSQL) {
      form.setFieldValue(["connection_config", "port"], 3306);
    }
    if (nextSourceType === SOURCE_TYPE_POSTGRESQL) {
      form.setFieldValue(["connection_config", "port"], 5432);
    }
    if (nextSourceType === SOURCE_TYPE_REST_API) {
      form.setFieldsValue({
        connection_config: {
          ...form.getFieldValue("connection_config"),
          method: "GET",
          timeout: 10,
        },
      });
    }
    if (nextSourceType === SOURCE_TYPE_PROMETHEUS) {
      form.setFieldsValue({
        chart_type: [...PROMETHEUS_DEFAULT_CHART_TYPES],
        connection_config: {
          auth_type: "none",
          timeout_seconds: 30,
        },
        query_config: {
          query: "up",
          query_type: "range",
          time_range: 60,
          step: "1m",
          max_series: 20,
        },
      });
      setParams(createPrometheusDefaultParams(t));
    }
    if (
      nextSourceType !== SOURCE_TYPE_NATS &&
      nextSourceType !== SOURCE_TYPE_PROMETHEUS
    ) {
      form.setFieldValue("chart_type", [TABLE_CHART_TYPE]);
      setParams([]);
    }
  };

  const onFinish = async (values: any) => {
    if (readOnly) return;
    try {
      setLoading(true);

      if (isBuiltinDatasource(currentRow) && currentRow?.id) {
        await patchDataSource(currentRow.id, buildBuiltinGroupsPayload(values.groups));
        message.success(t("dataSource.updateDataSourceSuccess"));
        onClose();
        onSuccess && onSuccess();
        return;
      }

      if (isNatsSource) {
        if (!paramTableRef.current?.validate()) {
          scrollToFormError(undefined, "process", "connect");
          setLoading(false);
          return;
        }
      }

      const excelStatus = excelMaterialization?.status;
      const hasLegacyImported =
        Array.isArray(values.query_config?.imported_items) &&
        values.query_config.imported_items.length > 0;
      const isEditExcel = Boolean(currentRow?.id);
      const canSaveWithoutNewFile = canSaveExcelWithoutNewFile({
        isEdit: isEditExcel,
        hasLegacyImported,
        excelStatus,
        hasSavedSource: excelMaterialization?.has_saved_source,
      });

      if (isExcelSource && !excelFile && !canSaveWithoutNewFile) {
        setSourceInlineError(
          excelStatus === "needs_upload"
            ? t("dataSource.excelStatus.needsUpload")
            : t("dataSource.excelFileRequired"),
        );
        scrollToFormError(undefined, "process", "connect");
        setLoading(false);
        return;
      }

      if (schemaFields.length > 0) {
        if (!fieldSchemaTableRef.current?.validate()) {
          scrollToFormError(undefined, "process", "fields");
          setLoading(false);
          return;
        }
      }

      if (supportsTransform && transformEnabled) {
        await form.validateFields([["transform_config", "script"]]);
      }

      const fieldSchema = normalizeFieldSchema(schemaFields);
      const connectorPayload = buildConnectorPayload(values, {
        excelFileName: excelFile?.name,
        hasNewExcelFile: Boolean(excelFile),
        previewData,
        t,
      });

      const submitData = {
        ...connectorPayload,
        rest_api: isNatsSource ? values.rest_api : "",
        name: values.name.trim(),
        desc: values.desc ? values.desc.trim() : "",
        namespaces: isNatsSource ? values.namespaces || [] : [],
        tag: values.tag || [],
        chart_type: isNatsSource
          ? values.chart_type || []
          : isPrometheusSource
            ? values.chart_type || [...PROMETHEUS_DEFAULT_CHART_TYPES]
            : [TABLE_CHART_TYPE],
        groups: values.groups || [],
        field_schema: fieldSchema,
        params:
          isNatsSource || isPrometheusSource ? normalizeParams(params) : [],
      };

      const isEdit = Boolean(currentRow?.id);
      let datasourceId = currentRow?.id || undefined;
      const isExcelCreate = isExcelSource && !isEdit;

      if (isEdit && datasourceId) {
        await updateDataSource(datasourceId, submitData);
      } else {
        const created = await createDataSource(submitData);
        datasourceId = created?.id;
        if (!datasourceId) {
          throw new Error(t("dataSource.operationFailed"));
        }
      }

      if (isExcelSource && excelFile && datasourceId) {
        try {
          const formData = new FormData();
          formData.append("file", excelFile);
          formData.append(
            "transform_config",
            JSON.stringify(normalizeTransformConfig(values.transform_config)),
          );
          formData.append("sync", "1");
          formData.append("discard_on_fail", isExcelCreate ? "1" : "0");
          await submitExcelMaterialization(datasourceId, formData);
          message.success(
            isExcelCreate
              ? t("dataSource.excelStatus.createImportSuccess")
              : t("dataSource.excelStatus.saveAndSubmitSuccess"),
          );
        } catch {
          if (isExcelCreate && datasourceId) {
            try {
              await deleteDataSource(datasourceId, {
                suppressErrorNotification: true,
              });
            } catch {
              /* 可能已被服务端删除 */
            }
          } else if (datasourceId) {
            try {
              await refreshExcelMaterialization(datasourceId);
            } catch {
              /* ignore */
            }
            message.warning(t("dataSource.excelStatus.updateProcessFailed"));
          }
          setLoading(false);
          return;
        }
      } else {
        message.success(
          isEdit
            ? t("dataSource.updateDataSourceSuccess")
            : t("dataSource.createDataSourceSuccess"),
        );
      }

      onClose();
      onSuccess && onSuccess();
    } catch (error: any) {
      if (error?.errorFields) {
        scrollToFormError(error.errorFields);
        setLoading(false);
        return;
      }
      message.error(error.message || t("dataSource.operationFailed"));
    } finally {
      setLoading(false);
    }
  };

  const previewActions = definitionReadOnly ? null : (
    <div
      className={`flex items-center justify-end gap-3${supportsTransform ? " mb-3" : ""}`}
    >
      {previewData?.fields?.length ? (
        <span className="inline-flex items-center gap-1">
          <Button
            type="link"
            size="small"
            onClick={handleApplyPreviewFields}
            className="!px-0"
          >
            {t("dataSource.applyPreviewFields")}
          </Button>
          <Tooltip
            placement="top"
            overlayStyle={{ maxWidth: 420 }}
            overlayInnerStyle={{ maxWidth: 420 }}
            title={t("dataSource.applyPreviewFieldsTooltip")}
          >
            <QuestionCircleOutlined
              aria-label={t("dataSource.applyPreviewFieldsTooltip")}
              className="cursor-help text-[14px] text-[var(--color-text-3)]"
            />
          </Tooltip>
        </span>
      ) : null}
      <Button
        type="primary"
        size="small"
        loading={previewLoading}
        onClick={handlePreview}
      >
        {t("dataSource.samplePreview")}
      </Button>
    </div>
  );

  return (
    <>
    <Drawer
      title={
        mode === "view" && currentRow
          ? `${t("common.view")}${t("dataSource.title")} - ${currentRow.name}`
          : currentRow
            ? `${t("common.edit")}${t("dataSource.title")} - ${currentRow.name}`
            : `${t("common.add")}${t("dataSource.title")}`
      }
      placement="right"
      width={900}
      open={open}
      maskClosable={false}
      onClose={handleClose}
      styles={{
        header: {
          padding: "14px 20px",
          background: "var(--color-bg-2)",
        },
        body: {
          padding: 0,
          overflow: "hidden",
        },
        footer: {
          padding: "12px 20px",
          background: "var(--color-bg)",
        },
      }}
      footer={
        <div className="text-right">
          {canSaveDatasource ? (
            <Button
              type="primary"
              loading={loading}
              onClick={() => {
                if (isBuiltinDatasource(currentRow)) {
                  form
                    .validateFields(["groups"])
                    .then((values) => {
                      void onFinish(values);
                    })
                    .catch(() => undefined);
                  return;
                }
                form.submit();
              }}
            >
              {t("common.confirm")}
            </Button>
          ) : null}
          <Button
            className={canSaveDatasource ? "ml-2" : undefined}
            onClick={handleClose}
          >
            {readOnly ? t("common.close") : t("common.cancel")}
          </Button>
        </div>
      }
    >
      <Form
        form={form}
        layout="vertical"
        onFinish={onFinish}
        scrollToFirstError={{ behavior: "smooth", block: "center" }}
        className="ds-operate-form flex h-full min-h-0 flex-col"
        onValuesChange={(changed) => {
          if (!supportsTransform && !isExcelSource) return;
          const keys = Object.keys(changed);
          if (
            keys.some((key) =>
              [
                "connection",
                "connection_mode",
                "connection_config",
                "connection_overrides",
                "query_config",
              ].includes(key),
            )
          ) {
            clearPreviewState();
          }
        }}
      >
        <div
          ref={formScrollRef}
          className="min-h-0 flex-1 overflow-y-auto bg-[var(--color-bg)] px-6 pb-4 pt-5"
        >
        <FormSection
          id="basic"
          step={1}
          title={t("dataSource.sections.basic")}
        >
          <DatasourceBasicFields
            definitionReadOnly={definitionReadOnly}
            groupsReadOnly={groupsReadOnly}
            currentRow={currentRow}
            sourceTypeOptions={sourceTypeOptions}
            chartTypeOptions={chartTypeOptions}
            isNatsSource={isNatsSource}
            namespacesLoading={namespacesLoading}
            namespaceList={namespaceList}
            tagsLoading={tagsLoading}
            tagList={tagList}
            onSourceTypeChange={handleSourceTypeRadioChange}
          />
        </FormSection>

        <FormSection
          id="process"
          step={2}
          title={t("dataSource.sections.process")}
        >
        <FormSubsection
          id="connect"
          title={connectSubsectionTitle}
          extra={
            isNatsSource && !definitionReadOnly ? (
              <Button
                type="link"
                size="small"
                className="!px-1"
                onClick={() => setParams([...params, createDefaultParam()])}
              >
                {t("dataSource.addParam")}
              </Button>
            ) : null
          }
        >
        {isRestApiSource && (
          <RestApiConnectFields
            definitionReadOnly={definitionReadOnly}
            useSharedConnection={useSharedConnection}
            connectionList={connectionList}
            extractButton={extractToConnectionLibraryButton}
          />
        )}
        {isDatabaseSource && (
          <DatabaseConnectFields
            definitionReadOnly={definitionReadOnly}
            useSharedConnection={useSharedConnection}
            connectionList={connectionList}
            extractButton={extractToConnectionLibraryButton}
            onPasswordFocus={handlePasswordFocus}
            onPasswordBlur={handlePasswordBlur}
          />
        )}
        {isPrometheusSource && (
          <PrometheusConnectFields
            definitionReadOnly={definitionReadOnly}
            prometheusAuthType={prometheusAuthType}
            prometheusQueryType={prometheusQueryType}
            testConnectionLoading={testConnectionLoading}
            onTestConnection={() => {
              void handleTestConnection();
            }}
            onPasswordFocus={handlePasswordFocus}
            onPasswordBlur={handlePasswordBlur}
            onSecretFocus={handleSecretFocus}
            onSecretBlur={handleSecretBlur}
          />
        )}
        {isExcelSource && (
          <ExcelConnectFields
            definitionReadOnly={definitionReadOnly}
            sourceInlineError={sourceInlineError}
            excelFileList={excelFileList}
            excelMaterialization={excelMaterialization}
            excelRetryLoading={excelRetryLoading}
            pendingNewFile={Boolean(excelFile)}
            onFile={(file) => {
              setExcelFile(file);
              setExcelFileList([file]);
              setSourceInlineError(null);
              clearPreviewState();
              setSchemaFields([]);
            }}
            onRemove={() => {
              setExcelFile(null);
              setExcelFileList([]);
              clearPreviewState();
              setSchemaFields([]);
            }}
            onRetry={
              excelMaterialization?.can_retry
                ? handleRetryExcelMaterialization
                : undefined
            }
          />
        )}
        {isNatsSource && (
          <ParamTable
            ref={paramTableRef}
            params={params}
            onChange={setParams}
            readOnly={definitionReadOnly}
          />
        )}
        </FormSubsection>

        {!isNatsSource && (
          <FormSubsection
            id="preview"
            title={previewSubsectionTitle}
            extra={supportsTransform ? null : previewActions}
          >
            {supportsTransform ? (
              <TransformScriptPanel
                enabled={transformEnabled}
                readOnly={definitionReadOnly}
                onEnabledChange={clearPreviewState}
                onScriptChange={clearPreviewState}
              />
            ) : null}
            {supportsTransform ? previewActions : null}
            <PreviewPanel
              previewData={previewData}
              rawPreviewData={rawPreviewData}
              transformPreviewError={transformPreviewError}
              previewActionError={previewInlineError}
              showTransformTabs={supportsTransform && transformEnabled}
            />
          </FormSubsection>
        )}
        {showSchemaConfig && (
          <FormSubsection
            id="fields"
            title={t("dataSource.sections.fields")}
            titleExtra={
              <Tooltip
                title={t("dataSource.schemaOptionalAutoGenTip")}
                overlayStyle={{ maxWidth: 420 }}
                overlayInnerStyle={{ maxWidth: 420 }}
              >
                <QuestionCircleOutlined
                  aria-label={t("dataSource.sections.fields")}
                  className="cursor-help text-[14px] text-[var(--color-text-3)]"
                />
              </Tooltip>
            }
            extra={
              definitionReadOnly ? null : (
                <Button
                  type="link"
                  size="small"
                  className="!px-1"
                  onClick={() =>
                    setSchemaFields([
                      ...schemaFields,
                      createDefaultSchemaField(),
                    ])
                  }
                >
                  {t("dataSource.addField")}
                </Button>
              )
            }
          >
            <FieldSchemaTable
              ref={fieldSchemaTableRef}
              schemaFields={schemaFields}
              onChange={setSchemaFields}
              readOnly={definitionReadOnly}
            />
          </FormSubsection>
        )}
        </FormSection>
        </div>
      </Form>
    </Drawer>
    <ExtractConnectionModal
      open={extractModalOpen}
      loading={extractLoading}
      form={extractForm}
      onCancel={() => {
        if (extractLoading) return;
        setExtractModalOpen(false);
        extractForm.resetFields();
      }}
      onOk={() => {
        void handleExtractToConnectionLibrary();
      }}
    />
    </>
  );
};

export default OperateModal;
