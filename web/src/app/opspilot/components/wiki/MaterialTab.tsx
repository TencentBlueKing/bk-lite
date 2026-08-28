"use client";

import React, { useCallback, useEffect, useRef, useState } from "react";
import {
  Alert,
  App,
  Button,
  Descriptions,
  Form,
  Input,
  InputNumber,
  List,
  Modal,
  Select,
  Space,
  Spin,
  Switch,
  Tag,
  Upload,
} from "antd";
import type { ColumnsType } from "antd/es/table";
import type { UploadFile } from "antd/es/upload/interface";
import { LoadingOutlined, UploadOutlined } from "@ant-design/icons";
import { useRouter, useSearchParams } from "next/navigation";
import CustomTable from "@/components/custom-table";
import CompactEmptyState from "@/components/compact-empty-state";
import {
  buildWikiMaterialDetailPath,
  buildWikiMaterialListPath,
} from "@/app/opspilot/utils/wikiMaterialRoutes";
import { useTranslation } from "@/utils/i18n";
import { HandledRequestError } from "@/utils/request";
import { useWikiApi } from "@/app/opspilot/api/wiki";
import {
  Material,
  MaterialBatchUploadEntry,
  MaterialDeleteImpact,
  MaterialInfo,
  MaterialType,
  MaterialUpdateImpact,
  WikiDirectoryTreeResult,
} from "@/app/opspilot/types/wiki";
import MaterialDetailPanel from "./MaterialDetailPanel";
import WikiDirectorySelect from "./WikiDirectorySelect";
import {
  MATERIAL_DISPLAY_STATUS_OPTIONS,
  MATERIAL_STATUS_META,
  formatWikiDuration,
  formatWikiTime,
  materialDisplayStatus,
  type MaterialDisplayStatus,
} from "./wikiFormat";
const MATERIAL_TYPE_KEY: Record<MaterialType, string> = {
  file: "wiki.materialFile",
  text: "wiki.materialText",
  web: "wiki.materialWeb",
};
const IN_PROGRESS = ["queued", "parsing", "building"];
const SUPPORTED_FILE_EXTENSIONS = [
  ".pdf",
  ".docx",
  ".pptx",
  ".xlsx",
  ".xls",
  ".msg",
  ".html",
  ".htm",
  ".txt",
  ".md",
  ".markdown",
  ".csv",
  ".json",
  ".xml",
  ".jpg",
  ".jpeg",
  ".png",
  ".gif",
  ".bmp",
  ".tiff",
  ".tif",
  ".webp",
  ".zip",
  ".epub",
];
const FILE_ACCEPT = SUPPORTED_FILE_EXTENSIONS.join(",");
const SHOW_MATERIAL_REINDEX_ACTION = false;
const LARGE_FILE_WARNING_BYTES = 500 * 1024 * 1024;

interface MaterialLoadOptions {
  silent?: boolean;
}

