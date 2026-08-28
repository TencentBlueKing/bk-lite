"use client";

import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Button,
  Descriptions,
  Drawer,
  Input,
  Popconfirm,
  Select,
  Space,
  Tag,
  message,
} from "antd";
import type { ColumnsType } from "antd/es/table";
import CustomTable from "@/components/custom-table";
import { useTranslation } from "@/utils/i18n";
import { useWikiApi } from "@/app/opspilot/api/wiki";
import type {
  BuildAffectedPage,
  BuildMaintenance,
  BuildMaintenanceStage,
  BuildPageAction,
  BuildRecord,
  BuildSourceChunk,
  BuildSourceMaterialTrace,
  BuildSourceTrace,
} from "@/app/opspilot/types/wiki";
import {
  TRIGGER_LABEL,
  STAGE_LABEL,
  BUILD_STATUS_LABEL,
  PAGE_STATUS_LABEL,
  PAGE_TYPE_LABEL,
  formatWikiTime,
} from "./wikiFormat";

const STATUS_COLOR: Record<string, string> = {
  success: "green",
  running: "processing",
  partial: "gold",
  failed: "red",
  cancelled: "default",
};

const PAGE_STATUS_COLOR: Record<string, string> = {
  active: "green",
  archived: "default",
  source_invalid: "red",
};

const AFFECTED_PAGES_MAX_HEIGHT = "calc(100vh - 400px)";
const SOURCE_TRACE_MAX_HEIGHT = "calc(100vh - 460px)";

const MAINTENANCE_STAGE_LABEL: Record<string, string> = {
  relations: "wiki.maintenanceRelations",
  page_embedding: "wiki.maintenancePageEmbedding",
  chunk_embedding: "wiki.maintenanceChunkEmbedding",
  check_sweep: "wiki.maintenanceCheckSweep",
  deleted_page_prune: "wiki.maintenanceDeletedPagePrune",
};

const MAINTENANCE_STATUS_LABEL: Record<string, string> = {
  success: "wiki.maintenanceSuccess",
  partial: "wiki.maintenancePartial",
  failed: "wiki.maintenanceFailed",
  skipped: "wiki.maintenanceSkipped",
};

const MAINTENANCE_STATUS_COLOR: Record<string, string> = {
  success: "green",
  partial: "gold",
  failed: "red",
  skipped: "default",
};

const MAINTENANCE_REASON_LABEL: Record<string, string> = {
  prune_deleted_pages_disabled: "wiki.maintenancePruneDisabled",
  generation_relations_already_materialized:
    "wiki.maintenanceRelationsAlreadyMaterialized",
};

const MAINTENANCE_STAGE_LABEL_EXTRA: Record<string, string> = {
  cascade: "wiki.maintenanceCascade",
};

const RETRYABLE_MAINTENANCE_STATUS = new Set(["partial", "failed"]);
const FULL_RETRY_TRIGGERS = new Set(["rebuild", "material", "material_update"]);

// 计数键 → 中文标签 + 配色(避免直接暴露 {"new":0,...} 这类 JSON,用户看不懂)
const COUNT_META: Record<string, { key: string; color: string }> = {
  new: { key: "wiki.countNew", color: "green" },
  updated: { key: "wiki.countUpdated", color: "blue" },
  unchanged: { key: "wiki.countUnchanged", color: "default" },
  pending_review: { key: "wiki.countPendingReview", color: "gold" },
  processed: { key: "wiki.countProcessed", color: "blue" },
  failed: { key: "wiki.countFailed", color: "red" },
  skipped_unchanged: { key: "wiki.countSkippedUnchanged", color: "default" },
  removed: { key: "wiki.countRemoved", color: "red" },
  archived: { key: "wiki.countArchived", color: "default" },
  restored: { key: "wiki.countRestored", color: "blue" },
  candidate: { key: "wiki.countCandidate", color: "gold" },
};

const formatBuildErrorRaw = (item: unknown): string => {
  if (typeof item === "string") return item;
  if (item && typeof item === "object") {
    const row = item as Record<string, unknown>;
    const message =
      (typeof row.message === "string" && row.message) ||
      (typeof row.error === "string" && row.error) ||
      "";
    const name = typeof row.name === "string" ? row.name : "";
    const code = typeof row.code === "string" ? row.code : "";
    if (code && message) return `${code}: ${message}`;
    if (name && message) return `${name}: ${message}`;
    if (message) return message;
    if (code) return code;
    if (name) return name;
  }
  try {
    return JSON.stringify(item);
  } catch {
    return String(item);
  }
};

