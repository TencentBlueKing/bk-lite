"use client";

import React, { useEffect } from "react";
import GroupTreeSelect from "@/components/group-tree-select";
import { v4 as uuidv4 } from "uuid";
import { getChartTypeList } from "@/app/ops-analysis/constants/common";
import { UploadOutlined } from "@ant-design/icons";
import { useDataSourceApi } from "@/app/ops-analysis/api/dataSource";
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
  Radio,
} from "antd";
import type { UploadFile } from "antd/es/upload/interface";
import ParamTable, { ParamTableRef } from "./paramTable";
import FieldSchemaTable, { FieldSchemaTableRef } from "./fieldSchemaTable";
import PreviewPanel from "./previewPanel";
import {
  buildConnectorPayload,
  formatJsonText,
  normalizeFieldSchema,
  normalizeParams,
  PASSWORD_PLACEHOLDER,
  SchemaField,
  SOURCE_TYPE_EXCEL,
  SOURCE_TYPE_MYSQL,
  SOURCE_TYPE_NATS,
  SOURCE_TYPE_POSTGRESQL,
  SOURCE_TYPE_REST_API,
  TABLE_CHART_TYPE,
} from "./operateModalUtils";

const OperateModal: React.FC<OperateModalProps> = ({
  open,
  currentRow,
  onClose,
  onSuccess,
}) => {
  const { t } = useTranslation();
  const guardClose = useUnsavedConfirm();
  const [form] = Form.useForm();
  const handleClose = () => guardClose(form.isFieldsTouched(), onClose);
  const { selectedGroup } = useUserInfoContext();
  const [params, setParams] = React.useState<ParamItem[]>([]);
  const [loading, setLoading] = React.useState(false);
  const [schemaFields, setSchemaFields] = React.useState<SchemaField[]>([]);
  const [showSchemaConfig, setShowSchemaConfig] = React.useState(true);
  const [tagList, setTagList] = React.useState<TagItem[]>([]);
  const [tagsLoading, setTagsLoading] = React.useState(false);
  const [previewLoading, setPreviewLoading] = React.useState(false);
  const [previewData, setPreviewData] =
    React.useState<DataSourcePreviewResult | null>(null);
  const [excelFile, setExcelFile] = React.useState<File | null>(null);
  const [excelFileList, setExcelFileList] = React.useState<UploadFile[]>([]);
  const previousSourceTypeRef = React.useRef<DataSourceSourceType | undefined>(
    undefined,
  );
  const paramTableRef = React.useRef<ParamTableRef>(null);
  const fieldSchemaTableRef = React.useRef<FieldSchemaTableRef>(null);
  const { namespaceList, namespacesLoading, refreshNamespaces } =
    useOpsAnalysis();
  const {
    createDataSource,
    updateDataSource,
    previewDataSource,
    previewDataSourceConfig,
  } = useDataSourceApi();
  const { getTagList } = useNamespaceApi();
  const sourceType =
    (Form.useWatch("source_type", form) as DataSourceSourceType | undefined) ||
    SOURCE_TYPE_NATS;

  const sourceTypeOptions = [
    { label: t("dataSource.sourceTypes.nats"), value: SOURCE_TYPE_NATS },
    { label: "MySQL", value: SOURCE_TYPE_MYSQL },
    { label: "PostgreSQL", value: SOURCE_TYPE_POSTGRESQL },
    { label: "REST API", value: SOURCE_TYPE_REST_API },
    { label: "Excel", value: SOURCE_TYPE_EXCEL },
  ];

  const isNatsSource = sourceType === SOURCE_TYPE_NATS;
  const isRestApiSource = sourceType === SOURCE_TYPE_REST_API;
  const isDatabaseSource =
    sourceType === SOURCE_TYPE_MYSQL || sourceType === SOURCE_TYPE_POSTGRESQL;
  const isExcelSource = sourceType === SOURCE_TYPE_EXCEL;
  const chartTypeOptions = getChartTypeList()
    .filter((item) => isNatsSource || item.value === TABLE_CHART_TYPE)
    .map((item) => ({
      label: t(item.label),
      value: item.value,
    }));

  useEffect(() => {
    if (!open) return;

    const fetchTags = async () => {
      try {
        setTagsLoading(true);
        const response = await getTagList({ page_size: -1 });
        setTagList(Array.isArray(response) ? response : []);
      } catch (error) {
        console.error("获取标签列表失败:", error);
        setTagList([]);
      } finally {
        setTagsLoading(false);
      }
    };

    form.resetFields();
    setSchemaFields([]);
    paramTableRef.current?.clearValidation();
    fieldSchemaTableRef.current?.clearValidation();
    setShowSchemaConfig(true);
    setPreviewData(null);
    setExcelFile(null);
    setExcelFileList([]);
    previousSourceTypeRef.current = currentRow?.source_type || SOURCE_TYPE_NATS;
    void refreshNamespaces();
    void fetchTags();

    if (!currentRow) {
      setParams([]);
      form.setFieldsValue({
        source_type: SOURCE_TYPE_NATS,
        connection_config: {
          method: "GET",
          timeout: 10,
        },
        query_config: {},
      });
      // 新增时，如果用户有选中的分组，则设置为默认值
      if (selectedGroup) {
        form.setFieldValue("groups", [selectedGroup.id]);
      }
      return;
    }

    const connectionConfig = currentRow.connection_config || {};
    const queryConfig = currentRow.query_config || {};
    const rowSourceType = currentRow.source_type || SOURCE_TYPE_NATS;
    const formValues = {
      ...currentRow,
      source_type: rowSourceType,
      namespaces: currentRow.namespaces || [],
      groups: currentRow.groups || [],
      chart_type:
        rowSourceType === SOURCE_TYPE_NATS
          ? currentRow.chart_type || []
          : [TABLE_CHART_TYPE],
      connection_config: {
        ...connectionConfig,
        headersText: formatJsonText(connectionConfig.headers),
      },
      query_config: {
        ...queryConfig,
        paramsText: formatJsonText(queryConfig.params),
        bodyText: formatJsonText(queryConfig.body),
      },
    };
    form.setFieldsValue(formValues);

    if (
      currentRow.source_type === SOURCE_TYPE_EXCEL &&
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

    if (Array.isArray(currentRow.field_schema)) {
      setSchemaFields(
        currentRow.field_schema.map((field) => ({
          ...field,
          id: uuidv4(),
        })),
      );
    }

    const hasValidParams =
      currentRow.params &&
      Array.isArray(currentRow.params) &&
      currentRow.params.length > 0;

    if (hasValidParams) {
      setParams(
        currentRow.params.map((param: any) => ({
          ...param,
          type: param.type || "string",
          filterType:
            param.filterType ||
            (param.type === "timeRange" ? "filter" : "fixed"),
          id: param.id || uuidv4(),
        })),
      );
    } else {
      setParams([]);
    }
  }, [open, currentRow, form, selectedGroup, refreshNamespaces, getTagList]);

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
      return;
    }

    const previousSourceType = previousSourceTypeRef.current;
    if (!previousSourceType) {
      previousSourceTypeRef.current = sourceType;
      return;
    }

    if (previousSourceType !== sourceType) {
      if (sourceType !== SOURCE_TYPE_NATS) {
        form.setFieldValue("chart_type", [TABLE_CHART_TYPE]);
      }
      setPreviewData(null);
      setExcelFile(null);
      setExcelFileList([]);
      setSchemaFields([]);
      fieldSchemaTableRef.current?.clearValidation();
      previousSourceTypeRef.current = sourceType;
    }
  }, [open, sourceType, form]);

  const getPreviewFieldNames = (): (string | (string | number)[])[] => {
    if (isRestApiSource) {
      return [
        "source_type",
        ["connection_config", "url"],
        ["connection_config", "method"],
      ];
    }
    if (isDatabaseSource) {
      return [
        "source_type",
        ["connection_config", "host"],
        ["connection_config", "port"],
        ["connection_config", "database"],
        ["connection_config", "username"],
        ["connection_config", "password"],
      ];
    }
    return ["source_type"];
  };

  const handlePreview = async () => {
    if (isNatsSource) return;

    try {
      setPreviewLoading(true);
      await form.validateFields(getPreviewFieldNames());
      const values = form.getFieldsValue(true);
      let response: DataSourcePreviewResult;

      if (isExcelSource) {
        if (!excelFile) {
          message.error(t("dataSource.excelFileRequired"));
          return;
        }
        const formData = new FormData();
        formData.append("source_type", SOURCE_TYPE_EXCEL);
        formData.append("limit", "1000");
        formData.append("file", excelFile);
        response = await previewDataSourceConfig(formData);
      } else {
        const payload = {
          ...buildConnectorPayload(values, {
            excelFileName: excelFile?.name,
            previewData,
            t,
          }),
          limit: 50,
        };
        response = currentRow
          ? await previewDataSource(currentRow.id, payload)
          : await previewDataSourceConfig(payload);
      }

      setPreviewData(response);
      message.success(t("dataSource.previewSuccess"));
    } catch (error: any) {
      if (error?.errorFields) return;
    } finally {
      setPreviewLoading(false);
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

  const handlePasswordFocus = (event: React.FocusEvent<HTMLInputElement>) => {
    if (!currentRow) return;
    if (event.target.value === PASSWORD_PLACEHOLDER) {
      form.setFieldValue(["connection_config", "password"], "");
    }
  };

  const handlePasswordBlur = (event: React.FocusEvent<HTMLInputElement>) => {
    if (!currentRow) return;
    if (!event.target.value?.trim()) {
      form.setFieldValue(
        ["connection_config", "password"],
        PASSWORD_PLACEHOLDER,
      );
    }
  };

  const onFinish = async (values: any) => {
    try {
      setLoading(true);

      if (isNatsSource) {
        if (!paramTableRef.current?.validate()) {
          setLoading(false);
          return;
        }
      }

      if (isExcelSource && !previewData?.items?.length) {
        message.error(t("dataSource.excelPreviewRequired"));
        setLoading(false);
        return;
      }

      // 检查表格字段配置
      if (schemaFields.length > 0) {
        if (!fieldSchemaTableRef.current?.validate()) {
          setLoading(false);
          return;
        }
      }

      const fieldSchema = normalizeFieldSchema(schemaFields);
      const connectorPayload = buildConnectorPayload(values, {
        excelFileName: excelFile?.name,
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
        chart_type: isNatsSource ? values.chart_type || [] : [TABLE_CHART_TYPE],
        groups: values.groups || [],
        field_schema: fieldSchema,
        params: isNatsSource ? normalizeParams(params) : [],
      };

      if (currentRow) {
        await updateDataSource(currentRow.id, submitData);
        message.success(t("dataSource.updateDataSourceSuccess"));
      } else {
        await createDataSource(submitData);
        message.success(t("dataSource.createDataSourceSuccess"));
      }

      onClose();
      onSuccess && onSuccess();
    } catch (error: any) {
      message.error(error.message || t("dataSource.operationFailed"));
    } finally {
      setLoading(false);
    }
  };

  return (
    <Drawer
      title={
        currentRow
          ? `${t("common.edit")}${t("dataSource.title")} - ${currentRow.name}`
          : `${t("common.add")}${t("dataSource.title")}`
      }
      placement="right"
      width={900}
      open={open}
      maskClosable={false}
      onClose={handleClose}
      styles={{
        body: {
          maxHeight: "calc(100vh - 112px)",
          overflowY: "auto",
        },
      }}
      footer={
        <div style={{ textAlign: "right" }}>
          <Button
            type="primary"
            loading={loading}
            onClick={() => form.submit()}
          >
            {t("common.confirm")}
          </Button>
          <Button style={{ marginLeft: 8 }} onClick={handleClose}>
            {t("common.cancel")}
          </Button>
        </div>
      }
    >
      <Form
        form={form}
        layout="vertical"
        onFinish={onFinish}
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
              if (nextSourceType !== SOURCE_TYPE_NATS) {
                form.setFieldValue("chart_type", [TABLE_CHART_TYPE]);
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
                <div style={{ textAlign: "center", padding: "8px 0" }}>
                  <Spin size="small" />
                </div>
              ) : namespaceList.length === 0 ? (
                <div
                  style={{
                    color: "var(--color-text-4)",
                    fontSize: "13px",
                  }}
                >
                  {t("common.noData")}
                </div>
              ) : (
                <Checkbox.Group className="grid grid-cols-3 gap-x-4 gap-y-2 pt-1">
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
            <div style={{ textAlign: "center", padding: "8px 0" }}>
              <Spin size="small" />
            </div>
          ) : tagList.length === 0 ? (
            <div
              style={{
                color: "var(--color-text-4)",
                fontSize: "13px",
              }}
            >
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
          <Checkbox.Group options={chartTypeOptions} />
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
          />
        </Form.Item>
        <Form.Item name="desc" label={t("dataSource.describe")}>
          <Input.TextArea
            rows={3}
            placeholder={`${t("common.inputMsg")} ${t("dataSource.describe")}`}
          />
        </Form.Item>
        {isRestApiSource && (
          <Form.Item label={t("dataSource.connectionConfig")}>
            <div className="rounded-md border border-[var(--color-border-2)] bg-[var(--color-bg-2)] px-3 pb-0 pt-3">
              <div className="grid grid-cols-2 gap-x-3">
                <Form.Item
                  name={["connection_config", "url"]}
                  label={t("dataSource.url")}
                  className="!mb-2"
                  rules={[{ required: true, message: t("common.inputMsg") }]}
                >
                  <Input placeholder="https://example.com/api" />
                </Form.Item>
                <Form.Item
                  name={["connection_config", "method"]}
                  label={t("dataSource.method")}
                  className="!mb-2"
                  initialValue="GET"
                >
                  <Select
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
                  <InputNumber min={1} max={30} style={{ width: "100%" }} />
                </Form.Item>
                <Form.Item
                  name={["query_config", "response_path"]}
                  label={t("dataSource.responsePath")}
                  className="!mb-2"
                >
                  <Input placeholder="data.items" />
                </Form.Item>
              </div>
              <Form.Item
                name={["connection_config", "headersText"]}
                label={t("dataSource.headers")}
                className="!mb-2"
              >
                <Input.TextArea
                  rows={3}
                  placeholder='{"Authorization":"Bearer ..."}'
                />
              </Form.Item>
              <Form.Item
                name={["query_config", "paramsText"]}
                label={t("dataSource.queryParams")}
                className="!mb-2"
              >
                <Input.TextArea rows={3} placeholder='{"page":1}' />
              </Form.Item>
              <Form.Item
                name={["query_config", "bodyText"]}
                label={t("dataSource.requestBody")}
                className="!mb-2"
              >
                <Input.TextArea rows={3} placeholder='{"limit":50}' />
              </Form.Item>
            </div>
          </Form.Item>
        )}
        {isDatabaseSource && (
          <Form.Item label={t("dataSource.connectionConfig")}>
            <div className="rounded-md border border-[var(--color-border-2)] bg-[var(--color-bg-2)] px-3 pb-0 pt-3">
              <div className="grid grid-cols-2 gap-x-3">
                <Form.Item
                  name={["connection_config", "host"]}
                  label={t("dataSource.host")}
                  className="!mb-2"
                  rules={[{ required: true, message: t("common.inputMsg") }]}
                >
                  <Input placeholder="127.0.0.1" />
                </Form.Item>
                <Form.Item
                  name={["connection_config", "port"]}
                  label={t("dataSource.port")}
                  className="!mb-2"
                  rules={[{ required: true, message: t("common.inputMsg") }]}
                >
                  <InputNumber min={1} max={65535} style={{ width: "100%" }} />
                </Form.Item>
                <Form.Item
                  name={["connection_config", "database"]}
                  label={t("dataSource.database")}
                  className="!mb-2"
                  rules={[{ required: true, message: t("common.inputMsg") }]}
                >
                  <Input />
                </Form.Item>
                <Form.Item
                  name={["connection_config", "username"]}
                  label={t("dataSource.username")}
                  className="!mb-2"
                  rules={[{ required: true, message: t("common.inputMsg") }]}
                >
                  <Input />
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
                  />
                </Form.Item>
                <Form.Item
                  name={["query_config", "table"]}
                  label={t("dataSource.tableName")}
                  className="!mb-2"
                >
                  <Input />
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
                />
              </Form.Item>
            </div>
          </Form.Item>
        )}
        {isExcelSource && (
          <Form.Item label={t("dataSource.excelImport")}>
            <div>
              <Upload
                accept=".xlsx"
                maxCount={1}
                beforeUpload={(file) => {
                  setExcelFile(file);
                  setExcelFileList([file]);
                  setPreviewData(null);
                  setSchemaFields([]);
                  return false;
                }}
                onRemove={() => {
                  setExcelFile(null);
                  setExcelFileList([]);
                  setPreviewData(null);
                  setSchemaFields([]);
                }}
                fileList={excelFileList}
              >
                <Button icon={<UploadOutlined />}>
                  {t("dataSource.selectExcelFile")}
                </Button>
              </Upload>
            </div>
          </Form.Item>
        )}
        {!isNatsSource && (
          <PreviewPanel
            previewData={previewData}
            previewLoading={previewLoading}
            onPreview={handlePreview}
            onApplyPreviewFields={handleApplyPreviewFields}
          />
        )}
        {isNatsSource && (
          <ParamTable
            ref={paramTableRef}
            params={params}
            onChange={setParams}
          />
        )}
        {showSchemaConfig && (
          <FieldSchemaTable
            ref={fieldSchemaTableRef}
            schemaFields={schemaFields}
            onChange={setSchemaFields}
          />
        )}
      </Form>
    </Drawer>
  );
};

export default OperateModal;