const MaterialTab: React.FC<{ kbId: number }> = ({ kbId }) => {
  const { t } = useTranslation();
  const router = useRouter();
  const searchParams = useSearchParams();
  const materialIdParam = Number(searchParams?.get("materialId") || 0);
  const materialId =
    Number.isFinite(materialIdParam) && materialIdParam > 0
      ? materialIdParam
      : null;
  const {
    fetchKnowledgeBase,
    fetchMaterials,
    fetchDirectoryTree,
    fetchMaterialInfo,
    fetchMaterialDeleteImpact,
    fetchMaterialUpdateImpact,
    createMaterial,
    updateMaterial,
    createMaterialFile,
    batchCreateMaterials,
    deleteMaterial,
    buildMaterial,
    batchBuildMaterials,
    proposeUpdate,
    reindexMaterial,
  } = useWikiApi();
  const { message } = App.useApp();
  const [form] = Form.useForm();
  const [data, setData] = useState<Material[]>([]);
  const [loading, setLoading] = useState(false);
  const [selectedRowKeys, setSelectedRowKeys] = useState<React.Key[]>([]);
  const [batchBuilding, setBatchBuilding] = useState(false);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [total, setTotal] = useState(0);
  const [nameDraft, setNameDraft] = useState("");
  const [statusDraft, setStatusDraft] = useState<MaterialDisplayStatus[]>([]);
  const [nameQuery, setNameQuery] = useState("");
  const [statusGroups, setStatusGroups] = useState<MaterialDisplayStatus[]>([]);
  const loadRequestSequenceRef = useRef(0);
  const loadingRequestSequenceRef = useRef<number | null>(null);
  const silentPageCorrectionRef = useRef(false);
  const pendingSilentRefreshRef = useRef(false);
  const pollingRequestInFlightRef = useRef(false);
  const loadScopeRef = useRef({
    kbId,
    page,
    pageSize,
    nameQuery,
    statusGroups: statusGroups as MaterialDisplayStatus[],
  });
  loadScopeRef.current = { kbId, page, pageSize, nameQuery, statusGroups };
  const [open, setOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [editingMaterial, setEditingMaterial] = useState<Material | null>(null);
  const [type, setType] = useState<MaterialType>("text");
  const [fileList, setFileList] = useState<UploadFile[]>([]);
  const [folderImport, setFolderImport] = useState(false);
  const [classificationRootId, setClassificationRootId] = useState<number>();
  const [directoryTree, setDirectoryTree] =
    useState<WikiDirectoryTreeResult | null>(null);
  const [detail, setDetail] = useState<MaterialInfo | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [hasVisionModel, setHasVisionModel] = useState(false);
  const [reindexingMaterialId, setReindexingMaterialId] = useState<
    number | null
  >(null);
  const [deleteImpactVisible, setDeleteImpactVisible] = useState(false);
  const [deleteImpactLoading, setDeleteImpactLoading] = useState(false);
  const [deleteSubmitting, setDeleteSubmitting] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<Material | null>(null);
  const [deleteImpact, setDeleteImpact] = useState<MaterialDeleteImpact | null>(
    null,
  );
  const [updateImpactVisible, setUpdateImpactVisible] = useState(false);
  const [updateImpactLoading, setUpdateImpactLoading] = useState(false);
  const [updateSubmitting, setUpdateSubmitting] = useState(false);
  const [updateTarget, setUpdateTarget] = useState<Material | null>(null);
  const [updateImpact, setUpdateImpact] = useState<MaterialUpdateImpact | null>(
    null,
  );
  const isEditing = Boolean(editingMaterial);

  const load = useCallback(
    async (options: MaterialLoadOptions = {}) => {
      const silent = options.silent ?? false;
      if (silent && loadingRequestSequenceRef.current !== null) {
        pendingSilentRefreshRef.current = true;
        return null;
      }
      const {
        kbId: requestedKbId,
        page: requestedPage,
        pageSize: requestedPageSize,
        nameQuery: requestedNameQuery,
        statusGroups: requestedStatusGroups,
      } = loadScopeRef.current;
      const requestSequence = ++loadRequestSequenceRef.current;
      if (!silent) {
        loadingRequestSequenceRef.current = requestSequence;
        setLoading(true);
      }
      try {
        const res = await fetchMaterials(requestedKbId, {
          page: requestedPage,
          page_size: requestedPageSize,
          ...(requestedNameQuery.trim()
            ? { search: requestedNameQuery.trim() }
            : {}),
          ...(requestedStatusGroups.length
            ? { status_group: requestedStatusGroups.join(",") }
            : {}),
        });
        const currentScope = loadScopeRef.current;
        if (
          requestSequence !== loadRequestSequenceRef.current ||
          currentScope.kbId !== requestedKbId ||
          currentScope.page !== requestedPage ||
          currentScope.pageSize !== requestedPageSize ||
          currentScope.nameQuery !== requestedNameQuery ||
          currentScope.statusGroups.join(",") !==
            requestedStatusGroups.join(",")
        ) {
          return null;
        }

        const lastPage = Math.max(1, Math.ceil(res.count / requestedPageSize));
        setTotal(res.count);
        if (requestedPage > lastPage) {
          loadScopeRef.current = {
            kbId: requestedKbId,
            page: lastPage,
            pageSize: requestedPageSize,
            nameQuery: requestedNameQuery,
            statusGroups: requestedStatusGroups,
          };
          silentPageCorrectionRef.current = silent;
          setPage(lastPage);
          return null;
        }
        setData(res.items);
        return res;
      } finally {
        if (!silent && loadingRequestSequenceRef.current === requestSequence) {
          loadingRequestSequenceRef.current = null;
          setLoading(false);
          if (pendingSilentRefreshRef.current) {
            pendingSilentRefreshRef.current = false;
            void load({ silent: true }).catch(() => undefined);
          }
        }
      }
       
    },
    [kbId, page, pageSize, nameQuery, statusGroups],
  );
  useEffect(() => {
    let active = true;
    setDirectoryTree(null);
    fetchDirectoryTree(kbId)
      .then((result) => {
        if (active) setDirectoryTree(result);
      })
      .catch(() => {
        if (active) setDirectoryTree(null);
      });
    return () => {
      active = false;
    };
     
  }, [kbId]);

  useEffect(() => {
    const silent = silentPageCorrectionRef.current;
    silentPageCorrectionRef.current = false;
    void load({ silent }).catch(() => undefined);
     
  }, [kbId, page, pageSize, nameQuery, statusGroups]);

  useEffect(() => {
    fetchKnowledgeBase(kbId)
      .then((kb) => setHasVisionModel(Boolean(kb.vision_model)))
      .catch(() => setHasVisionModel(false));
     
  }, [kbId]);

  // 排队中 / 构建中(含 parsing) 均静默轮询刷新列表状态。
  useEffect(() => {
    if (!data.some((m) => IN_PROGRESS.includes(m.status || ""))) return;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      if (
        !pollingRequestInFlightRef.current &&
        loadingRequestSequenceRef.current === null
      ) {
        pollingRequestInFlightRef.current = true;
        try {
          await load({ silent: true });
        } catch {
          // 后台刷新失败时保留当前数据，下一轮继续重试。
        } finally {
          pollingRequestInFlightRef.current = false;
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

  const openCreate = () => {
    form.resetFields();
    setEditingMaterial(null);
    setType("file");
    setFileList([]);
    setFolderImport(false);
    setClassificationRootId(undefined);
    form.setFieldsValue({ material_type: "file", ocr_enhance: false });
    setOpen(true);
  };

  const closeMaterialModal = () => {
    if (saving) return;
    setOpen(false);
    setEditingMaterial(null);
  };

  const openEdit = (record: Material) => {
    setEditingMaterial(record);
    setType(record.material_type);
    setFileList([]);
    setFolderImport(false);
    setClassificationRootId(undefined);
    form.resetFields();
    form.setFieldsValue({
      name: record.name,
      material_type: record.material_type,
      text_content: record.text_content ?? "",
      url: record.url ?? "",
      sync_enabled: Boolean(record.sync_policy?.enabled),
      sync_interval_hours: record.sync_policy?.interval_hours ?? 24,
      ocr_enhance: Boolean(record.ocr_enhance),
    });
    setOpen(true);
  };

  const confirmLargeFileUpload = (files: File[]) =>
    new Promise<boolean>((resolve) => {
      Modal.confirm({
        title: t("wiki.largeFileUploadTitle"),
        content: (
          <div>
            <p>{t("wiki.largeFileUploadWarning")}</p>
            <div className="mt-2 max-h-32 overflow-auto text-xs text-gray-500">
              {files.slice(0, 5).map((file) => (
                <div key={file.name + "-" + file.size}>
                  {file.name} ({(file.size / 1024 / 1024).toFixed(1)} MB)
                </div>
              ))}
              {files.length > 5 && <div>…</div>}
            </div>
          </div>
        ),
        okText: t("wiki.continueUpload"),
        cancelText: t("common.cancel"),
        onOk: () => resolve(true),
        onCancel: () => resolve(false),
      });
    });

  const handleSave = async () => {
    const values = await form.validateFields();
    if (!editingMaterial && values.material_type === "file") {
      const largeFiles = fileList
        .map((item) => item.originFileObj as File | undefined)
        .filter((file): file is File =>
          Boolean(file && file.size > LARGE_FILE_WARNING_BYTES),
        );
      if (
        largeFiles.length > 0 &&
        !(await confirmLargeFileUpload(largeFiles))
      ) {
        return;
      }
    }
    setSaving(true);
    try {
      let successMessage = t("wiki.saveSuccess");
      if (editingMaterial) {
        // 编辑任何类型都带上 ocr_enhance:web 含图,text 字段保留一致。
        const common = { ocr_enhance: Boolean(values.ocr_enhance) };
        if (editingMaterial.material_type === "file") {
          await updateMaterial(editingMaterial.id, common);
        } else if (editingMaterial.material_type === "web") {
          await updateMaterial(editingMaterial.id, {
            ...common,
            name: values.name,
            sync_policy: {
              enabled: !!values.sync_enabled,
              interval_hours: values.sync_interval_hours ?? 24,
            },
          });
        } else if (editingMaterial.material_type === "text") {
          await updateMaterial(editingMaterial.id, {
            ...common,
            name: values.name,
            text_content: values.text_content ?? "",
          });
        }
      } else if (values.material_type === "file") {
        const uploads = fileList.reduce<MaterialBatchUploadEntry[]>(
          (result, item) => {
            const file = item.originFileObj as File | undefined;
            if (file) {
              result.push({
                file,
                source_relative_path:
                  file.webkitRelativePath?.trim() || file.name,
              });
            }
            return result;
          },
          [],
        );
        if (!uploads.length) {
          message.error(t("wiki.fileRequired"));
          return;
        }
        if (uploads.length === 1) {
          // 单文件发送完整来源相对路径；来源 identity/folder 由后端确定性生成。
          await createMaterialFile(
            kbId,
            values.name || uploads[0].file.name,
            uploads[0].file,
            Boolean(values.ocr_enhance),
            {
              source_relative_path: uploads[0].source_relative_path,
              classification_root_id: classificationRootId,
            },
          );
        } else {
          // 重复 source_relative_paths 与 files 严格同序，避免同名文件丢失 provenance。
          const result = await batchCreateMaterials(
            kbId,
            uploads,
            Boolean(values.ocr_enhance),
            classificationRootId,
          );
          const failed = result?.errors ?? [];
          if (failed.length) {
            // 部分失败:展示汇总,允许用户从列表中删除失败项
            const preview = failed
              .slice(0, 3)
              .map((f) => `${f.name}: ${f.error}`)
              .join("；");
            const suffix =
              failed.length > 3
                ? `…(共 ${failed.length} 项)`
                : `共 ${failed.length} 项`;
            message.warning(
              `${t("wiki.batchAddMaterialPartial")}: ${suffix}\n${preview}`,
            );
          }
          successMessage = `${t("wiki.batchAddMaterialDone")}: ${result?.items?.length ?? 0}`;
        }
      } else {
        // 网页资料:按站点单独配置同步策略(替代原知识库级别的统一规则)
        const { sync_enabled, sync_interval_hours, ...rest } = values;
        delete rest.ocr_enhance;
        const payload: Partial<Material> = { ...rest, knowledge_base: kbId };
        if (values.material_type === "web") {
          payload.sync_policy = {
            enabled: !!sync_enabled,
            interval_hours: sync_interval_hours ?? 24,
          };
        }
        await createMaterial(payload);
      }
      message.success(successMessage);
      setOpen(false);
      setEditingMaterial(null);
      void load({ silent: true }).catch(() => undefined);
    } finally {
      setSaving(false);
    }
  };

  useEffect(() => {
    if (!materialId) {
      setDetail(null);
      setDetailLoading(false);
      return;
    }
    let active = true;
    setDetailLoading(true);
    void fetchMaterialInfo(materialId)
      .then((info) => {
        if (active) setDetail(info);
      })
      .catch(() => {
        if (active) setDetail(null);
      })
      .finally(() => {
        if (active) setDetailLoading(false);
      });
    return () => {
      active = false;
    };
     
  }, [materialId]);

  const openDetail = (id: number) => {
    router.push(
      buildWikiMaterialDetailPath({
        kbId,
        materialId: id,
        searchParams,
      }),
    );
  };

  const backToList = () => {
    router.push(buildWikiMaterialListPath({ kbId, searchParams }));
  };

  const handleBuild = async (id: number) => {
    try {
      // suppress:业务冲突由本处用 warning 提示,避免拦截器 error + 未捕获 Promise 刷控制台
      await buildMaterial(id, true, { suppressErrorNotification: true });
      message.success(t("wiki.batchBuildDone"));
      void load({ silent: true }).catch(() => undefined);
    } catch (error) {
      if (error instanceof HandledRequestError) {
        if (error.status === 409) {
          message.warning(error.message);
        } else {
          message.error(error.message);
        }
        void load({ silent: true }).catch(() => undefined);
        return;
      }
      message.error(t("common.error"));
    }
  };

  const handleBatchBuild = async () => {
    const ids = selectedRowKeys
      .map((key) => Number(key))
      .filter((id) => Number.isFinite(id) && id > 0);
    if (!ids.length) {
      message.warning(t("wiki.batchBuildEmpty"));
      return;
    }
    setBatchBuilding(true);
    try {
      const result = await batchBuildMaterials(kbId, ids, {
        suppressErrorNotification: true,
      });
      const queuedCount =
        (result.queued?.length || 0) + (result.already_queued?.length || 0);
      message.success(
        `${t("wiki.batchBuildDone")}: ${queuedCount}` +
          (result.in_progress?.length
            ? ` (${t("wiki.statusBuilding")} ${result.in_progress.length})`
            : ""),
      );
      setSelectedRowKeys([]);
      void load({ silent: true }).catch(() => undefined);
    } catch (error) {
      if (error instanceof HandledRequestError) {
        message.error(error.message);
      } else {
        message.error(t("common.error"));
      }
    } finally {
      setBatchBuilding(false);
    }
  };

  const openDeleteImpact = async (record: Material) => {
    setDeleteTarget(record);
    setDeleteImpact(null);
    setDeleteImpactVisible(true);
    setDeleteImpactLoading(true);
    try {
      setDeleteImpact(await fetchMaterialDeleteImpact(record.id));
    } finally {
      setDeleteImpactLoading(false);
    }
  };

  const closeDeleteImpact = () => {
    if (deleteSubmitting) return;
    setDeleteImpactVisible(false);
    setDeleteTarget(null);
    setDeleteImpact(null);
  };

  const handleDelete = async () => {
    if (!deleteTarget) return;
    setDeleteSubmitting(true);
    try {
      await deleteMaterial(deleteTarget.id);
      message.success(t("wiki.deleteSuccess"));
      setDeleteImpactVisible(false);
      setDeleteTarget(null);
      setDeleteImpact(null);
      void load({ silent: true }).catch(() => undefined);
    } finally {
      setDeleteSubmitting(false);
    }
  };

  const openUpdateImpact = async (record: Material) => {
    setUpdateTarget(record);
    setUpdateImpact(null);
    setUpdateImpactVisible(true);
    setUpdateImpactLoading(true);
    try {
      setUpdateImpact(await fetchMaterialUpdateImpact(record.id));
    } finally {
      setUpdateImpactLoading(false);
    }
  };

  const closeUpdateImpact = () => {
    if (updateSubmitting) return;
    setUpdateImpactVisible(false);
    setUpdateTarget(null);
    setUpdateImpact(null);
  };

  const handleProposeUpdate = async () => {
    if (!updateTarget) return;
    setUpdateSubmitting(true);
    try {
      await proposeUpdate(updateTarget.id);
      message.success(t("wiki.proposeUpdateDone"));
      setUpdateImpactVisible(false);
      setUpdateTarget(null);
      setUpdateImpact(null);
      void load({ silent: true }).catch(() => undefined);
    } finally {
      setUpdateSubmitting(false);
    }
  };

  const handleReindexMaterial = async (id: number) => {
    setReindexingMaterialId(id);
    try {
      await reindexMaterial(id);
      message.success(t("wiki.reindexPageDone"));
      void load({ silent: true }).catch(() => undefined);
    } finally {
      setReindexingMaterialId(null);
    }
  };

  const materialTypeLabel = (type: MaterialType) =>
    t(MATERIAL_TYPE_KEY[type] || type);

  const renderImpactPages = (pages: MaterialDeleteImpact["affected_pages"]) => (
    <List
      size="small"
      dataSource={pages}
      locale={{ emptyText: t("wiki.noAffectedPages") }}
      renderItem={(pageItem) => (
        <List.Item>
          <div className="min-w-0">
            <div className="truncate font-medium">{pageItem.title}</div>
            {pageItem.reason && (
              <div className="text-xs text-[var(--color-text-3)] mt-0.5">
                {pageItem.reason}
              </div>
            )}
            <Space size={[4, 4]} wrap className="mt-1">
              <Tag className="m-0">#{pageItem.id}</Tag>
              <Tag className="m-0">{pageItem.page_type}</Tag>
              <Tag className="m-0">{pageItem.status}</Tag>
            </Space>
          </div>
        </List.Item>
      )}
    />
  );

  const versionLabel = (version?: MaterialUpdateImpact["latest_version"]) => {
    if (!version) return "--";
    const hash = version.content_hash ? version.content_hash.slice(0, 8) : "--";
    return `#${version.id} ${hash}`;
  };

  const columns: ColumnsType<Material> = [
    {
      title: t("wiki.name"),
      dataIndex: "name",
      key: "name",
      render: (name: string) => (
        <div className="truncate" title={name}>
          {name}
        </div>
      ),
    },
    {
      title: t("wiki.materialType"),
      dataIndex: "material_type",
      key: "material_type",
      width: 100,
      render: (type: MaterialType) => materialTypeLabel(type),
    },
    {
      title: t("wiki.status"),
      dataIndex: "status",
      key: "status",
      width: 120,
      render: (s: string) => {
        const meta = MATERIAL_STATUS_META[materialDisplayStatus(s)];
        return (
          <Tag
            color={meta?.color || "default"}
            icon={
              IN_PROGRESS.includes(s) ? <LoadingOutlined spin /> : undefined
            }
          >
            {t(meta.key)}
          </Tag>
        );
      },
    },
    {
      title: t("wiki.buildStartedAt"),
      dataIndex: "build_started_at",
      key: "build_started_at",
      width: 170,
      render: (v: string | null | undefined) => formatWikiTime(v),
    },
    {
      title: t("wiki.buildFinishedAt"),
      dataIndex: "build_finished_at",
      key: "build_finished_at",
      width: 170,
      render: (v: string | null | undefined) => formatWikiTime(v),
    },
    {
      title: t("wiki.buildDuration"),
      dataIndex: "build_duration_seconds",
      key: "build_duration_seconds",
      width: 110,
      render: (v: number | null | undefined) => formatWikiDuration(v),
    },
    {
      // AI 解读列只做单行预览:自定义 render 绕过 CustomTable 的 EllipsisWithTooltip,
      // 并 showTitle:false 关闭原生提示——超长内容不再 hover 弹出全文撑出滚动条,完整内容见详情页
      title: t("wiki.aiSummary"),
      dataIndex: "ai_summary",
      key: "ai_summary",
      width: 280,
      ellipsis: { showTitle: false },
      render: (s: string) => (
        <span className="text-[var(--color-text-3)]">{s || "--"}</span>
      ),
    },
    {
      title: t("common.actions"),
      key: "action",
      width: 360,
      render: (_: unknown, record) => {
        const busy = IN_PROGRESS.includes(record.status || "");
        const canBuild =
          !busy && record.status !== "invalid" && record.status !== "queued";
        const canProposeUpdate = record.status === "updated";
        return (
          <Space>
            <Button
              type="link"
              size="small"
              onClick={() => openDetail(record.id)}
            >
              {t("wiki.detail")}
            </Button>
            <Button
              type="link"
              size="small"
              disabled={busy}
              onClick={() => openEdit(record)}
            >
              {t("common.edit")}
            </Button>
            <Button
              type="link"
              size="small"
              disabled={!canBuild}
              onClick={() => handleBuild(record.id)}
            >
              {t("wiki.build")}
            </Button>
            {SHOW_MATERIAL_REINDEX_ACTION && (
              <Button
                type="link"
                size="small"
                disabled={
                  busy ||
                  (reindexingMaterialId !== null &&
                    reindexingMaterialId !== record.id)
                }
                loading={reindexingMaterialId === record.id}
                onClick={() => handleReindexMaterial(record.id)}
              >
                {t("wiki.reindexPage")}
              </Button>
            )}
            {canProposeUpdate && (
              <Button
                type="link"
                size="small"
                disabled={busy}
                onClick={() => openUpdateImpact(record)}
              >
                {t("wiki.proposeUpdate")}
              </Button>
            )}
            <Button
              type="link"
              size="small"
              danger
              disabled={busy}
              onClick={() => openDeleteImpact(record)}
            >
              {t("common.delete")}
            </Button>
          </Space>
        );
      },
    },
  ];

  const applyMaterialFilters = (overrides?: {
    name?: string;
    status?: MaterialDisplayStatus[];
  }) => {
    const nextName = (overrides?.name ?? nameDraft).trim();
    const nextStatus = [...(overrides?.status ?? statusDraft)];
    if (overrides?.name !== undefined) {
      setNameDraft(overrides.name);
    }
    if (overrides?.status !== undefined) {
      setStatusDraft(overrides.status);
    }
    loadScopeRef.current = {
      kbId,
      page: 1,
      pageSize,
      nameQuery: nextName,
      statusGroups: nextStatus,
    };
    setSelectedRowKeys([]);
    setNameQuery(nextName);
    setStatusGroups(nextStatus);
    setPage(1);
  };

  if (materialId) {
    return (
      <div className="flex h-full min-h-0 min-w-0 flex-col overflow-hidden">
        <Spin
          spinning={detailLoading}
          wrapperClassName="flex h-full min-h-0 flex-1 flex-col [&_.ant-spin-container]:flex [&_.ant-spin-container]:h-full [&_.ant-spin-container]:min-h-0 [&_.ant-spin-container]:flex-1 [&_.ant-spin-container]:flex-col"
        >
          {detail ? (
            <MaterialDetailPanel detail={detail} onBack={backToList} />
          ) : (
            !detailLoading && <CompactEmptyState description={t("wiki.empty")} />
          )}
        </Spin>
      </div>
    );
  }

  return (
    <div className="h-full flex flex-col">
      <div className="mb-3 flex shrink-0 flex-wrap items-center justify-end gap-2">
        <Select
          mode="multiple"
          allowClear
          className="min-w-[200px] max-w-full sm:min-w-[240px] sm:max-w-[360px]"
          placeholder={t("wiki.filterStatusAll")}
          value={statusDraft}
          options={MATERIAL_DISPLAY_STATUS_OPTIONS.map((value) => ({
            value,
            label: t(MATERIAL_STATUS_META[value].key),
          }))}
          maxTagCount="responsive"
          onChange={(values: MaterialDisplayStatus[] | undefined) => {
            const next = values || [];
            setStatusDraft(next);
            applyMaterialFilters({
              name: nameDraft,
              status: next,
            });
          }}
        />
        <Input.Search
          allowClear
          enterButton
          className="w-60"
          placeholder={t("wiki.filterNamePlaceholder")}
          value={nameDraft}
          onChange={(event) => setNameDraft(event.target.value)}
          onSearch={(value) =>
            applyMaterialFilters({
              name: value,
              status: statusDraft,
            })
          }
        />
        <Button
          disabled={!selectedRowKeys.length}
          loading={batchBuilding}
          onClick={() => void handleBatchBuild()}
        >
          {t("wiki.batchBuild")}
        </Button>
        <Button type="primary" onClick={openCreate}>
          {t("wiki.addMaterial")}
        </Button>
      </div>
      {/* flex-1 容器给表格确定高度,使分页时 CustomTable 自动算出的 scroll.y 稳定;
          scroll x:undefined 关闭默认按列宽合计强制的横向滚动,列宽自适应容器 */}
      <div className="flex-1 min-h-0">
        <CustomTable<Material>
          rowKey="id"
          loading={loading}
          columns={columns}
          dataSource={data}
          rowSelection={{
            selectedRowKeys,
            onChange: (keys) => setSelectedRowKeys(keys),
            getCheckboxProps: (record) => ({
              disabled: IN_PROGRESS.includes(record.status || ""),
            }),
          }}
          pagination={{
            current: page,
            pageSize,
            total,
            showSizeChanger: true,
            onChange: (p, ps) => {
              loadScopeRef.current = {
                kbId,
                page: p,
                pageSize: ps,
                nameQuery,
                statusGroups,
              };
              setPage(p);
              setPageSize(ps);
            },
          }}
          scroll={{ x: undefined }}
        />
      </div>

      <Modal
        title={t("wiki.deleteImpact")}
        open={deleteImpactVisible}
        onOk={handleDelete}
        okText={t("common.delete")}
        okButtonProps={{
          danger: true,
          disabled: deleteImpactLoading || !deleteImpact,
        }}
        confirmLoading={deleteSubmitting}
        onCancel={closeDeleteImpact}
        maskClosable={false}
        destroyOnHidden
        // 弹窗禁止触底:限制最大高度,主体内部滚动(前端规范:弹窗禁止触底)
        styles={{
          body: {
            maxHeight: "calc(100vh - 280px)",
            overflowY: "auto",
            overflowX: "hidden",
          },
        }}
      >
        {deleteImpactLoading ? (
          <div className="py-6 text-center text-[var(--color-text-3)]">
            <LoadingOutlined spin className="mr-2" />
            {t("wiki.deleteImpactLoading")}
          </div>
        ) : (
          deleteImpact && (
            <>
              <div className="mb-3 text-sm text-[var(--color-text-2)]">
                {t("wiki.deleteImpactTip")}
              </div>
              <Descriptions column={3} bordered size="small">
                <Descriptions.Item label={t("wiki.affectedPages")}>
                  {deleteImpact.affected_count}
                </Descriptions.Item>
                <Descriptions.Item label={t("wiki.willLoseSource")}>
                  {deleteImpact.will_be_source_invalid_count}
                </Descriptions.Item>
                <Descriptions.Item label={t("wiki.sharedSourceProtected")}>
                  {deleteImpact.shared_source_protected_count}
                </Descriptions.Item>
              </Descriptions>
              <div className="mt-4 mb-2 font-medium">
                {t("wiki.willLoseSource")}
              </div>
              {renderImpactPages(deleteImpact.will_be_source_invalid)}
              <div className="mt-4 mb-2 font-medium">
                {t("wiki.sharedSourceProtected")}
              </div>
              {renderImpactPages(deleteImpact.shared_source_protected)}
            </>
          )
        )}
      </Modal>

      <Modal
        title={t("wiki.updateImpact")}
        open={updateImpactVisible}
        onOk={handleProposeUpdate}
        okText={t("wiki.proposeUpdate")}
        okButtonProps={{ disabled: updateImpactLoading || !updateImpact }}
        confirmLoading={updateSubmitting}
        onCancel={closeUpdateImpact}
        maskClosable={false}
        destroyOnHidden
      >
        {updateImpactLoading ? (
          <div className="py-6 text-center text-[var(--color-text-3)]">
            <LoadingOutlined spin className="mr-2" />
            {t("wiki.updateImpactLoading")}
          </div>
        ) : (
          updateImpact && (
            <>
              <div className="mb-3 text-sm text-[var(--color-text-2)]">
                {t("wiki.updateImpactTip")}
              </div>
              <Descriptions column={3} bordered size="small">
                <Descriptions.Item label={t("wiki.contentChanged")}>
                  {updateImpact.content_changed
                    ? t("common.yes")
                    : t("common.no")}
                </Descriptions.Item>
                <Descriptions.Item label={t("wiki.latestVersion")}>
                  {versionLabel(updateImpact.latest_version)}
                </Descriptions.Item>
                <Descriptions.Item label={t("wiki.previousVersion")}>
                  {versionLabel(updateImpact.previous_version)}
                </Descriptions.Item>
                <Descriptions.Item label={t("wiki.affectedPages")}>
                  {updateImpact.affected_count}
                </Descriptions.Item>
                <Descriptions.Item label={t("wiki.pendingReviewPages")}>
                  {updateImpact.pending_review_count}
                </Descriptions.Item>
              </Descriptions>
              <div className="mt-4 mb-2 font-medium">
                {t("wiki.pendingReviewPages")}
              </div>
              {renderImpactPages(updateImpact.pending_review_pages)}
            </>
          )
        )}
      </Modal>

      <Modal
        title={isEditing ? t("wiki.editMaterial") : t("wiki.addMaterial")}
        open={open}
        onOk={handleSave}
        confirmLoading={saving}
        onCancel={closeMaterialModal}
        maskClosable={false}
        destroyOnHidden
        centered
        width={640}
        styles={{
          body: {
            // header+footer+边距约 200px；再留余量避免 ant-modal-wrap 出现页面级滚动条
            maxHeight: "min(520px, calc(100vh - 200px))",
            overflowY: "auto",
            overflowX: "hidden",
          },
        }}
      >
        <Form form={form} layout="vertical">
          {(type !== "file" || isEditing) && (
            <Form.Item
              label={t("wiki.name")}
              name="name"
              rules={[
                {
                  required: true,
                  message: `${t("common.inputMsg")}${t("wiki.name")}`,
                },
              ]}
            >
              <Input disabled={isEditing && type === "file"} />
            </Form.Item>
          )}
          <Form.Item
            label={t("wiki.materialType")}
            name="material_type"
            initialValue="file"
          >
            <Select
              disabled={isEditing}
              onChange={(v: MaterialType) => {
                setType(v);
                if (v !== "file") {
                  setFolderImport(false);
                  setClassificationRootId(undefined);
                }
              }}
              options={[
                { value: "file", label: t("wiki.materialFile") },
                { value: "text", label: t("wiki.materialText") },
                { value: "web", label: t("wiki.materialWeb") },
              ]}
            />
          </Form.Item>
          {type === "text" && (
            <Form.Item
              label={t("wiki.materialText")}
              name="text_content"
              rules={[{ required: true }]}
            >
              <Input.TextArea rows={6} />
            </Form.Item>
          )}
          {type === "web" && (
            <>
              <Form.Item
                label="URL"
                name="url"
                rules={isEditing ? [] : [{ required: true }]}
              >
                <Input placeholder="https://..." disabled={isEditing} />
              </Form.Item>
              {!isEditing && (
                <Alert
                  showIcon
                  type="warning"
                  className="mb-4"
                  message={t("wiki.webMaterialUsageWarning")}
                />
              )}
              {/* 网页同步按站点单独配置 */}
              <Form.Item
                label={t("wiki.webSyncEnabled")}
                name="sync_enabled"
                valuePropName="checked"
                initialValue={true}
                tooltip={t("wiki.webSyncTip")}
              >
                <Switch />
              </Form.Item>
              <Form.Item
                label={t("wiki.webSyncInterval")}
                name="sync_interval_hours"
                initialValue={24}
              >
                <InputNumber min={1} max={720} addonAfter={t("wiki.hours")} />
              </Form.Item>
            </>
          )}
          {type === "file" && !isEditing && (
            <>
              <Form.Item
                label={t("wiki.folderImport")}
                tooltip={t("wiki.folderImportTip")}
              >
                <Switch
                  checked={folderImport}
                  onChange={(checked) => setFolderImport(checked)}
                />
              </Form.Item>
              <Alert
                showIcon
                type="info"
                className="mb-4"
                message={t("wiki.materialSourceFolderHint")}
              />
              {directoryTree?.enabled && (
                <Form.Item
                  label={t("wiki.materialClassificationRoot")}
                  tooltip={t("wiki.materialClassificationRootHint")}
                >
                  <WikiDirectorySelect
                    directories={directoryTree.directories}
                    value={classificationRootId}
                    allowClear
                    acceptsPagesOnly={false}
                    placeholder={t(
                      "wiki.materialClassificationRootPlaceholder",
                    )}
                    onChange={setClassificationRootId}
                  />
                </Form.Item>
              )}
              <Form.Item label={t("wiki.materialFile")} required>
                <Upload.Dragger
                  multiple
                  directory={folderImport}
                  fileList={fileList}
                  beforeUpload={() => false}
                  onChange={({ fileList: nextList }) => {
                    setFileList((prev) => {
                      const unchanged =
                        prev.length === nextList.length &&
                        prev.every((file, index) => file.uid === nextList[index]?.uid);
                      return unchanged ? prev : nextList;
                    });
                    // 单文件自动填名称;多文件清空名称字段。仅在值变化时写 Form,避免 Upload 受控循环。
                    if (nextList.length === 1) {
                      const fname = nextList[0]?.name || "";
                      if (fname && form.getFieldValue("name") !== fname) {
                        form.setFieldsValue({ name: fname });
                      }
                    } else if (form.getFieldValue("name")) {
                      form.setFieldsValue({ name: "" });
                    }
                  }}
                  accept={FILE_ACCEPT}
                >
                  <p className="ant-upload-drag-icon !mb-2">
                    <UploadOutlined />
                  </p>
                  <p className="ant-upload-text !text-sm">{t("wiki.uploadHint")}</p>
                  <p className="ant-upload-hint !text-xs text-gray-400">
                    {t("wiki.supportedFileHint")}
                  </p>
                  <p className="ant-upload-hint !mb-0 !text-xs text-amber-600">
                    {t("wiki.largeFileUploadHint")}
                  </p>
                </Upload.Dragger>
                {fileList.length > 1 && (
                  <p className="mt-2 text-xs text-gray-400">
                    {t("wiki.selectedFiles")}: {fileList.length}
                  </p>
                )}
              </Form.Item>
            </>
          )}
          {/* 新增 + 编辑(file/web 都可修改):ocr_enhance 让 LLM 在解析时调用 vision
              抽取图片内容;text 类型无图片,不放该开关。 */}
          {(!isEditing || type === "file" || type === "web") && (
            <Form.Item
              label={t("wiki.imageEnhance")}
              name="ocr_enhance"
              valuePropName="checked"
              initialValue={false}
              tooltip={
                hasVisionModel
                  ? t("wiki.imageEnhanceTip")
                  : t("wiki.imageEnhanceDisabledTip")
              }
            >
              <Switch disabled={!hasVisionModel} />
            </Form.Item>
          )}
        </Form>
      </Modal>
    </div>
  );
}

export default MaterialTab;