/** 后端 errors 常为 "code: message"；映射为用户可读文案。 */
const BUILD_ERROR_I18N: Record<string, string> = {
  base_generation_conflict: "wiki.buildErrorActivationConflict",
  structure_revision_conflict: "wiki.buildErrorActivationConflict",
  structure_version_conflict: "wiki.buildErrorActivationConflict",
  "generation 激活竞争失败": "wiki.buildErrorActivationConflict",
  candidate_not_ready: "wiki.buildErrorCandidateNotReady",
  candidate_incomplete: "wiki.buildErrorCandidateIncomplete",
  candidate_already_active: "wiki.buildErrorCandidateAlreadyActive",
  candidate_structure_mismatch: "wiki.buildErrorStructureMismatch",
  structure_fingerprint_mismatch: "wiki.buildErrorStructureMismatch",
  candidate_base_generation_mismatch: "wiki.buildErrorBaseMismatch",
  candidate_base_generation_cycle: "wiki.buildErrorBaseMismatch",
  maintenance_stage_failed: "wiki.buildErrorMaintenanceStageFailed",
};

/** 需要保留后端明细的错误码（只替换 code 前缀）。 */
const BUILD_ERROR_KEEP_DETAIL = new Set(["maintenance_stage_failed"]);

/** 历史英文异常串兜底映射（新写入已由后端人话化）。 */
const localizeMaintenanceStageError = (
  raw: string,
  translate: (key: string, fallback?: string) => string,
): string => {
  const text = (raw || "").trim();
  if (!text) return translate("wiki.maintenanceErrorGeneric", "维护阶段执行失败");
  if (/timeout|timed?\s*out|time[_\s-]?out|deadline exceeded/i.test(text)) {
    return translate("wiki.maintenanceErrorTimeout", "连接超时");
  }
  if (
    /connection\s*(refused|reset|aborted|error)|connect(ion)?\s*(failed|error)|max retries exceeded|network is unreachable|name or service not known/i.test(
      text,
    )
  ) {
    return translate("wiki.maintenanceErrorConnection", "无法连接服务");
  }
  if (/unauthorized|forbidden|invalid\s*api\s*key|authentication|\b401\b|\b403\b/i.test(text)) {
    return translate("wiki.maintenanceErrorAuth", "认证失败，请检查模型配置");
  }
  if (/rate\s*limit|too many requests|\b429\b|quota\s*exceeded/i.test(text)) {
    return translate("wiki.maintenanceErrorRateLimit", "请求过于频繁");
  }
  if (/internal server error|bad gateway|service unavailable|gateway timeout|\b502\b|\b503\b|\b504\b/i.test(text)) {
    return translate("wiki.maintenanceErrorUpstream", "上游服务异常");
  }
  if (/embed|embedding|\/v1\/embeddings/i.test(text)) {
    return translate("wiki.maintenanceErrorEmbedding", "索引服务调用失败");
  }
  // 已是中文人话则原样展示；其它未知英文统一兜底
  if (/[\u4e00-\u9fff]/.test(text)) {
    // 兼容历史「原因 + 请稍后重试」写法，展示时去掉建议尾句
    return text.replace(/[，,]?\s*请稍后重试\s*$/u, "");
  }
  return translate("wiki.maintenanceErrorGeneric", "维护阶段执行失败");
};

const localizeBuildError = (
  item: unknown,
  translate: (key: string, fallback?: string) => string,
): string => {
  const raw = formatBuildErrorRaw(item).trim();
  if (!raw) return "--";
  const matched = /^([a-z0-9_]+):\s*(.*)$/i.exec(raw);
  if (matched) {
    const code = matched[1].toLowerCase();
    const message = matched[2].trim();
    const byCode = BUILD_ERROR_I18N[code];
    if (byCode) {
      if (BUILD_ERROR_KEEP_DETAIL.has(code) && message) {
        return localizeMaintenanceStageError(message, translate);
      }
      return translate(byCode);
    }
    const byMessage = BUILD_ERROR_I18N[message];
    if (byMessage) return translate(byMessage);
  }
  const byRaw = BUILD_ERROR_I18N[raw];
  if (byRaw) return translate(byRaw);
  return localizeMaintenanceStageError(raw, translate);
};

