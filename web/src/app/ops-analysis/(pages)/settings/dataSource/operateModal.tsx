"use client";

import React, { useEffect } from "react";
import GroupTreeSelect from "@/components/group-tree-select";
import { v4 as uuidv4 } from "uuid";
import { getChartTypeList } from "@/app/ops-analysis/constants/common";
import { UploadOutlined, QuestionCircleOutlined } from "@ant-design/icons";
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
  DatasourceItem,
  OperateModalProps,
  ParamItem,
} from "@/app/ops-analysis/types/dataSource";
import { DataConnectionItem } from "@/app/ops-analysis/types/dataConnection";
import { NamespaceItem, TagItem } from "@/app/ops-analysis/types/namespace";
import {
  Drawer,
  Form,
  Input,
  InputNumber,
  Select,
  Button,
  Upload,
  Checkbox,
  Spin,
  message,
  Modal,
  Radio,
  Collapse,
  Tooltip,
} from "antd";
import type { UploadFile } from "antd/es/upload/interface";
import ParamTable, { ParamTableRef } from "./paramTable";
import FieldSchemaTable, { FieldSchemaTableRef } from "./fieldSchemaTable";
import PreviewPanel from "./previewPanel";
import TransformScriptPanel from "@/app/ops-analysis/components/ops-analysis-transform-script-panel";
import ExcelMaterializationStatus, {
  ExcelMaterializationState,
} from "@/app/ops-analysis/components/ops-analysis-excel-materialization-status";
import { ensurePrometheusQueryRequired } from "@/app/ops-analysis/utils/dataSourceParamContract";
import {
  buildConnectorPayload,
  buildConnectionLibraryCreateFromDatasourceForm,
  canExtractConnectionFromDatasourceForm,
  createDefaultParam,
  createDefaultSchemaField,
  createDefaultTransformConfig,
  createPrometheusDefaultParams,
  formatJsonText,
  normalizeFieldSchema,
  normalizeParams,
  normalizeTransformConfig,
  PASSWORD_PLACEHOLDER,
  prometheusTimeRangeToMinutes,
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

type FormSectionId = "basic" | "process";
type FormSubsectionId = "connect" | "preview" | "fields";

function resolveSubsectionForFieldName(
  name: string | number | (string | number)[],
): FormSubsectionId | null {
  const root = Array.isArray(name) ? name[0] : name;
  const key = String(root || "");
  if (
    key === "transform_config" ||
    key === "excel_file" ||
    key.startsWith("transform")
  ) {
    return "preview";
  }
  if (key === "field_schema" || key === "schema") {
    return "fields";
  }
  if (
    key === "connection" ||
    key === "connection_mode" ||
    key === "connection_config" ||
    key === "connection_overrides" ||
    key === "query_config" ||
    key === "params"
  ) {
    return "connect";
  }
  return null;
}

function resolveSectionForFieldName(
  name: string | number | (string | number)[],
): FormSectionId {
  return resolveSubsectionForFieldName(name) ? "process" : "basic";
}

function fieldDomId(name: string | number | (string | number)[]): string {
  return (Array.isArray(name) ? name : [name]).map(String).join("_");
}

const FormSection: React.FC<{
  id: FormSectionId;
  step: number;
  title: string;
  titleExtra?: React.ReactNode;
  extra?: React.ReactNode;
  children: React.ReactNode;
}> = ({ id, step, title, titleExtra, extra, children }) => (
  <section
    id={`ds-form-section-${id}`}
    data-form-section={id}
    className="scroll-mt-3 [&:not(:last-child)]:mb-7 [&>.ant-form-item:last-child]:mb-0 [&>.ant-form-item]:mb-5"
  >
    <div className="mb-4 flex min-h-[28px] items-center justify-between gap-3">
      <div className="flex min-w-0 items-center gap-2">
        <div className="inline-flex items-center gap-1.5">
          <span
            aria-hidden="true"
            className="inline-grid h-5 w-5 shrink-0 place-items-center rounded-full bg-[var(--color-primary)] text-[11px] font-semibold text-white"
          >
            {step}
          </span>
          <h3 className="m-0 text-[13px] font-semibold leading-5 text-[var(--color-primary)]">
            {title}
          </h3>
        </div>
        {titleExtra}
      </div>
      {extra ? <div className="shrink-0">{extra}</div> : null}
    </div>
    {children}
  </section>
);

const FormSubsection: React.FC<{
  id: FormSubsectionId;
  title: string;
  titleExtra?: React.ReactNode;
  extra?: React.ReactNode;
  children: React.ReactNode;
}> = ({ id, title, titleExtra, extra, children }) => (
  <div
    id={`ds-form-subsection-${id}`}
    data-form-subsection={id}
    className="scroll-mt-3 [&:not(:last-child)]:mb-6 [&>.ant-form-item:last-child]:mb-0 [&>.ant-form-item]:mb-5"
  >
    <div className="mb-3 flex min-h-[22px] items-center justify-between gap-3">
      <div className="flex min-w-0 items-center gap-1.5">
        <h4 className="m-0 text-sm font-semibold leading-[22px] text-[var(--color-text-1)]">
          {title}
        </h4>
        {titleExtra}
      </div>
      {extra ? <div className="shrink-0">{extra}</div> : null}
    </div>
    {children}
  </div>
);

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
  const { selectedGroup } = useUserInfoContext();
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

  const isNatsSource = sourceType === SOURCE_TYPE_NATS;
  const isRestApiSource = sourceType === SOURCE_TYPE_REST_API;
  const isPrometheusSource = sourceType === SOURCE_TYPE_PROMETHEUS;
  const isDatabaseSource =
    sourceType === SOURCE_TYPE_MYSQL || sourceType === SOURCE_TYPE_POSTGRESQL;
  const isExcelSource = sourceType === SOURCE_TYPE_EXCEL;
  const supportsTransform = isRestApiSource || isExcelSource;
  const supportsSharedConnection =
    isDatabaseSource || isRestApiSource;
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

      if (currentRow?.id) {
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
    currentRow?.id,
    extractDataSourceConnection,
    extractForm,
    form,
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
    !useSharedConnection && !readOnly ? (
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

    const hydrateForm = (row: DatasourceItem | undefined) => {
      if (cancelled) return;

      form.resetFields();
      setSchemaFields([]);
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

      if (!row) {
        setParams([]);
        form.setFieldsValue({
          source_type: SOURCE_TYPE_NATS,
          connection_mode: "connection",
          connection_config: {
            method: "GET",
            timeout: 10,
          },
          query_config: {},
          transform_config: createDefaultTransformConfig(),
        });
        if (selectedGroup) {
          form.setFieldValue("groups", [selectedGroup.id]);
        }
        return;
      }

      const connectionConfig = row.connection_config || {};
      const queryConfig = row.query_config || {};
      const rowSourceType = row.source_type || SOURCE_TYPE_NATS;
      const hasConnection = !!(row.connection || row.connection_id);
      const prometheusConnectionConfig = { ...connectionConfig };
      if (rowSourceType === SOURCE_TYPE_PROMETHEUS) {
        if (prometheusConnectionConfig.password) {
          prometheusConnectionConfig.password = PASSWORD_PLACEHOLDER;
        }
        if (prometheusConnectionConfig.token) {
          prometheusConnectionConfig.token = PASSWORD_PLACEHOLDER;
        }
      }
      const formValues = {
        ...row,
        source_type: rowSourceType,
        connection_mode: hasConnection ? "connection" : "inline",
        connection: row.connection || row.connection_id || undefined,
        connection_overrides: row.connection_overrides || {},
        namespaces: row.namespaces || [],
        groups: row.groups || [],
        chart_type:
          rowSourceType === SOURCE_TYPE_NATS
            ? row.chart_type || []
            : rowSourceType === SOURCE_TYPE_PROMETHEUS
              ? row.chart_type?.length
                ? row.chart_type
                : [...PROMETHEUS_DEFAULT_CHART_TYPES]
              : [TABLE_CHART_TYPE],
        connection_config: {
          ...prometheusConnectionConfig,
          headersText: formatJsonText(connectionConfig.headers),
          password: connectionConfig.password
            ? PASSWORD_PLACEHOLDER
            : connectionConfig.password,
        },
        query_config: {
          ...queryConfig,
          paramsText: formatJsonText(queryConfig.params),
          bodyText: formatJsonText(queryConfig.body),
          ...(rowSourceType === SOURCE_TYPE_PROMETHEUS
            ? {
              time_range: prometheusTimeRangeToMinutes(queryConfig.time_range),
              max_series: queryConfig.max_series ?? 20,
            }
            : {}),
        },
        transform_config: createDefaultTransformConfig(row.transform_config),
      };
      form.setFieldsValue(formValues);

      if (
        row.source_type === SOURCE_TYPE_EXCEL &&
        Array.isArray(queryConfig.imported_items)
      ) {
        setPreviewData({
          items: queryConfig.imported_items,
          count:
            Number(queryConfig.imported_count) ||
            queryConfig.imported_items.length,
          fields: Array.isArray(queryConfig.imported_fields)
            ? queryConfig.imported_fields
            : [],
        });
      }

      if (Array.isArray(row.field_schema)) {
        setSchemaFields(
          row.field_schema.map((field) => ({
            ...field,
            id: uuidv4(),
          })),
        );
      }

      const hasValidParams =
        row.params && Array.isArray(row.params) && row.params.length > 0;

      if (hasValidParams) {
        const restoredParams = row.params.map((param: any) => ({
          ...param,
          type: param.type || "string",
          filterType:
            param.filterType ||
            (param.type === "timeRange" ? "filter" : "fixed"),
          id: param.id || uuidv4(),
        }));
        setParams(
          rowSourceType === SOURCE_TYPE_PROMETHEUS
            ? ensurePrometheusQueryRequired(restoredParams)
            : restoredParams,
        );
      } else if (rowSourceType === SOURCE_TYPE_PROMETHEUS) {
        setParams(createPrometheusDefaultParams());
      } else {
        setParams([]);
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
        setParams(createPrometheusDefaultParams());
      } else if (sourceType !== SOURCE_TYPE_NATS) {
        form.setFieldValue("chart_type", [TABLE_CHART_TYPE]);
        setParams([]);
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

  const getPreviewFieldNames = (): (string | (string | number)[])[] => {
    if (isRestApiSource) {
      if (useSharedConnection) {
        return ["source_type", "connection", ["connection_config", "method"]];
      }
      return [
        "source_type",
        ["connection_config", "url"],
        ["connection_config", "method"],
      ];
    }
    if (isDatabaseSource) {
      if (useSharedConnection) {
        return ["source_type", "connection"];
      }
      return [
        "source_type",
        ["connection_config", "host"],
        ["connection_config", "port"],
        ["connection_config", "database"],
        ["connection_config", "username"],
        ["connection_config", "password"],
      ];
    }
    if (isPrometheusSource) {
      const fieldNames: (string | (string | number)[])[] = [
        "source_type",
        ["connection_config", "url"],
        ["query_config", "query"],
        ["query_config", "query_type"],
      ];
      if (prometheusQueryType === "range") {
        fieldNames.push(["query_config", "time_range"]);
        fieldNames.push(["query_config", "step"]);
      }
      return fieldNames;
    }
    return ["source_type"];
  };

  const handlePreview = async () => {
    if (isNatsSource) return;

    try {
      setPreviewLoading(true);
      setTransformPreviewError(null);
      const previewFields = getPreviewFieldNames();
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
    if (!currentRow || readOnly) return;
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
    if (readOnly || !isPrometheusSource) return;

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

  const onFinish = async (values: any) => {
    if (readOnly) return;
    try {
      setLoading(true);

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
      // 新建必须带文件；编辑仅在已有可运行结果/旧成功/已存原文件时可无新文件保存。
      const canSaveWithoutNewFile =
        isEditExcel &&
        (hasLegacyImported ||
          excelStatus === "ready" ||
          excelStatus === "processing" ||
          excelStatus === "update_failed_using_previous" ||
          (excelStatus === "failed" &&
            Boolean(excelMaterialization?.has_saved_source)));

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

      // 检查表格字段配置
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
          // 新建失败清盘，避免列表残留半成品；编辑失败保留旧成功结果。
          formData.append("discard_on_fail", isExcelCreate ? "1" : "0");
          await submitExcelMaterialization(datasourceId, formData);
          message.success(
            isExcelCreate
              ? t("dataSource.excelStatus.createImportSuccess")
              : t("dataSource.excelStatus.saveAndSubmitSuccess"),
          );
        } catch {
          if (isExcelCreate && datasourceId) {
            // 服务端 discard_on_fail 为主；网络中断等残留再由前端补偿删除。
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

  const previewActions = readOnly ? null : (
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
          {readOnly ? null : (
            <Button
              type="primary"
              loading={loading}
              onClick={() => form.submit()}
            >
              {t("common.confirm")}
            </Button>
          )}
          <Button
            className={readOnly ? undefined : "ml-2"}
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
        disabled={readOnly}
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
        <Form.Item
          name="source_type"
          label={t("dataSource.sourceType")}
          rules={[{ required: true, message: t("common.inputMsg") }]}
        >
          <Radio.Group
            optionType="button"
            buttonStyle="solid"
            options={sourceTypeOptions}
            onChange={(event) => {
              const nextSourceType = event.target.value as DataSourceSourceType;
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
                setParams(createPrometheusDefaultParams());
              }
              if (
                nextSourceType !== SOURCE_TYPE_NATS &&
                nextSourceType !== SOURCE_TYPE_PROMETHEUS
              ) {
                form.setFieldValue("chart_type", [TABLE_CHART_TYPE]);
                setParams([]);
              }
            }}
          />
        </Form.Item>

        <Form.Item
          name="name"
          label={t("dataSource.name")}
          rules={[{ required: true, message: t("common.inputMsg") }]}
        >
          <Input placeholder={t("common.inputMsg")} />
        </Form.Item>
        {isNatsSource && (
          <>
            <Form.Item
              name="rest_api"
              label="NATS"
              rules={[{ required: true, message: t("common.inputMsg") }]}
            >
              <Input placeholder={t("common.inputMsg")} />
            </Form.Item>
            <Form.Item
              name="namespaces"
              label={t("namespace.title")}
              rules={[
                {
                  required: true,
                  type: "array",
                  min: 1,
                  message: t("common.selectMsg"),
                },
              ]}
            >
              {namespacesLoading ? (
                <div className="py-2 text-center">
                  <Spin size="small" />
                </div>
              ) : namespaceList.length === 0 ? (
                <div className="text-[13px] text-[var(--color-text-4)]">
                  {t("common.noData")}
                </div>
              ) : (
                <Checkbox.Group className="flex flex-wrap gap-x-4 gap-y-2 pt-1">
                  {namespaceList.map((ns: NamespaceItem) => (
                    <Checkbox
                      key={ns.id}
                      value={ns.id}
                      className="!ml-0 flex min-w-0 items-center"
                    >
                      <span
                        className="inline-block max-w-[180px] truncate align-bottom"
                        title={ns.name}
                      >
                        {ns.name}
                      </span>
                    </Checkbox>
                  ))}
                </Checkbox.Group>
              )}
            </Form.Item>
          </>
        )}
        <Form.Item
          name="tag"
          label={t("dataSource.tag")}
          rules={[
            {
              required: true,
              type: "array",
              min: 1,
              message: t("common.selectMsg"),
            },
          ]}
        >
          {tagsLoading ? (
            <div className="py-2 text-center">
              <Spin size="small" />
            </div>
          ) : tagList.length === 0 ? (
            <div className="text-[13px] text-[var(--color-text-4)]">
              {t("common.noData")}
            </div>
          ) : (
            <Checkbox.Group
              options={tagList.map((tag: TagItem) => ({
                label: tag.name,
                value: tag.id,
              }))}
            />
          )}
        </Form.Item>
        <Form.Item
          name="chart_type"
          label={t("dataSource.chartType")}
          rules={[
            {
              required: true,
              type: "array",
              min: 1,
              message: t("common.selectMsg"),
            },
          ]}
        >
          <Select
            mode="multiple"
            allowClear
            showSearch
            optionFilterProp="label"
            placeholder={t("common.selectMsg")}
            options={chartTypeOptions}
            disabled={readOnly}
          />
        </Form.Item>
        <Form.Item
          name="groups"
          label={t("common.group")}
          rules={[
            {
              required: true,
              message: `${t("common.selectMsg")}${t("common.group")}`,
            },
          ]}
        >
          <GroupTreeSelect
            placeholder={`${t("common.selectMsg")}${t("common.group")}`}
            multiple={true}
            mode="ownership"
            disabled={readOnly}
          />
        </Form.Item>
        <Form.Item name="desc" label={t("dataSource.describe")}>
          <Input.TextArea
            rows={3}
            placeholder={`${t("common.inputMsg")} ${t("dataSource.describe")}`}
          />
        </Form.Item>
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
            isNatsSource && !readOnly ? (
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
          <Form.Item>
            <div className="rounded-lg border border-[var(--color-border-1)] bg-[var(--color-fill-2)] px-4 pb-1 pt-4">
              <Form.Item
                name="connection_mode"
                label={t("dataConnection.title")}
                className="!mb-2"
                initialValue="connection"
              >
                <Radio.Group disabled={readOnly}>
                  <Radio.Button value="connection">
                    {t("dataConnection.useConnection")}
                  </Radio.Button>
                  <Radio.Button value="inline">
                    {t("dataConnection.useInline")}
                  </Radio.Button>
                </Radio.Group>
              </Form.Item>
              {useSharedConnection ? (
                <>
                  <Form.Item
                    name="connection"
                    label={t("dataConnection.selectConnection")}
                    className="!mb-2"
                    rules={[{ required: true, message: t("common.selectMsg") }]}
                  >
                    <Select
                      disabled={readOnly}
                      placeholder={t("common.selectMsg")}
                      options={connectionList.map((item) => ({
                        label: `${item.name}${item.endpoint_summary ? ` (${item.endpoint_summary})` : ""}`,
                        value: item.id,
                      }))}
                      showSearch
                      optionFilterProp="label"
                    />
                  </Form.Item>
                  <Form.Item
                    name={["connection_overrides", "path"]}
                    label={t("dataConnection.relativePath")}
                    className="!mb-2"
                  >
                    <Input disabled={readOnly} placeholder="/api/v1/items" />
                  </Form.Item>
                </>
              ) : (
                <Form.Item
                  name={["connection_config", "url"]}
                  label={t("dataSource.url")}
                  className="!mb-2"
                  rules={[{ required: true, message: t("common.inputMsg") }]}
                >
                  <Input placeholder="https://example.com/api" disabled={readOnly} />
                </Form.Item>
              )}
              <div className="grid grid-cols-2 gap-x-3">
                <Form.Item
                  name={["connection_config", "method"]}
                  label={t("dataSource.method")}
                  className="!mb-2"
                  initialValue="GET"
                >
                  <Select
                    disabled={readOnly}
                    options={[
                      { label: "GET", value: "GET" },
                      { label: "POST", value: "POST" },
                    ]}
                  />
                </Form.Item>
                <Form.Item
                  name={["connection_config", "timeout"]}
                  label={t("dataSource.timeout")}
                  className="!mb-2"
                  initialValue={10}
                >
                  <InputNumber min={1} max={30} className="w-full" disabled={readOnly} />
                </Form.Item>
                <Form.Item
                  name={["query_config", "response_path"]}
                  label={t("dataSource.responsePath")}
                  className="!mb-2"
                >
                  <Input placeholder="data.items" disabled={readOnly} />
                </Form.Item>
              </div>
              {!useSharedConnection && (
                <Form.Item
                  name={["connection_config", "headersText"]}
                  label={t("dataSource.headers")}
                  className="!mb-2"
                >
                  <Input.TextArea
                    rows={3}
                    placeholder='{"Authorization":"Bearer ..."}'
                    disabled={readOnly}
                  />
                </Form.Item>
              )}
              <Form.Item
                name={["query_config", "paramsText"]}
                label={t("dataSource.queryParams")}
                className="!mb-2"
              >
                <Input.TextArea rows={3} placeholder='{"page":1}' disabled={readOnly} />
              </Form.Item>
              <Form.Item
                name={["query_config", "bodyText"]}
                label={t("dataSource.requestBody")}
                className="!mb-2"
              >
                <Input.TextArea rows={3} placeholder='{"limit":50}' disabled={readOnly} />
              </Form.Item>
              {extractToConnectionLibraryButton}
            </div>
          </Form.Item>
        )}
        {isDatabaseSource && (
          <Form.Item>
            <div className="rounded-lg border border-[var(--color-border-1)] bg-[var(--color-fill-2)] px-4 pb-1 pt-4">
              <Form.Item
                name="connection_mode"
                label={t("dataConnection.title")}
                className="!mb-2"
                initialValue="connection"
              >
                <Radio.Group disabled={readOnly}>
                  <Radio.Button value="connection">
                    {t("dataConnection.useConnection")}
                  </Radio.Button>
                  <Radio.Button value="inline">
                    {t("dataConnection.useInline")}
                  </Radio.Button>
                </Radio.Group>
              </Form.Item>
              {useSharedConnection ? (
                <>
                  <Form.Item
                    name="connection"
                    label={t("dataConnection.selectConnection")}
                    className="!mb-2"
                    rules={[{ required: true, message: t("common.selectMsg") }]}
                  >
                    <Select
                      disabled={readOnly}
                      placeholder={t("common.selectMsg")}
                      options={connectionList.map((item) => ({
                        label: `${item.name}${item.endpoint_summary ? ` (${item.endpoint_summary})` : ""}`,
                        value: item.id,
                      }))}
                      showSearch
                      optionFilterProp="label"
                    />
                  </Form.Item>
                  <Form.Item
                    name={["connection_overrides", "database"]}
                    label={t("dataConnection.overrideDatabase")}
                    className="!mb-2"
                  >
                    <Input disabled={readOnly} placeholder={t("dataSource.database")} />
                  </Form.Item>
                </>
              ) : (
                <div className="grid grid-cols-2 gap-x-3">
                <Form.Item
                  name={["connection_config", "host"]}
                  label={t("dataSource.host")}
                  className="!mb-2"
                  rules={[{ required: true, message: t("common.inputMsg") }]}
                >
                  <Input placeholder="127.0.0.1" disabled={readOnly} />
                </Form.Item>
                <Form.Item
                  name={["connection_config", "port"]}
                  label={t("dataSource.port")}
                  className="!mb-2"
                  rules={[{ required: true, message: t("common.inputMsg") }]}
                >
                  <InputNumber min={1} max={65535} className="w-full" disabled={readOnly} />
                </Form.Item>
                <Form.Item
                  name={["connection_config", "database"]}
                  label={t("dataSource.database")}
                  className="!mb-2"
                  rules={[{ required: true, message: t("common.inputMsg") }]}
                >
                  <Input disabled={readOnly} />
                </Form.Item>
                <Form.Item
                  name={["connection_config", "username"]}
                  label={t("dataSource.username")}
                  className="!mb-2"
                  rules={[{ required: true, message: t("common.inputMsg") }]}
                >
                  <Input disabled={readOnly} />
                </Form.Item>
                <Form.Item
                  name={["connection_config", "password"]}
                  label={t("dataSource.password")}
                  className="!mb-2"
                  rules={[{ required: true, message: t("common.inputMsg") }]}
                >
                  <Input.Password
                    autoComplete="new-password"
                    onFocus={handlePasswordFocus}
                    onBlur={handlePasswordBlur}
                    disabled={readOnly}
                  />
                </Form.Item>
                </div>
              )}
              <div className="grid grid-cols-2 gap-x-3">
                <Form.Item
                  name={["query_config", "table"]}
                  label={t("dataSource.tableName")}
                  className="!mb-2"
                >
                  <Input disabled={readOnly} />
                </Form.Item>
              </div>
              <Form.Item
                name={["query_config", "sql"]}
                label={t("dataSource.sql")}
                className="!mb-2"
              >
                <Input.TextArea
                  rows={3}
                  placeholder="SELECT * FROM table_name"
                  disabled={readOnly}
                />
              </Form.Item>
              {extractToConnectionLibraryButton}
            </div>
          </Form.Item>
        )}
        {isPrometheusSource && (
          <Form.Item>
            <div className="rounded-lg border border-[var(--color-border-1)] bg-[var(--color-fill-2)] px-4 pb-1 pt-4">
              <div className="grid grid-cols-2 gap-x-3">
                <Form.Item
                  name={["connection_config", "url"]}
                  label={t("dataSource.url")}
                  className="!mb-2"
                  rules={[{ required: true, message: t("common.inputMsg") }]}
                >
                  <Input placeholder="https://prometheus.example.com" />
                </Form.Item>
                <Form.Item
                  name={["connection_config", "auth_type"]}
                  label={t("dataSource.authType")}
                  className="!mb-2"
                  initialValue="none"
                >
                  <Select
                    options={[
                      { label: t("dataSource.authTypes.none"), value: "none" },
                      { label: t("dataSource.authTypes.basic"), value: "basic" },
                      { label: t("dataSource.authTypes.bearer"), value: "bearer" },
                    ]}
                  />
                </Form.Item>
                {prometheusAuthType === "basic" && (
                  <>
                    <Form.Item
                      name={["connection_config", "username"]}
                      label={t("dataSource.username")}
                      className="!mb-2"
                      rules={[
                        { required: true, message: t("common.inputMsg") },
                      ]}
                    >
                      <Input />
                    </Form.Item>
                    <Form.Item
                      name={["connection_config", "password"]}
                      label={t("dataSource.password")}
                      className="!mb-2"
                      rules={[
                        { required: true, message: t("common.inputMsg") },
                      ]}
                    >
                      <Input.Password
                        autoComplete="new-password"
                        onFocus={handlePasswordFocus}
                        onBlur={handlePasswordBlur}
                      />
                    </Form.Item>
                  </>
                )}
                {prometheusAuthType === "bearer" && (
                  <Form.Item
                    name={["connection_config", "token"]}
                    label={t("dataSource.token")}
                    className="!mb-2"
                    rules={[{ required: true, message: t("common.inputMsg") }]}
                  >
                    <Input.Password
                      autoComplete="new-password"
                      onFocus={(event) =>
                        handleSecretFocus(
                          ["connection_config", "token"],
                          event,
                        )
                      }
                      onBlur={(event) =>
                        handleSecretBlur(["connection_config", "token"], event)
                      }
                    />
                  </Form.Item>
                )}
                <Form.Item
                  name={["connection_config", "timeout_seconds"]}
                  label={t("dataSource.timeout")}
                  className="!mb-2"
                  initialValue={30}
                >
                  <InputNumber min={1} max={120} className="w-full" />
                </Form.Item>
              </div>
              {readOnly ? null : (
                <div className="mb-3 text-right">
                  <Button
                    size="small"
                    loading={testConnectionLoading}
                    onClick={handleTestConnection}
                  >
                    {t("dataSource.testConnection")}
                  </Button>
                </div>
              )}
              <Collapse
                ghost
                items={[
                  {
                    key: "prometheus-preview-query",
                    label: t("dataSource.prometheusPreviewQuery"),
                    children: (
                      <div className="grid grid-cols-2 gap-x-3">
                        <Form.Item
                          name={["query_config", "query"]}
                          label={t("dataSource.promql")}
                          className="!mb-2 col-span-2"
                          rules={[
                            { required: true, message: t("common.inputMsg") },
                          ]}
                        >
                          <Input.TextArea
                            rows={2}
                            placeholder="up"
                          />
                        </Form.Item>
                        <Form.Item
                          name={["query_config", "query_type"]}
                          label={t("dataSource.queryType")}
                          className="!mb-2"
                          initialValue="range"
                        >
                          <Select
                            options={[
                              { label: "range", value: "range" },
                              { label: "instant", value: "instant" },
                            ]}
                          />
                        </Form.Item>
                        {prometheusQueryType === "range" && (
                          <>
                            <Form.Item
                              name={["query_config", "time_range"]}
                              label={t("dataSource.paramTypes.timeRange")}
                              className="!mb-2"
                              initialValue={60}
                              rules={[
                                {
                                  required: true,
                                  message: t("common.inputMsg"),
                                },
                              ]}
                            >
                              <InputNumber
                                min={1}
                                max={44640}
                                className="w-full"
                              />
                            </Form.Item>
                            <Form.Item
                              name={["query_config", "step"]}
                              label={t("dataSource.step")}
                              className="!mb-2"
                              initialValue="1m"
                            >
                              <Input placeholder="1m" />
                            </Form.Item>
                          </>
                        )}
                        <Form.Item
                          name={["query_config", "max_series"]}
                          label={t("dataSource.maxSeries")}
                          className="!mb-2"
                          initialValue={20}
                        >
                          <InputNumber
                            min={1}
                            max={50}
                            className="w-full"
                          />
                        </Form.Item>
                      </div>
                    ),
                  },
                ]}
              />
            </div>
          </Form.Item>
        )}
        {isExcelSource && (
          <Form.Item
            validateStatus={sourceInlineError ? "error" : undefined}
            help={sourceInlineError || undefined}
          >
            <div>
              <Upload
                disabled={readOnly}
                accept=".xlsx"
                maxCount={1}
                beforeUpload={(file) => {
                  setExcelFile(file);
                  setExcelFileList([file]);
                  setSourceInlineError(null);
                  clearPreviewState();
                  setSchemaFields([]);
                  return false;
                }}
                onRemove={() => {
                  setExcelFile(null);
                  setExcelFileList([]);
                  clearPreviewState();
                  setSchemaFields([]);
                }}
                fileList={excelFileList}
              >
                <Button icon={<UploadOutlined />}>
                  {t("dataSource.selectExcelFile")}
                </Button>
              </Upload>
              <div className="mt-3">
                <ExcelMaterializationStatus
                  state={excelMaterialization}
                  readOnly={readOnly}
                  retrying={excelRetryLoading}
                  pendingNewFile={Boolean(excelFile)}
                  onRetry={
                    excelMaterialization?.can_retry
                      ? handleRetryExcelMaterialization
                      : undefined
                  }
                />
              </div>
            </div>
          </Form.Item>
        )}
        {isNatsSource && (
          <ParamTable
            ref={paramTableRef}
            params={params}
            onChange={setParams}
            readOnly={readOnly}
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
                readOnly={readOnly}
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
              readOnly ? null : (
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
              readOnly={readOnly}
            />
          </FormSubsection>
        )}
        </FormSection>
        </div>
      </Form>
    </Drawer>
    <Modal
      title={t("dataConnection.extractConnectionTitle")}
      open={extractModalOpen}
      centered
      confirmLoading={extractLoading}
      okText={t("common.confirm")}
      cancelText={t("common.cancel")}
      onCancel={() => {
        if (extractLoading) return;
        setExtractModalOpen(false);
        extractForm.resetFields();
      }}
      onOk={() => {
        void handleExtractToConnectionLibrary();
      }}
      destroyOnClose
    >
      <Form form={extractForm} layout="vertical" className="pt-2">
        <Form.Item
          name="name"
          label={t("dataConnection.name")}
          rules={[{ required: true, message: t("common.inputMsg") }]}
        >
          <Input placeholder={t("common.inputMsg")} maxLength={128} />
        </Form.Item>
        <Form.Item name="description" label={t("dataConnection.describe")}>
          <Input.TextArea
            rows={3}
            placeholder={t("common.inputMsg")}
            maxLength={512}
          />
        </Form.Item>
      </Form>
    </Modal>
    </>
  );
};

export default OperateModal;
