import React, { useEffect, useMemo, useState } from "react";
import {
  Drawer,
  Button,
  Tag,
  Select,
  Form,
  Radio,
  Space,
  Popconfirm,
  Empty,
  Tooltip,
} from "antd";
import {
  DeleteOutlined,
  EditOutlined,
  PlusOutlined,
} from "@ant-design/icons";
import { useTranslation } from "@/utils/i18n";
import { ThresholdColorConfigSection } from "@/app/ops-analysis/components/thresholdColorConfigSection";
import type {
  NetworkMetricAggregateType,
  NetworkMetricConditionFilter,
  NetworkMetricDisplayMode,
  NetworkInterfaceRef,
  NetworkNodeRuntime,
  NetworkTopologyMetric,
  NetworkTopologyNode,
} from "@/app/ops-analysis/types/networkTopology";
import type { ThresholdColorConfig } from "@/app/ops-analysis/utils/thresholdUtils";
import { DEFAULT_THRESHOLD_COLORS } from "@/app/ops-analysis/constants/threshold";
import { isValidThresholdList } from "../utils/thresholdUtils";
import {
  buildBoundMetricConfigRows,
  buildNetworkTopologyMetricDraft,
  isMetricOptionMatched,
  normalizeNetworkTopologyMetricOrder,
  replaceNetworkTopologyMetricDraft,
} from "../utils/networkTopologyUtils";

interface NetworkMetricOption {
  metric_field: string;
  result_table_id: string;
  display_name: string;
  unit: string;
  supported_dimensions?: string[];
}

const AGGREGATE_OPTIONS: Array<{
  value: NetworkMetricAggregateType;
  labelKey: string;
}> = [
  { value: "sum", labelKey: "opsAnalysis.networkTopology.node.aggregateSum" },
  { value: "max", labelKey: "opsAnalysis.networkTopology.node.aggregateMax" },
  { value: "min", labelKey: "opsAnalysis.networkTopology.node.aggregateMin" },
  { value: "mean", labelKey: "opsAnalysis.networkTopology.node.aggregateMean" },
  { value: "last", labelKey: "opsAnalysis.networkTopology.node.aggregateLast" },
];

export interface NetworkNodeDrawerProps {
  open: boolean;
  node: NetworkTopologyNode | null;
  nodeRuntime?: NetworkNodeRuntime;
  /** WeOps 接口下拉选项(从后端返回的当前节点的接口)。 */
  interfaces?: Array<NetworkInterfaceRef>;
  readonly?: boolean;
  metricOptions?: NetworkMetricOption[];
  metricOptionsLoading?: boolean;
  dimensionValueOptions?: Record<
    string,
    Array<{ label: string; value: string }>
  >;
  dimensionValuesLoading?: boolean;
  dimensionLoadError?: string | null;
  onLoadDimensionValues?: (
    metric: NetworkMetricOption,
    dimensionKeys?: string[],
  ) => void | Promise<void>;
  onClose: () => void;
  onCommitMetrics: (metrics: NetworkTopologyMetric[]) => void;
  onEditEdge?: (sortOrder: number) => void;
  zIndex?: number;
  testId?: string;
}

const buildThresholdDraftFromMetric = (
  metric: NetworkTopologyMetric | undefined,
): ThresholdColorConfig[] => {
  if (!metric || metric.thresholds.length === 0) {
    return DEFAULT_THRESHOLD_COLORS.map((t) => ({ ...t }));
  }
  return metric.thresholds.map((t) => ({
    value: String(t.value),
    color: t.color,
  }));
};

const conditionFilterFromDimensions = (
  dimensions: Record<string, string> | undefined,
): NetworkMetricConditionFilter[] =>
  Object.entries(dimensions ?? {}).reduce<NetworkMetricConditionFilter[]>(
    (acc, [dimensionId, value]) => {
      if (dimensionId && value) {
        acc.push({ dimension_id: dimensionId, value: [value] });
      }
      return acc;
    },
    [],
  );