const ACTION_META: Record<string, { key: string; color: string }> = {
  new: { key: "wiki.countNew", color: "green" },
  updated: { key: "wiki.countUpdated", color: "blue" },
  unchanged: { key: "wiki.countUnchanged", color: "default" },
  pending_review: { key: "wiki.countPendingReview", color: "gold" },
};

// 构建记录工作区(spec 4.4):长期记录 + 详情(输入版本/受影响页/错误)+ 重试/继续/取消/查看结果
const BuildRecordTab: React.FC<{ kbId: number }> = ({ kbId }) => {
  const { t } = useTranslation();
  const {
    fetchBuildRecords,
    fetchBuildRecord,
    retryBuild,
    retryBuildMaintenance,
    cancelBuild,
  } = useWikiApi();
  const [data, setData] = useState<BuildRecord[]>([]);
  const [loading, setLoading] = useState(false);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [total, setTotal] = useState(0);
  const [detail, setDetail] = useState<BuildRecord | null>(null);
  const [statusFilter, setStatusFilter] = useState("");
  const [materialNameInput, setMaterialNameInput] = useState("");
  const [materialNameFilter, setMaterialNameFilter] = useState("");
  const pollingInFlightRef = useRef(false);

  const load = useCallback(async (options?: { silent?: boolean }) => {
    const silent = Boolean(options?.silent);
    if (!silent) {
      setLoading(true);
    }
    try {
      const res = await fetchBuildRecords(kbId, {
        page,
        page_size: pageSize,
        status: statusFilter || undefined,
        material_name: materialNameFilter || undefined,
      });
      setData(res.items);
      setTotal(res.count);
    } finally {
      if (!silent) {
        setLoading(false);
      }
    }
  }, [kbId, page, pageSize, statusFilter, materialNameFilter]);

  useEffect(() => {
    void load();
  }, [load]);

  // 有 running 记录时每 3s 静默刷新进度，不刷表格 loading；全部结束自动停止
  useEffect(() => {
    if (!data.some((b) => b.status === "running")) return;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      if (!pollingInFlightRef.current) {
        pollingInFlightRef.current = true;
        try {
          await load({ silent: true });
        } catch {
          // 后台刷新失败时保留当前数据，下一轮继续重试。
        } finally {
          pollingInFlightRef.current = false;
        }
      }
      if (!cancelled) timer = setTimeout(poll, 3000);
    };
    timer = setTimeout(poll, 3000);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [data, load]);

  const openDetail = async (id: number) =>
    setDetail(await fetchBuildRecord(id));
  const handleRetry = async (id: number) => {
    await retryBuild(id);
    message.success(t("wiki.saveSuccess"));
    load();
  };
  const handleMaintenanceRetry = async (id: number, stages?: string[]) => {
    const next = await retryBuildMaintenance(id, stages);
    message.success(t("wiki.maintenanceRetryDone"));
    setDetail((current) => (current?.id === id ? next : current));
    load();
  };
  const canRetryMaintenance = (record: BuildRecord) =>
    RETRYABLE_MAINTENANCE_STATUS.has(record.maintenance?.status || "") &&
    !!(record.affected_pages || []).length;
  const canFullRetry = (record: BuildRecord) =>
    ["failed", "partial", "cancelled"].includes(record.status) &&
    FULL_RETRY_TRIGGERS.has(record.trigger || "");
  const canRetry = (record: BuildRecord) =>
    canRetryMaintenance(record) || canFullRetry(record);
  const handleSmartRetry = async (record: BuildRecord) => {
    // 列表统一「重试」：能重跑维护就只重维护，否则整段重试
    if (canRetryMaintenance(record)) {
      await handleMaintenanceRetry(record.id);
      return;
    }
    await handleRetry(record.id);
  };
  const handleCancel = async (id: number) => {
    await cancelBuild(id);
    message.success(t("wiki.saveSuccess"));
    load();
  };
  const resetFilterPage = () => setPage(1);
  const handleStatusFilterChange = (value: string) => {
    setStatusFilter(value || "");
    resetFilterPage();
  };
  const applyMaterialNameFilter = (value: string) => {
    setMaterialNameInput(value);
    setMaterialNameFilter(value.trim());
    resetFilterPage();
  };

  const buildStatusOptions = useMemo(
    () => [
      { value: "", label: t("wiki.buildRecordStatusAll") },
      ...Object.entries(BUILD_STATUS_LABEL).map(([value, labelKey]) => ({
        value,
        label: t(labelKey),
      })),
    ],
    [t],
  );

  // 计数渲染:仅展示非零项为标签(新增 6 / 修改 3 …);全为 0 显示"无变更"
  const renderCounts = (c?: Record<string, number>) => {
    const entries = Object.entries(c || {}).filter(([, v]) => v);
    if (!entries.length)
      return (
        <span className="text-[var(--color-text-4)]">{t("wiki.noChange")}</span>
      );
    return (
      <Space size={[4, 4]} wrap>
        {entries.map(([k, v]) => {
          const meta = COUNT_META[k];
          return (
            <Tag key={k} color={meta?.color || "default"} className="m-0">
              {meta ? t(meta.key) : k} {v}
            </Tag>
          );
        })}
      </Space>
    );
  };

  const labelOf = (map: Record<string, string>, v: string) =>
    map[v] ? t(map[v]) : v || "--";

  const renderMaintenanceStage = (
    stageKey: string,
    stage: BuildMaintenanceStage,
  ) => {
    const status = stage.status || "";
    return (
      <div
        key={stageKey}
        className="min-w-0 rounded-md border border-[var(--color-border-2)] bg-[var(--color-fill-1)] px-2 py-1.5"
      >
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="break-words text-sm font-medium text-[var(--color-text-1)]">
            {labelOf(
              { ...MAINTENANCE_STAGE_LABEL, ...MAINTENANCE_STAGE_LABEL_EXTRA },
              stageKey,
            )}
          </span>
          <Tag
            color={MAINTENANCE_STATUS_COLOR[status] || "default"}
            className="m-0"
          >
            {labelOf(MAINTENANCE_STATUS_LABEL, status)}
          </Tag>
          {typeof stage.count === "number" && (
            <Tag className="m-0">
              {t("wiki.maintenanceStageCount", "数量 {count}", {
                count: stage.count,
              })}
            </Tag>
          )}
          {detail && stage.status === "failed" && (
            <Button
              type="link"
              size="small"
              className="h-auto p-0"
              onClick={() => handleMaintenanceRetry(detail.id, [stageKey])}
            >
              {t("wiki.maintenanceRetryStage")}
            </Button>
          )}
        </div>
        {stage.reason && (
          <div className="mt-1 break-words text-xs text-[var(--color-text-3)]">
            {labelOf(MAINTENANCE_REASON_LABEL, stage.reason)}
          </div>
        )}
        {stage.error && (
          <div className="mt-1 break-words text-xs text-red-500">
            {localizeMaintenanceStageError(stage.error, t)}
          </div>
        )}
      </div>
    );
  };

  const renderMaintenance = (maintenance?: BuildMaintenance) => {
    const stages = Object.entries(maintenance?.stages || {});
    if (!maintenance || !stages.length)
      return <span className="text-[var(--color-text-4)]">--</span>;
    return (
      <div className="flex flex-col gap-2">
        <Space size={[4, 4]} wrap>
          {maintenance.status && (
            <Tag
              color={MAINTENANCE_STATUS_COLOR[maintenance.status] || "default"}
              className="m-0"
            >
              {labelOf(MAINTENANCE_STATUS_LABEL, maintenance.status)}
            </Tag>
          )}
          {maintenance.event && (
            <Tag className="m-0">
              {labelOf(TRIGGER_LABEL, maintenance.event)}
            </Tag>
          )}
        </Space>
        <div className="flex flex-col gap-1.5">
          {stages.map(([stageKey, stage]) =>
            renderMaintenanceStage(stageKey, stage),
          )}
        </div>
      </div>
    );
  };

  const renderAffectedPages = (
    pages?: BuildAffectedPage[],
    pageIds?: number[],
  ) => {
    const existingPages = pages || [];
    if (existingPages.length) {
      return (
        <div
          className="flex flex-col gap-2 overflow-auto pr-1"
          style={{ maxHeight: AFFECTED_PAGES_MAX_HEIGHT }}
        >
          {existingPages.map((pageInfo) => (
            <div
              key={pageInfo.id}
              className="min-w-0 rounded-md border border-[var(--color-border-2)] bg-[var(--color-fill-1)] px-2 py-1.5"
            >
              <div className="break-words text-sm font-medium text-[var(--color-text-1)]">
                {pageInfo.title || `#${pageInfo.id}`}
              </div>
              <Space size={[4, 4]} wrap className="mt-1">
                <Tag className="m-0">#{pageInfo.id}</Tag>
                {pageInfo.page_type && (
                  <Tag className="m-0">
                    {labelOf(PAGE_TYPE_LABEL, pageInfo.page_type)}
                  </Tag>
                )}
                {pageInfo.status && (
                  <Tag
                    color={PAGE_STATUS_COLOR[pageInfo.status] || "default"}
                    className="m-0"
                  >
                    {labelOf(PAGE_STATUS_LABEL, pageInfo.status)}
                  </Tag>
                )}
              </Space>
            </div>
          ))}
        </div>
      );
    }

    const fallbackPageIds = pageIds || [];
    if (!fallbackPageIds.length)
      return <span className="text-[var(--color-text-4)]">--</span>;
    return (
      <Space size={[4, 4]} wrap>
        {fallbackPageIds.map((pageId) => (
          <Tag key={pageId} className="m-0">
            #{pageId}
          </Tag>
        ))}
      </Space>
    );
  };

  const renderActionTag = (action: string) => {
    const meta = ACTION_META[action];
    return (
      <Tag color={meta?.color || "default"} className="m-0">
        {meta ? t(meta.key) : action}
      </Tag>
    );
  };

  const renderSourceChunk = (chunk: BuildSourceChunk) => (
    <div
      key={chunk.index}
      className="min-w-0 rounded-md border border-[var(--color-border-2)] bg-[var(--color-fill-1)] px-2 py-1.5"
    >
      <Space size={[4, 4]} wrap>
        <Tag className="m-0">
          {t("wiki.sourceChunk")} #{chunk.index + 1}
        </Tag>
        <Tag className="m-0">
          {chunk.start}-{chunk.end}
        </Tag>
      </Space>
      <div className="mt-1 whitespace-pre-wrap break-words text-xs text-[var(--color-text-3)]">
        {chunk.preview || "--"}
      </div>
    </div>
  );

  const renderPageAction = (action: BuildPageAction, index: number) => {
    const locator = action.source_locator || {};
    return (
      <div
        key={`${action.page_id}-${action.action}-${index}`}
        className="min-w-0 rounded-md border border-[var(--color-border-2)] bg-[var(--color-fill-1)] px-2 py-1.5"
      >
        <div className="break-words text-sm font-medium text-[var(--color-text-1)]">
          {action.title || `#${action.page_id}`}
        </div>
        <Space size={[4, 4]} wrap className="mt-1">
          <Tag className="m-0">#{action.page_id}</Tag>
          {action.page_type && (
            <Tag className="m-0">
              {labelOf(PAGE_TYPE_LABEL, action.page_type)}
            </Tag>
          )}
          {renderActionTag(action.action)}
          {typeof locator.chunk_index === "number" && (
            <Tag className="m-0">
              {t("wiki.sourceChunk")} #{locator.chunk_index + 1}
            </Tag>
          )}
        </Space>
        {locator.snippet && (
          <div className="mt-1 whitespace-pre-wrap break-words text-xs text-[var(--color-text-3)]">
            {locator.snippet}
          </div>
        )}
      </div>
    );
  };

  const renderSourceTraceSections = (
    chunks: BuildSourceChunk[],
    pageActions: BuildPageAction[],
  ) => (
    <>
      {!!pageActions.length && (
        <div className="flex flex-col gap-1.5">
          <div className="text-xs text-[var(--color-text-3)]">
            {t("wiki.pageActions")}
          </div>
          {pageActions.map(renderPageAction)}
        </div>
      )}
      {!!chunks.length && (
        <div className="flex flex-col gap-1.5">
          <div className="text-xs text-[var(--color-text-3)]">
            {t("wiki.sourceChunks")}
          </div>
          {chunks.map(renderSourceChunk)}
        </div>
      )}
    </>
  );

  const renderSourceMaterialTrace = (
    materialTrace: BuildSourceMaterialTrace,
  ) => (
    <div
      key={materialTrace.material_id}
      className="min-w-0 border-l-2 border-[var(--color-border-2)] pl-2"
    >
      <Space size={[4, 4]} wrap>
        <Tag className="m-0">{t("wiki.sourceMaterial")}</Tag>
        <Tag className="m-0">#{materialTrace.material_id}</Tag>
        <span className="break-words text-sm font-medium text-[var(--color-text-1)]">
          {materialTrace.material_name}
        </span>
      </Space>
      <div className="mt-2 flex flex-col gap-2">
        {renderSourceTraceSections(
          materialTrace.chunks || [],
          materialTrace.page_actions || [],
        )}
      </div>
    </div>
  );

  const renderSourceTrace = (trace?: BuildSourceTrace) => {
    const chunks = trace?.chunks || [];
    const pageActions = trace?.page_actions || [];
    const materials = trace?.materials || [];
    if (!chunks.length && !pageActions.length && !materials.length)
      return <span className="text-[var(--color-text-4)]">--</span>;
    return (
      <div
        className="flex flex-col gap-3 overflow-auto pr-1"
        style={{ maxHeight: SOURCE_TRACE_MAX_HEIGHT }}
      >
        {!!materials.length && (
          <div className="flex flex-col gap-1.5">
            <div className="text-xs text-[var(--color-text-3)]">
              {t("wiki.sourceMaterials")}
            </div>
            {materials.map(renderSourceMaterialTrace)}
          </div>
        )}
        {renderSourceTraceSections(chunks, pageActions)}
      </div>
    );
  };

  const buildTargetLabel = (record: BuildRecord) => {
    if (record.input_label) return record.input_label;
    if (record.trigger === "rebuild") return t("wiki.buildTargetWholeKb");
    if (record.trigger === "material_queue") return t("wiki.buildTargetQueue");
    const materialId = record.inputs?.material_id;
    if (materialId != null && materialId !== "") return `#${materialId}`;
    return "--";
  };

  // 资料列不设 width，吃满剩余宽度；状态/计数/时间/操作固定窄列，避免均分撑出大空白
  const columns: ColumnsType<BuildRecord> = [
    {
      title: t("wiki.buildTarget"),
      key: "buildTarget",
      ellipsis: true,
      render: (_: unknown, record) => (
        <div className="min-w-0">
          <div
            className="truncate font-medium text-[var(--color-text-1)]"
            title={buildTargetLabel(record)}
          >
            {buildTargetLabel(record)}
          </div>
          <div className="truncate text-xs text-[var(--color-text-3)]">
            {labelOf(TRIGGER_LABEL, record.trigger)}
          </div>
        </div>
      ),
    },
    {
      title: t("wiki.status"),
      dataIndex: "status",
      key: "status",
      width: 110,
      render: (s: string) => (
        <Tag color={STATUS_COLOR[s] || "default"}>
          {labelOf(BUILD_STATUS_LABEL, s)}
        </Tag>
      ),
    },
    {
      title: t("wiki.counts"),
      dataIndex: "counts",
      key: "counts",
      width: 220,
      render: (c: Record<string, number>) => renderCounts(c),
    },
    {
      title: t("wiki.buildTimeStart"),
      dataIndex: "created_at",
      key: "created_at",
      width: 170,
      render: (v: string) => formatWikiTime(v),
    },
    {
      title: t("wiki.buildTimeEnd"),
      dataIndex: "updated_at",
      key: "updated_at",
      width: 170,
      render: (v: string, record) =>
        record.status === "running" ? "--" : formatWikiTime(v),
    },
    {
      title: t("common.actions"),
      key: "action",
      width: 180,
      render: (_: unknown, r) => (
        <Space>
          <Button type="link" size="small" onClick={() => openDetail(r.id)}>
            {t("wiki.viewResult")}
          </Button>
          {canRetry(r) && (
            <Button
              type="link"
              size="small"
              onClick={() => handleSmartRetry(r)}
            >
              {t("wiki.retry")}
            </Button>
          )}
          {r.status === "running" && (
            <Popconfirm
              title={t("wiki.cancelConfirm")}
              onConfirm={() => handleCancel(r.id)}
            >
              <Button type="link" size="small" danger>
                {t("wiki.cancel")}
              </Button>
            </Popconfirm>
          )}
        </Space>
      ),
    },
  ];

  return (
    // h-full + flex:给表格一个确定高度的父级,使 CustomTable 开启分页时自动算出的 scroll.y 稳定(否则只显示 1 行)
    <div className="h-full flex flex-col">
      <div className="mb-3 flex flex-wrap items-center justify-end gap-2">
        <Select
          value={statusFilter || undefined}
          options={buildStatusOptions.filter((item) => item.value !== "")}
          allowClear
          placeholder={t("wiki.buildRecordStatusAll")}
          className="w-[140px]"
          onChange={(value) => handleStatusFilterChange(value || "")}
        />
        <Input.Search
          allowClear
          enterButton
          value={materialNameInput}
          placeholder={t("wiki.filterMaterialNamePlaceholder")}
          className="w-60"
          onChange={(event) => setMaterialNameInput(event.target.value)}
          onSearch={applyMaterialNameFilter}
        />
      </div>
      <div className="flex-1 min-h-0">
        <CustomTable<BuildRecord>
          rowKey="id"
          loading={loading}
          columns={columns}
          dataSource={data}
          autoScrollX={false}
          tableLayout="fixed"
          pagination={{
            current: page,
            pageSize,
            total,
            showSizeChanger: true,
            onChange: (p, ps) => {
              setPage(p);
              setPageSize(ps);
            },
          }}
          scroll={{ x: undefined }}
        />
      </div>
      <Drawer
        title={`${t("wiki.buildRecord")} #${detail?.id ?? ""}`}
        open={!!detail}
        width={720}
        onClose={() => setDetail(null)}
      >
        {detail && (
          <Descriptions
            column={1}
            bordered
            size="small"
            labelStyle={{ width: 144, whiteSpace: "nowrap" }}
            contentStyle={{ minWidth: 0 }}
          >
            <Descriptions.Item label={t("wiki.buildTarget")}>
              {buildTargetLabel(detail)}
            </Descriptions.Item>
            <Descriptions.Item label={t("wiki.buildActionType")}>
              {labelOf(TRIGGER_LABEL, detail.trigger)}
            </Descriptions.Item>
            <Descriptions.Item label={t("wiki.operator")}>
              {detail.operator || "--"}
            </Descriptions.Item>
            <Descriptions.Item label={t("wiki.sourceTrace")}>
              {renderSourceTrace(detail.inputs?.source_trace)}
            </Descriptions.Item>
            <Descriptions.Item label={t("wiki.status")}>
              <Tag color={STATUS_COLOR[detail.status] || "default"}>
                {labelOf(BUILD_STATUS_LABEL, detail.status)}
              </Tag>
            </Descriptions.Item>
            {detail.status === "running" && (
              <Descriptions.Item label={t("wiki.stage")}>
                {labelOf(STAGE_LABEL, detail.stage)} ({detail.progress ?? 0}%)
              </Descriptions.Item>
            )}
            <Descriptions.Item label={t("wiki.buildStartedAt")}>
              {formatWikiTime(detail.created_at)}
            </Descriptions.Item>
            <Descriptions.Item label={t("wiki.buildFinishedAt")}>
              {detail.status === "running"
                ? "--"
                : formatWikiTime(detail.updated_at)}
            </Descriptions.Item>
            <Descriptions.Item label={t("wiki.counts")}>
              {renderCounts(detail.counts)}
            </Descriptions.Item>
            <Descriptions.Item label={t("wiki.maintenanceResult")}>
              {renderMaintenance(detail.maintenance)}
            </Descriptions.Item>
            <Descriptions.Item label={t("wiki.affectedPages")}>
              {renderAffectedPages(
                detail.affected_page_details,
                detail.affected_pages,
              )}
            </Descriptions.Item>
            <Descriptions.Item label={t("wiki.errors")}>
              {(detail.errors || []).length ? (
                <div className="space-y-1">
                  {(detail.errors || []).map((item, index) => {
                    const text = localizeBuildError(item, t);
                    return (
                      <div
                        key={`${index}-${text}`}
                        className="whitespace-pre-wrap break-words text-[var(--color-error)]"
                      >
                        {text}
                      </div>
                    );
                  })}
                </div>
              ) : (
                "--"
              )}
            </Descriptions.Item>
          </Descriptions>
        )}
      </Drawer>
    </div>
  );
};

export default BuildRecordTab;