const normalizeConditionFilterFormValue = (
  value: unknown,
): NetworkMetricConditionFilter[] =>
  Array.isArray(value)
    ? value.reduce<NetworkMetricConditionFilter[]>((acc, item) => {
      if (!item || typeof item !== "object") return acc;
      const row = item as {
        dimension_id?: unknown;
        value?: unknown;
      };
      const dimensionId =
        typeof row.dimension_id === "string" ? row.dimension_id.trim() : "";
      const rawValues = Array.isArray(row.value) ? row.value : [row.value];
      const values = Array.from(
        new Set(
          rawValues
            .map((option) =>
              typeof option === "string" ? option.trim() : "",
            )
            .filter(Boolean),
        ),
      );
      if (dimensionId && values.length > 0) {
        acc.push({ dimension_id: dimensionId, value: values });
      }
      return acc;
    }, [])
    : [];

/**
 * 节点配置 Drawer(design.md §7.4):
 * - 基本信息只读
 * - 已绑定指标列表(行内可编辑 / 删除)
 * - 添加新指标 → 选 metric → 维度(可选) → 阈值
 */
const NetworkNodeDrawer: React.FC<NetworkNodeDrawerProps> = ({
  open,
  node,
  nodeRuntime,
  readonly = false,
  metricOptions = [],
  dimensionValueOptions = {},
  dimensionValuesLoading = false,
  dimensionLoadError = null,
  onLoadDimensionValues,
  onClose,
  onCommitMetrics,
  metricOptionsLoading = false,
  zIndex,
  testId,
}) => {
  const { t } = useTranslation();
  const [form] = Form.useForm();
  const [selectedMetricKey, setSelectedMetricKey] = useState<string | null>(
    null,
  );
  const [editingSortOrder, setEditingSortOrder] = useState<number | null>(null);
  const [draftMetrics, setDraftMetrics] = useState<NetworkTopologyMetric[]>([]);
  const [thresholds, setThresholds] = useState<ThresholdColorConfig[]>(
    DEFAULT_THRESHOLD_COLORS.map((t) => ({ ...t })),
  );
  const displayMode = Form.useWatch("display_mode", form) as
    | NetworkMetricDisplayMode
    | undefined;
  const conditionFilterRows = (Form.useWatch("condition_filter", form) ??
    []) as NetworkMetricConditionFilter[];
  const metricKeyOf = (
    metric: Pick<NetworkTopologyMetric, "metric_field" | "result_table_id">,
  ) => `${metric.metric_field}::${metric.result_table_id}`;

  useEffect(() => {
    if (!open) return;
    form.resetFields();
    setSelectedMetricKey(null);
    setEditingSortOrder(null);
    setDraftMetrics(normalizeNetworkTopologyMetricOrder(node?.metrics ?? []));
    setThresholds(DEFAULT_THRESHOLD_COLORS.map((t) => ({ ...t })));
  }, [open, form, node?.id]);

  const sortedMetrics = useMemo(() => {
    return normalizeNetworkTopologyMetricOrder(draftMetrics);
  }, [draftMetrics]);
  const boundMetricRows = useMemo(
    () =>
      buildBoundMetricConfigRows(sortedMetrics, {
        aggregate: t("opsAnalysis.networkTopology.node.displayModeAggregate"),
        dimension: t("opsAnalysis.networkTopology.node.displayModeDimension"),
        aggregateTypes: {
          sum: t("opsAnalysis.networkTopology.node.aggregateSum"),
          max: t("opsAnalysis.networkTopology.node.aggregateMax"),
          min: t("opsAnalysis.networkTopology.node.aggregateMin"),
          mean: t("opsAnalysis.networkTopology.node.aggregateMean"),
          last: t("opsAnalysis.networkTopology.node.aggregateLast"),
        },
      }),
    [sortedMetrics, t],
  );
  const combinedMetricOptions = useMemo(() => {
    const optionMap = new Map<string, NetworkMetricOption>();
    metricOptions.forEach((item) => {
      optionMap.set(`${item.metric_field}::${item.result_table_id}`, item);
    });
    draftMetrics.forEach((metric) => {
      const key = metricKeyOf(metric);
      if (!optionMap.has(key)) {
        optionMap.set(key, {
          metric_field: metric.metric_field,
          result_table_id: metric.result_table_id,
          display_name: metric.display_name,
          unit: metric.unit,
          supported_dimensions: Array.from(
            new Set([
              ...Object.keys(metric.dimensions ?? {}),
              ...(metric.condition_filter ?? []).map(
                (item) => item.dimension_id,
              ),
            ]),
          ).filter(Boolean),
        });
      }
    });
    return Array.from(optionMap.values());
  }, [draftMetrics, metricOptions]);
  const compactFormItemStyle: React.CSSProperties = { marginBottom: 10 };
  const compactLabelStyle: React.CSSProperties = {
    color: "#334250",
    fontSize: 14,
    fontWeight: 400,
  };
  const interfaceSummary = nodeRuntime?.interface_summary;

  const onSelectMetric = (
    metricKey: string,
    options?: { preserveConfig?: boolean },
  ) => {
    setSelectedMetricKey(metricKey);
    const metric = combinedMetricOptions.find(
      (item) => `${item.metric_field}::${item.result_table_id}` === metricKey,
    );
    if (metric) {
      if (options?.preserveConfig) {
        form.setFieldValue("dimensions", {});
        form.setFieldValue("condition_filter", []);
      } else {
        form.setFieldsValue({
          display_mode: "aggregate",
          aggregate_type: "sum",
          dimensions: {},
          condition_filter: [],
        });
        setThresholds(buildThresholdDraftFromMetric(undefined));
      }
    }
  };

  const buildPendingMetric = (sortOrder: number): NetworkTopologyMetric | null => {
    if (!node || readonly || !selectedMetricKey) return null;
    const metric = combinedMetricOptions.find(
      (item) =>
        `${item.metric_field}::${item.result_table_id}` === selectedMetricKey,
    );
    if (!metric) return null;
    const metricDisplayMode =
      ((form.getFieldValue("display_mode") as NetworkMetricDisplayMode) ??
        "aggregate");
    const aggregateType =
      ((form.getFieldValue("aggregate_type") as NetworkMetricAggregateType) ??
        "sum");
    const conditionFilter = normalizeConditionFilterFormValue(
      form.getFieldValue("condition_filter"),
    );
    if (!isValidThresholdList(thresholds)) {
      return null;
    }
    return buildNetworkTopologyMetricDraft({
      metricOption: metric,
      displayMode: metricDisplayMode,
      aggregateType,
      conditionFilter,
      sortOrder,
      thresholds,
    });
  };

  const resetPendingMetric = () => {
    setSelectedMetricKey(null);
    setThresholds(DEFAULT_THRESHOLD_COLORS.map((t) => ({ ...t })));
    form.resetFields();
  };

  const buildMetricsForCommit = (): NetworkTopologyMetric[] | null => {
    if (editingSortOrder !== null) {
      const nextMetric = buildPendingMetric(editingSortOrder);
      if (!nextMetric) return selectedMetricKey ? null : sortedMetrics;
      return replaceNetworkTopologyMetricDraft(
        draftMetrics,
        editingSortOrder,
        nextMetric,
      );
    }
    const pending = buildPendingMetric(draftMetrics.length);
    if (!pending) return selectedMetricKey ? null : sortedMetrics;
    return normalizeNetworkTopologyMetricOrder([...draftMetrics, pending]);
  };

  const onSaveNewMetric = () => {
    const pending = buildPendingMetric(draftMetrics.length);
    if (!pending) return;
    setDraftMetrics((prev) =>
      normalizeNetworkTopologyMetricOrder([...prev, pending]),
    );
    resetPendingMetric();
  };

  const commitMetricsAndClose = () => {
    const nextMetrics = buildMetricsForCommit();
    if (!nextMetrics) return;
    onCommitMetrics(nextMetrics);
    onClose();
  };

  const closeWithPendingMetric = () => {
    const nextMetrics = buildMetricsForCommit();
    if (!readonly && nextMetrics && selectedMetricKey) {
      onCommitMetrics(nextMetrics);
    }
    onClose();
  };

  const onSaveEditMetric = (sortOrder: number) => {
    if (!node || readonly) return;
    const next = buildPendingMetric(sortOrder);
    if (!next) return;
    setDraftMetrics((prev) =>
      replaceNetworkTopologyMetricDraft(
        prev,
        sortOrder,
        next,
      ),
    );
    setEditingSortOrder(null);
    resetPendingMetric();
  };

  const onRemoveMetric = (sortOrder: number) => {
    if (readonly) return;
    setDraftMetrics((prev) =>
      normalizeNetworkTopologyMetricOrder(
        prev.filter((metric) => metric.sort_order !== sortOrder),
      ),
    );
    if (editingSortOrder === sortOrder) {
      setEditingSortOrder(null);
      resetPendingMetric();
    }
  };

  const renderMetricEditor = (
    onSave: () => void,
    onCancel: () => void,
    saveButtonSize?: "small",
  ) => {
    if (!selectedMetricKey) return null;
    const metric = combinedMetricOptions.find(
      (item) => `${item.metric_field}::${item.result_table_id}` === selectedMetricKey,
    );
    const dimensionKeys = metric?.supported_dimensions ?? [];
    return (
      <Form form={form} layout="vertical" style={{ marginTop: 6 }}>
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "52px minmax(0, 1fr)",
            alignItems: "center",
            gap: 10,
            marginBottom: 10,
          }}
        >
          <span style={compactLabelStyle}>
            {t("opsAnalysis.networkTopology.node.labelMetric")}
          </span>
          <Select
            showSearch
            optionFilterProp="label"
            filterOption={isMetricOptionMatched}
            placeholder={t(
              "opsAnalysis.networkTopology.node.selectMetricPlaceholder",
            )}
            loading={metricOptionsLoading}
            getPopupContainer={(trigger) =>
              trigger.parentElement ?? document.body
            }
            options={combinedMetricOptions.map((item) => ({
              label: item.display_name,
              value: `${item.metric_field}::${item.result_table_id}`,
            }))}
            value={selectedMetricKey ?? undefined}
            onChange={(value) =>
              onSelectMetric(value, {
                preserveConfig: editingSortOrder !== null,
              })
            }
            data-testid="network-node-drawer-metric-select"
          />
        </div>
        {metric && (
          <>
            {dimensionLoadError &&
              (displayMode ?? "aggregate") === "dimension" && (
                <div
                  style={{
                    marginBottom: 10,
                    fontSize: 12,
                    color: "#94a3b8",
                  }}
                >
                  {t(
                    "opsAnalysis.networkTopology.node.dimensionLoadFailed",
                  )}
                </div>
            )}
            <Form.Item
              name="display_mode"
              label={t(
                "opsAnalysis.networkTopology.node.labelDisplayMode",
              )}
              initialValue="aggregate"
              style={compactFormItemStyle}
            >
              <Radio.Group
                onChange={(event) => {
                  const nextMode = event.target.value as NetworkMetricDisplayMode;
                  if (
                    nextMode === "dimension" &&
                    (metric.supported_dimensions ?? []).length > 0 &&
                    conditionFilterRows.length === 0
                  ) {
                    form.setFieldValue("condition_filter", [
                      { dimension_id: "", value: [] },
                    ]);
                  }
                }}
              >
                <Radio value="aggregate">
                  {t(
                    "opsAnalysis.networkTopology.node.displayModeAggregate",
                  )}
                </Radio>
                <Radio
                  value="dimension"
                  disabled={dimensionKeys.length === 0}
                >
                  {t(
                    "opsAnalysis.networkTopology.node.displayModeDimension",
                  )}
                </Radio>
              </Radio.Group>
            </Form.Item>
            <Form.Item
              name="aggregate_type"
              label={t(
                "opsAnalysis.networkTopology.node.labelAggregateType",
              )}
              initialValue="sum"
              style={compactFormItemStyle}
            >
              <Select
                getPopupContainer={(trigger) =>
                  trigger.parentElement ?? document.body
                }
                options={AGGREGATE_OPTIONS.map((item) => ({
                  value: item.value,
                  label: t(item.labelKey),
                }))}
              />
            </Form.Item>
            {(displayMode ?? "aggregate") === "dimension" &&
              dimensionKeys.length > 0 && (
                <Form.List name="condition_filter">
                  {(fields, { add, remove }) => {
                    const selectedDimensions = new Set(
                      conditionFilterRows
                        .map((item) => item?.dimension_id)
                        .filter(Boolean),
                    );
                    return (
                      <div style={{ marginBottom: 10 }}>
                        <div
                          style={{
                            color: "#334250",
                            fontSize: 14,
                            marginBottom: 6,
                          }}
                        >
                          {t("opsAnalysis.networkTopology.node.dimensionFilter")}
                        </div>
                        <Space
                          direction="vertical"
                          size={8}
                          style={{ width: "100%" }}
                        >
                          {fields.map((field) => {
                            const selectedDimension =
                              conditionFilterRows[field.name]?.dimension_id;
                            return (
                              <div
                                key={field.key}
                                style={{
                                  display: "grid",
                                  gridTemplateColumns:
                                    "minmax(120px, 1fr) 20px minmax(0, 1.35fr) 28px",
                                  alignItems: "center",
                                  gap: 8,
                                }}
                              >
                                <Form.Item
                                  name={[field.name, "dimension_id"]}
                                  style={{ marginBottom: 0 }}
                                >
                                  <Select
                                    allowClear
                                    showSearch
                                    optionFilterProp="label"
                                    placeholder={t(
                                      "opsAnalysis.networkTopology.node.selectDimensionFieldPlaceholder",
                                    )}
                                    getPopupContainer={(trigger) =>
                                      trigger.parentElement ?? document.body
                                    }
                                    options={dimensionKeys.map((dim) => ({
                                      label: dim,
                                      value: dim,
                                      disabled:
                                        selectedDimensions.has(dim) &&
                                        dim !== selectedDimension,
                                    }))}
                                    onChange={(value) => {
                                      form.setFieldValue(
                                        ["condition_filter", field.name, "value"],
                                        [],
                                      );
                                      if (value) {
                                        void onLoadDimensionValues?.(metric, [
                                          value,
                                        ]);
                                      }
                                    }}
                                  />
                                </Form.Item>
                                <span style={{ color: "#64748b" }}>=</span>
                                <Form.Item
                                  name={[field.name, "value"]}
                                  style={{ marginBottom: 0 }}
                                >
                                  <Select
                                    allowClear
                                    showSearch
                                    mode="multiple"
                                    loading={dimensionValuesLoading}
                                    disabled={!selectedDimension}
                                    optionFilterProp="label"
                                    maxTagCount="responsive"
                                    placeholder={t(
                                      "opsAnalysis.networkTopology.node.selectDimensionValuePlaceholder",
                                    )}
                                    getPopupContainer={(trigger) =>
                                      trigger.parentElement ?? document.body
                                    }
                                    options={
                                      selectedDimension
                                        ? (dimensionValueOptions[
                                          selectedDimension
                                        ] ?? [])
                                        : []
                                    }
                                  />
                                </Form.Item>
                                <Button
                                  size="small"
                                  type="text"
                                  icon={<DeleteOutlined />}
                                  disabled={fields.length <= 1}
                                  onClick={() => remove(field.name)}
                                />
                              </div>
                            );
                          })}
                          <Button
                            size="small"
                            type="dashed"
                            icon={<PlusOutlined />}
                            onClick={() =>
                              add({ dimension_id: "", value: [] })
                            }
                          >
                            {t("opsAnalysis.networkTopology.node.addDimensionFilter")}
                          </Button>
                        </Space>
                      </div>
                    );
                  }}
                </Form.List>
            )}
            <div style={{ marginTop: 6 }}>
              <ThresholdColorConfigSection
                t={t}
                thresholdColors={thresholds}
                onThresholdChange={(idx, field, value) => {
                  setThresholds((prev) => {
                    const next = [...prev];
                    next[idx] = {
                      ...next[idx],
                      [field]:
                        typeof value === "string"
                          ? value
                          : String(value ?? ""),
                    };
                    return next;
                  });
                }}
                onThresholdBlur={() => {}}
                onAddThreshold={(afterIndex) => {
                  setThresholds((prev) => {
                    const insertAt =
                      typeof afterIndex === "number"
                        ? afterIndex + 1
                        : prev.length;
                    return [
                      ...prev.slice(0, insertAt),
                      { value: "0", color: "#d97706" },
                      ...prev.slice(insertAt),
                    ];
                  });
                }}
                onRemoveThreshold={(idx) => {
                  setThresholds((prev) =>
                    prev.filter((_, i) => i !== idx),
                  );
                }}
              />
              <Space>
                <Button
                  type="primary"
                  size={saveButtonSize}
                  onClick={onSave}
                  data-testid="network-node-drawer-save-metric"
                >
                  {t("opsAnalysis.networkTopology.node.confirmEdit")}
                </Button>
                <Button
                  size={saveButtonSize}
                  onClick={onCancel}
                >
                  {t(
                    editingSortOrder !== null
                      ? "opsAnalysis.networkTopology.node.cancelEdit"
                      : "opsAnalysis.networkTopology.node.cancelSelect",
                  )}
                </Button>
              </Space>
            </div>
          </>
        )}
      </Form>
    );
  };

  return (
    <Drawer
      open={open}
      onClose={closeWithPendingMetric}
      width={640}
      zIndex={zIndex}
      destroyOnClose
      title={
        node
          ? t(
            readonly
              ? "opsAnalysis.networkTopology.node.detailTitleWithName"
              : "opsAnalysis.networkTopology.node.drawerTitleWithName",
            undefined,
            {
              name: node.bk_inst_name,
            },
          )
          : t(
            readonly
              ? "opsAnalysis.networkTopology.node.detailTitle"
              : "opsAnalysis.networkTopology.node.drawerTitle",
          )
      }
      data-testid={testId ?? "network-node-drawer"}
      footer={
        <div style={{ display: "flex", justifyContent: "flex-end" }}>
          <Space>
            <Button onClick={closeWithPendingMetric}>
              {t("opsAnalysis.networkTopology.node.closeButton")}
            </Button>
            {!readonly && (
              <Button
                type="primary"
                onClick={commitMetricsAndClose}
              >
                {t("opsAnalysis.networkTopology.node.confirmEdit")}
              </Button>
            )}
          </Space>
        </div>
      }
    >
      {!node ? (
        <Empty
          description={t("opsAnalysis.networkTopology.node.emptySelection")}
        />
      ) : (
        <>
          <div
            data-testid="network-node-drawer-basic"
            style={{
              border: "1px solid #e5e9ef",
              borderRadius: 4,
              overflow: "hidden",
              background: "#fff",
            }}
          >
            <div
              style={{
                display: "grid",
                gridTemplateColumns: "132px minmax(0, 1fr)",
              }}
            >
              {[
                {
                  label: t("opsAnalysis.networkTopology.node.labelAsset"),
                  value: node.bk_inst_name || "--",
                },
                {
                  label: t("opsAnalysis.networkTopology.node.labelAssetId"),
                  value: `${node.bk_obj_id}:${node.bk_inst_id}`,
                },
                {
                  label: t("opsAnalysis.networkTopology.node.labelAddress"),
                  value: node.ip_addr || "--",
                },
                {
                  label: t("opsAnalysis.networkTopology.node.labelTemplate"),
                  value:
                    node.plugin_template_name ||
                    node.plugin_template_id ||
                    "--",
                },
                {
                  label: t(
                    "opsAnalysis.networkTopology.node.labelInterfaceSummary",
                  ),
                  value: interfaceSummary ? (
                    <Space size={6} wrap>
                      <Tag color="green">
                        {t(
                          "opsAnalysis.networkTopology.node.interfaceUp",
                          undefined,
                          {
                            count: interfaceSummary.up,
                          },
                        )}
                      </Tag>
                      <Tag color="red">
                        {t(
                          "opsAnalysis.networkTopology.node.interfaceDown",
                          undefined,
                          {
                            count: interfaceSummary.down,
                          },
                        )}
                      </Tag>
                      <Tag>
                        {t(
                          "opsAnalysis.networkTopology.node.interfaceUnknown",
                          undefined,
                          {
                            count: interfaceSummary.unknown,
                          },
                        )}
                      </Tag>
                      <Tag>
                        {t(
                          "opsAnalysis.networkTopology.node.interfaceTotal",
                          undefined,
                          {
                            count: interfaceSummary.total,
                          },
                        )}
                      </Tag>
                    </Space>
                  ) : (
                    "--"
                  ),
                },
              ].map((item) => (
                <React.Fragment key={item.label}>
                  <div
                    style={{
                      minWidth: 0,
                      padding: "10px 12px",
                      borderRight: "1px solid #e5e9ef",
                      borderBottom: "1px solid #e5e9ef",
                      background: "#f7f9fc",
                      color: "#5f7290",
                      fontSize: 12,
                    }}
                  >
                    {item.label}
                  </div>
                  <div
                    style={{
                      minWidth: 0,
                      padding: "10px 12px",
                      borderRight: "1px solid #e5e9ef",
                      borderBottom: "1px solid #e5e9ef",
                      color: "#1f2933",
                      fontSize: 12,
                      overflow: "hidden",
                      textOverflow: "ellipsis",
                      whiteSpace:
                        typeof item.value === "string" ? "nowrap" : undefined,
                    }}
                    title={
                      typeof item.value === "string" ? item.value : undefined
                    }
                  >
                    {item.value}
                  </div>
                </React.Fragment>
              ))}
            </div>
          </div>

          {sortedMetrics.length > 0 && (
            <div
              style={{
                marginTop: 14,
              }}
              data-testid="network-node-drawer-bound-metrics"
            >
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                  marginBottom: 8,
                }}
              >
                <strong style={{ color: "#1f2937", fontSize: 13 }}>
                  {t(
                    "opsAnalysis.networkTopology.node.boundMetricsTitle",
                    undefined,
                    {
                      count: sortedMetrics.length,
                    },
                  )}
                </strong>
              </div>
              <Space
                direction="vertical"
                size={10}
                style={{ width: "100%" }}
              >
                {sortedMetrics.map((metric, index) => {
                  const row = boundMetricRows[index];
                  const isEditing = editingSortOrder === metric.sort_order;
                  const thresholdPreviewItems = row?.thresholds ?? [];
                  return (
                    <div
                      key={`${metric.result_table_id}:${metric.metric_field}:${metric.sort_order}`}
                      style={{
                        padding: "10px 12px",
                        border: "1px solid #e6edf5",
                        borderRadius: 6,
                        background: "#fff",
                        boxShadow: "0 1px 2px rgba(15, 23, 42, 0.04)",
                      }}
                      data-testid="network-node-drawer-metric-row"
                    >
                      <div style={{ display: "flex", alignItems: "center" }}>
                        <div style={{ flex: 1, minWidth: 0 }}>
                          <strong
                            style={{
                              display: "block",
                              overflow: "hidden",
                              textOverflow: "ellipsis",
                              whiteSpace: "nowrap",
                              color: "#111827",
                              fontSize: 13,
                              fontWeight: 600,
                            }}
                            title={row?.label}
                          >
                            {row?.label ?? metric.display_name ?? metric.metric_field}
                          </strong>
                          {!isEditing && (
                            <div
                              style={{
                                display: "inline-flex",
                                alignItems: "center",
                                maxWidth: "100%",
                                marginTop: 5,
                                padding: "2px 7px",
                                borderRadius: 4,
                                background: "#f3f6fb",
                                color: "#5f6f85",
                                fontSize: 11,
                                lineHeight: "18px",
                              }}
                              title={row?.scopeText}
                            >
                              <span
                                style={{
                                  overflow: "hidden",
                                  textOverflow: "ellipsis",
                                  whiteSpace: "nowrap",
                                }}
                              >
                                {row?.scopeText}
                              </span>
                            </div>
                          )}
                        </div>
                        {!isEditing && (
                          <Tooltip
                            title={t(
                              "opsAnalysis.networkTopology.node.editThresholdTooltip",
                            )}
                          >
                            <Button
                              size="small"
                              type="text"
                              icon={<EditOutlined />}
                              disabled={readonly}
                              onClick={() => {
                                const metricKey = metricKeyOf(metric);
                                const metricDisplayMode =
                                  metric.display_mode ??
                                  (Object.keys(metric.dimensions ?? {}).length > 0
                                    ? "dimension"
                                    : "aggregate");
                                setEditingSortOrder(metric.sort_order);
                                setSelectedMetricKey(metricKey);
                                form.setFieldsValue({
                                  display_mode: metricDisplayMode,
                                  aggregate_type: metric.aggregate_type ?? "sum",
                                  dimensions: metric.dimensions ?? {},
                                  condition_filter:
                                    metric.condition_filter?.length
                                      ? metric.condition_filter
                                      : conditionFilterFromDimensions(
                                        metric.dimensions,
                                      ),
                                });
                                setThresholds(
                                  buildThresholdDraftFromMetric(metric),
                                );
                                const option = combinedMetricOptions.find(
                                  (item) =>
                                    `${item.metric_field}::${item.result_table_id}` === metricKey,
                                );
                                if (
                                  metricDisplayMode === "dimension" &&
                                  option &&
                                  (option.supported_dimensions ?? []).length > 0
                                ) {
                                  const dimensionIds = (
                                    metric.condition_filter?.length
                                      ? metric.condition_filter
                                      : conditionFilterFromDimensions(
                                        metric.dimensions,
                                      )
                                  ).map((item) => item.dimension_id);
                                  if (dimensionIds.length > 0) {
                                    void onLoadDimensionValues?.(
                                      option,
                                      dimensionIds,
                                    );
                                  }
                                }
                              }}
                            />
                          </Tooltip>
                        )}
                        <Popconfirm
                          title={t(
                            "opsAnalysis.networkTopology.node.removeMetricTitle",
                          )}
                          okText={t(
                            "opsAnalysis.networkTopology.actions.delete",
                          )}
                          cancelText={t(
                            "opsAnalysis.networkTopology.actions.cancel",
                          )}
                          okButtonProps={{ danger: true }}
                          disabled={readonly}
                          onConfirm={() => onRemoveMetric(metric.sort_order)}
                        >
                          <Button
                            size="small"
                            type="text"
                            danger
                            icon={<DeleteOutlined />}
                            disabled={readonly}
                          />
                        </Popconfirm>
                      </div>
                      {!isEditing && (
                        <div
                          style={{
                            display: "flex",
                            alignItems: "center",
                            gap: 8,
                            flexWrap: "wrap",
                            marginTop: 9,
                          }}
                        >
                          {thresholdPreviewItems.length === 0 && (
                            <span style={{ color: "#94a3b8", fontSize: 11 }}>
                              {t(
                                "opsAnalysis.networkTopology.node.noThresholds",
                              )}
                            </span>
                          )}
                          {thresholdPreviewItems.map((threshold, thresholdIndex) => (
                            <span
                              key={`${threshold.value}-${threshold.color}-${thresholdIndex}`}
                              style={{
                                display: "inline-flex",
                                alignItems: "center",
                                gap: 5,
                                color: "#64748b",
                                fontSize: 11,
                                lineHeight: "16px",
                              }}
                            >
                              <span
                                aria-hidden="true"
                                style={{
                                  width: 7,
                                  height: 7,
                                  borderRadius: "50%",
                                  background: threshold.color,
                                  boxShadow:
                                    "0 0 0 1px rgba(15, 23, 42, 0.08)",
                                }}
                              />
                              <span>{threshold.value}</span>
                            </span>
                          ))}
                        </div>
                      )}
                      {isEditing && (
                        <div style={{ marginTop: 8 }}>
                          {renderMetricEditor(
                            () => onSaveEditMetric(metric.sort_order),
                            () => {
                              setEditingSortOrder(null);
                              resetPendingMetric();
                            },
                            "small",
                          )}
                        </div>
                      )}
                    </div>
                  );
                })}
              </Space>
            </div>
          )}

          {!readonly && editingSortOrder === null && (
            <div
              style={{
                marginTop: 12,
                padding: 12,
                border: "1px solid #dce5ed",
                borderRadius: 8,
                background: "#f9fbfc",
              }}
              data-testid="network-node-drawer-add-metric"
            >
              <div style={{ display: "flex", alignItems: "center" }}>
                <strong style={{ flex: 1 }}>
                  {t("opsAnalysis.networkTopology.node.addMetric")}
                </strong>
              </div>
              {!selectedMetricKey ? (
                <div
                  style={{
                    display: "grid",
                    gridTemplateColumns: "52px minmax(0, 1fr)",
                    alignItems: "center",
                    gap: 10,
                  }}
                >
                  <span style={compactLabelStyle}>
                    {t("opsAnalysis.networkTopology.node.labelMetric")}
                  </span>
                  <Select
                    showSearch
                    optionFilterProp="label"
                    filterOption={isMetricOptionMatched}
                    placeholder={t(
                      "opsAnalysis.networkTopology.node.selectMetricPlaceholder",
                    )}
                    loading={metricOptionsLoading}
                    getPopupContainer={(trigger) =>
                      trigger.parentElement ?? document.body
                    }
                    options={metricOptions.map((item) => ({
                      label: item.display_name,
                      value: `${item.metric_field}::${item.result_table_id}`,
                    }))}
                    value={selectedMetricKey ?? undefined}
                    onChange={(value) => onSelectMetric(value)}
                    data-testid="network-node-drawer-metric-select"
                  />
                </div>
              ) : (
                renderMetricEditor(
                  onSaveNewMetric,
                  resetPendingMetric,
                )
              )}
            </div>
          )}
        </>
      )}
    </Drawer>
  );
};

export default NetworkNodeDrawer;
