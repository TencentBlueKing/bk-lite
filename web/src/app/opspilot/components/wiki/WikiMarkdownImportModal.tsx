"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import {
  Alert,
  Button,
  Collapse,
  Modal,
  Radio,
  Space,
  Spin,
  Switch,
  Table,
  Tag,
  Upload,
  message,
} from "antd";
import { InboxOutlined, ReloadOutlined } from "@ant-design/icons";
import type { ColumnsType } from "antd/es/table";
import type { RcFile, UploadFile } from "antd/es/upload/interface";
import { useWikiApi } from "@/app/opspilot/api/wiki";
import type {
  WikiDirectoryNode,
  WikiMarkdownImportArchiveKind,
  WikiMarkdownImportExecuteResult,
  WikiMarkdownImportPreflightOptions,
  WikiMarkdownImportPreflightResult,
  WikiMarkdownImportPreviewPage,
} from "@/app/opspilot/types/wiki";
import { HandledRequestError } from "@/utils/request";
import { useTranslation } from "@/utils/i18n";
import WikiDirectorySelect from "./WikiDirectorySelect";
import { formatPageTypeLabel } from "./wikiFormat";
import {
  markdownImportGovernanceErrorView,
  formatArchiveBytes,
  initialCreateDirectoriesFromFolders,
  markdownImportAccept,
  markdownImportFilePattern,
  okfSkippedReasonLabel,
  type MarkdownImportGovernanceErrorView,
  type WikiMarkdownImportFormat,
} from "@/app/opspilot/utils/wikiMarkdownImport";

type ImportRouteMode = "auto" | "target" | "classification";

interface WikiMarkdownImportModalProps {
  kbId: number;
  open: boolean;
  directories: WikiDirectoryNode[];
  directoryEnabled: boolean;
  importFormat?: WikiMarkdownImportFormat;
  onCancel: () => void;
  onCompleted: (
    result: WikiMarkdownImportExecuteResult,
  ) => void | Promise<void>;
}
const UNCLASSIFIED_DIRECTORY_KEY = "__unclassified__";

const directoryPathMap = (
  directories: WikiDirectoryNode[],
  ancestors: string[] = [],
  result = new Map<number, string>(),
): Map<number, string> => {
  directories.forEach((directory) => {
    const path = [...ancestors, directory.name];
    result.set(directory.id, path.join(" / "));
    directoryPathMap(directory.children || [], path, result);
  });
  return result;
};

const WikiMarkdownImportModal = ({
  kbId,
  open,
  directories,
  directoryEnabled,
  importFormat = "markdown",
  onCancel,
  onCompleted,
}: WikiMarkdownImportModalProps) => {
  const { t } = useTranslation();
  const { preflightKnowledgeBaseMarkdown, executeKnowledgeBaseMarkdown } =
    useWikiApi();
  const isOkf = importFormat === "okf";
  const archivePattern = markdownImportFilePattern(importFormat);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [fileList, setFileList] = useState<UploadFile[]>([]);
  const [routeMode, setRouteMode] = useState<ImportRouteMode>("auto");
  const [targetDirectoryId, setTargetDirectoryId] = useState<number>();
  const [classificationRootId, setClassificationRootId] = useState<number>();
  const [restoreStructure, setRestoreStructure] = useState(false);
  const [createDirectoriesFromFolders, setCreateDirectoriesFromFolders] =
    useState(() => initialCreateDirectoriesFromFolders(importFormat));
  const [preflight, setPreflight] =
    useState<WikiMarkdownImportPreflightResult | null>(null);
  const [preflightExpiresAt, setPreflightExpiresAt] = useState<number | null>(
    null,
  );
  const [preflightExpired, setPreflightExpired] = useState(false);
  const [preflightStale, setPreflightStale] = useState(false);
  const [preflighting, setPreflighting] = useState(false);
  const [executing, setExecuting] = useState(false);
  const [preflightError, setPreflightError] =
    useState<MarkdownImportGovernanceErrorView | null>(null);
  const preflightSequenceRef = useRef(0);

  const pathsByDirectoryId = useMemo(
    () => directoryPathMap(directories),
    [directories],
  );

  const preflightOptions = useMemo<WikiMarkdownImportPreflightOptions>(() => {
    const options: WikiMarkdownImportPreflightOptions = {
      restore_structure: restoreStructure,
      create_directories_from_folders: createDirectoriesFromFolders,
    };
    if (isOkf) options.import_format = "okf";
    if (routeMode === "target" && targetDirectoryId) {
      options.target_directory_id = targetDirectoryId;
    }
    if (routeMode === "classification" && classificationRootId) {
      options.classification_root_id = classificationRootId;
    }
    return options;
  }, [
    classificationRootId,
    createDirectoriesFromFolders,
    isOkf,
    restoreStructure,
    routeMode,
    targetDirectoryId,
  ]);

  const routeSelectionReady =
    routeMode === "auto" ||
    (routeMode === "target" && Boolean(targetDirectoryId)) ||
    (routeMode === "classification" && Boolean(classificationRootId));

  const resetState = () => {
    preflightSequenceRef.current += 1;
    setSelectedFile(null);
    setFileList([]);
    setRouteMode("auto");
    setTargetDirectoryId(undefined);
    setClassificationRootId(undefined);
    setRestoreStructure(false);
    setCreateDirectoriesFromFolders(
      initialCreateDirectoriesFromFolders(importFormat),
    );
    setPreflight(null);
    setPreflightExpiresAt(null);
    setPreflightExpired(false);
    setPreflightStale(false);
    setPreflighting(false);
    setExecuting(false);
    setPreflightError(null);
  };

  useEffect(() => {
    resetState();
    // resetState 仅重置当前弹窗状态；知识库变化必须丢弃旧 token。
  }, [kbId]);

  useEffect(() => {
    if (!open) resetState();
  }, [open]);

  useEffect(() => {
    setPreflightExpired(false);
    if (preflightExpiresAt === null) return;
    const remaining = preflightExpiresAt - Date.now();
    if (remaining <= 0) {
      setPreflightExpired(true);
      return;
    }
    const timeout = window.setTimeout(
      () => setPreflightExpired(true),
      Math.min(remaining + 50, 2_147_483_647),
    );
    return () => window.clearTimeout(timeout);
  }, [preflightExpiresAt]);

  const invalidatePreflight = () => {
    preflightSequenceRef.current += 1;
    setPreflighting(false);
    setPreflightStale(Boolean(preflight));
  };

  const runPreflight = async (
    file: File,
    options: WikiMarkdownImportPreflightOptions = preflightOptions,
  ) => {
    if (!routeSelectionReady) {
      message.warning(t("wiki.markdownImportRouteRequired"));
      return;
    }
    const sequence = ++preflightSequenceRef.current;
    setPreflighting(true);
    setPreflightExpired(false);
    setPreflightStale(Boolean(preflight));
    setPreflightError(null);
    try {
      const result = await preflightKnowledgeBaseMarkdown(kbId, file, options);
      if (sequence !== preflightSequenceRef.current) return;
      setPreflight(result);
      setPreflightExpiresAt(
        Date.now() + Math.max(result.expires_in_seconds, 0) * 1000,
      );
      setPreflightExpired(result.expires_in_seconds <= 0);
      setPreflightStale(false);
      setPreflightError(null);
    } catch (error) {
      if (sequence !== preflightSequenceRef.current) return;
      setPreflight(null);
      setPreflightExpiresAt(null);
      setPreflightStale(false);
      if (error instanceof HandledRequestError) {
        const view = markdownImportGovernanceErrorView(t, error);
        setPreflightError(view);
        message.error(view.title);
      } else {
        setPreflightError(null);
        message.error(t("wiki.markdownImportPreflightFailed"));
      }
    } finally {
      if (sequence === preflightSequenceRef.current) setPreflighting(false);
    }
  };

  const handleFileSelect = (file: RcFile) => {
    if (!archivePattern.test(file.name)) {
      message.error(
        t(isOkf ? "wiki.okfImportFileTypeInvalid" : "wiki.markdownImportFileTypeInvalid"),
      );
      return Upload.LIST_IGNORE;
    }
    const createFolders = initialCreateDirectoriesFromFolders(importFormat);
    preflightSequenceRef.current += 1;
    setSelectedFile(file);
    setFileList([
      {
        uid: file.uid,
        name: file.name,
        status: "done",
        originFileObj: file,
      },
    ]);
    setRestoreStructure(false);
    setCreateDirectoriesFromFolders(createFolders);
    setPreflight(null);
    setPreflightExpiresAt(null);
    setPreflightExpired(false);
    setPreflightStale(false);
    setPreflightError(null);
    void runPreflight(file, {
      ...preflightOptions,
      restore_structure: false,
      create_directories_from_folders: createFolders,
    });
    return false;
  };

  const handleRemoveFile = () => {
    preflightSequenceRef.current += 1;
    setSelectedFile(null);
    setFileList([]);
    setRestoreStructure(false);
    setCreateDirectoriesFromFolders(
      initialCreateDirectoriesFromFolders(importFormat),
    );
    setPreflight(null);
    setPreflightExpiresAt(null);
    setPreflightExpired(false);
    setPreflightStale(false);
    setPreflighting(false);
    setPreflightError(null);
    return true;
  };

  const handleRouteModeChange = (mode: ImportRouteMode) => {
    setRouteMode(mode);
    invalidatePreflight();
  };

  const handleTargetDirectoryChange = (directoryId?: number) => {
    setTargetDirectoryId(directoryId);
    invalidatePreflight();
  };

  const handleClassificationRootChange = (directoryId?: number) => {
    setClassificationRootId(directoryId);
    invalidatePreflight();
  };

  const handleRestoreStructureChange = (checked: boolean) => {
    setRestoreStructure(checked);
    if (checked) setCreateDirectoriesFromFolders(false);
    invalidatePreflight();
  };

  const handleCreateFoldersChange = (checked: boolean) => {
    setCreateDirectoriesFromFolders(checked);
    if (checked) setRestoreStructure(false);
    invalidatePreflight();
  };

  const handleExecute = async () => {
    if (!selectedFile || !preflight || preflightExpired || preflightStale) {
      message.warning(t("wiki.markdownImportRepreflightRequired"));
      return;
    }
    setExecuting(true);
    try {
      const result = await executeKnowledgeBaseMarkdown(
        kbId,
        selectedFile,
        preflight.token,
      );
      const created = result.counts?.created ?? result.created ?? 0;
      const updated = result.counts?.updated ?? result.updated ?? 0;
      const candidate = result.counts?.candidate ?? 0;
      setPreflight(null);
      message.success(
        t("wiki.markdownImportDone")
          .replace("{created}", String(created))
          .replace("{updated}", String(updated))
          .replace("{candidate}", String(candidate)),
      );
      await onCompleted(result);
    } catch (error) {
      setPreflightStale(true);
      if (error instanceof HandledRequestError && error.status === 409) {
        message.warning(t("wiki.markdownImportRepreflightRequired"));
      } else if (!(error instanceof HandledRequestError)) {
        message.error(t("wiki.markdownImportExecuteFailed"));
      }
    } finally {
      setExecuting(false);
    }
  };

  const archiveKindLabel = (kind: WikiMarkdownImportArchiveKind) => {
    const keyByKind: Record<WikiMarkdownImportArchiveKind, string> = {
      markdown: "wiki.markdownImportArchiveMarkdown",
      native: "wiki.markdownImportArchiveNative",
      opspilot_native: "wiki.markdownImportArchiveNative",
      third_party: "wiki.markdownImportArchiveThirdParty",
      okf: "wiki.okfImportArchiveKind",
    };
    return t(keyByKind[kind]);
  };

  const actionMeta = {
    create: { color: "green", label: t("wiki.markdownImportActionCreate") },
    update: { color: "blue", label: t("wiki.markdownImportActionUpdate") },
    candidate: {
      color: "gold",
      label: t("wiki.markdownImportActionCandidate"),
    },
  } as const;

  const columns: ColumnsType<WikiMarkdownImportPreviewPage> = [
    {
      title: t("wiki.markdownImportPage"),
      key: "page",
      width: 260,
      render: (_: unknown, record) => (
        <div className="min-w-0">
          <div className="truncate font-medium" title={record.title}>
            {record.title}
          </div>
          {record.renamed_from && (
            <div
              className="truncate text-xs text-[var(--color-text-3)]"
              title={record.renamed_from}
            >
              {t("wiki.okfImportRenamedFrom").replace(
                "{title}",
                record.renamed_from,
              )}
            </div>
          )}
          <div
            className="truncate text-xs text-[var(--color-text-3)]"
            title={record.archive_path}
          >
            {record.archive_path}
          </div>
        </div>
      ),
    },
    {
      title: t("wiki.markdownImportAction"),
      dataIndex: "action",
      key: "action",
      width: 96,
      render: (action: WikiMarkdownImportPreviewPage["action"]) => (
        <Tag color={actionMeta[action].color}>{actionMeta[action].label}</Tag>
      ),
    },
    {
      title: t("wiki.markdownImportDirectoryPath"),
      key: "directory",
      width: 230,
      render: (_: unknown, record) => {
        const directory = record.directory;
        if (!directory) return "--";
        const plannedFolder =
          preflight?.preview.structure_preview?.directories?.find(
            (item) => item.client_ref === directory.pending_client_ref,
          )?.folder_path;
        const path =
          (directory.directory_id
            ? pathsByDirectoryId.get(directory.directory_id)
            : undefined) ||
          plannedFolder ||
          directory.directory_key ||
          "--";
        const fallback =
          directory.directory_key === UNCLASSIFIED_DIRECTORY_KEY ||
          directory.source.toLocaleLowerCase().includes("fallback") ||
          directory.trace.some((item) =>
            item.toLocaleLowerCase().includes("fallback"),
          );
        return (
          <div className="min-w-0">
            <div className="truncate" title={path}>
              {path}
            </div>
            <Space size={4} wrap className="mt-1">
              <Tag className="m-0">{directory.assignment_mode}</Tag>
              {directory.pending_client_ref && (
                <Tag color="cyan" className="m-0">
                  {t("wiki.markdownImportCreateFolders")}
                </Tag>
              )}
              {fallback && (
                <Tag color="orange" className="m-0">
                  {t("wiki.markdownImportFallback")}
                </Tag>
              )}
              {directory.redirect_chain.length > 0 && (
                <Tag color="purple" className="m-0">
                  {t("wiki.markdownImportRedirected")}
                </Tag>
              )}
            </Space>
          </div>
        );
      },
    },
  ];

  const canExecute =
    Boolean(selectedFile && preflight) &&
    routeSelectionReady &&
    !preflightExpired &&
    !preflightStale &&
    !preflighting &&
    !executing;

  return (
    <Modal
      title={t(isOkf ? "wiki.okfImportTitle" : "wiki.markdownImportTitle")}
      open={open}
      width={1080}
      okText={t("wiki.markdownImportExecute")}
      cancelText={t("common.cancel")}
      cancelButtonProps={{ disabled: executing }}
      okButtonProps={{ disabled: !canExecute }}
      confirmLoading={executing}
      maskClosable={!executing}
      closable={!executing}
      destroyOnHidden
      styles={{
        body: {
          maxHeight: "calc(100vh - 220px)",
          overflowY: "auto",
          overflowX: "hidden",
        },
      }}
      onCancel={onCancel}
      onOk={handleExecute}
    >
      <div className="space-y-4 py-2">
        {directoryEnabled && (
          <section className="rounded-lg border border-[var(--color-border-1)] bg-[var(--color-bg-1)] p-4">
            <div className="mb-3 text-sm font-medium">
              {t("wiki.markdownImportRouteMode")}
            </div>
            <Radio.Group
              value={routeMode}
              optionType="button"
              buttonStyle="solid"
              options={[
                {
                  value: "auto",
                  label: t("wiki.markdownImportRouteAuto"),
                },
                {
                  value: "target",
                  label: t("wiki.markdownImportRouteTarget"),
                },
                {
                  value: "classification",
                  label: t("wiki.markdownImportRouteClassification"),
                },
              ]}
              onChange={(event) =>
                handleRouteModeChange(event.target.value as ImportRouteMode)
              }
            />
            {routeMode === "target" && (
              <div className="mt-3 max-w-xl">
                <WikiDirectorySelect
                  directories={directories}
                  value={targetDirectoryId}
                  allowClear
                  placeholder={t("wiki.markdownImportTargetDirectory")}
                  onChange={handleTargetDirectoryChange}
                />
              </div>
            )}
            {routeMode === "classification" && (
              <div className="mt-3 max-w-xl">
                <WikiDirectorySelect
                  directories={directories}
                  value={classificationRootId}
                  allowClear
                  acceptsPagesOnly={false}
                  placeholder={t("wiki.markdownImportClassificationRoot")}
                  onChange={handleClassificationRootChange}
                />
              </div>
            )}
            <div className="mt-2 text-xs text-[var(--color-text-3)]">
              {t("wiki.markdownImportRouteHint")}
            </div>
          </section>
        )}

        <Upload.Dragger
          accept={markdownImportAccept(importFormat)}
          maxCount={1}
          fileList={fileList}
          disabled={preflighting || executing}
          beforeUpload={handleFileSelect}
          onRemove={handleRemoveFile}
        >
          <p className="ant-upload-drag-icon">
            <InboxOutlined />
          </p>
          <p className="ant-upload-text">
            {t(isOkf ? "wiki.okfImportDropHint" : "wiki.markdownImportDropHint")}
          </p>
          <p className="ant-upload-hint">
            {t("wiki.markdownImportSizeHint")}
          </p>
        </Upload.Dragger>

        {preflightError && (
          <Alert
            showIcon
            type="error"
            message={preflightError.title}
            description={
              <div className="space-y-2">
                {preflightError.description ? (
                  <div className="whitespace-pre-wrap">{preflightError.description}</div>
                ) : null}
                {preflightError.example ? (
                  <pre className="mb-0 overflow-x-auto rounded-md bg-[var(--color-fill-2)] px-3 py-2 text-xs text-[var(--color-text-2)]">
                    {preflightError.example}
                  </pre>
                ) : null}
              </div>
            }
          />
        )}

        {selectedFile && (
          <div className="flex flex-wrap items-center justify-between gap-2">
            <span className="min-w-0 truncate text-xs text-[var(--color-text-3)]">
              {selectedFile.name}
            </span>
            <Button
              icon={<ReloadOutlined />}
              loading={preflighting}
              disabled={executing || !routeSelectionReady}
              onClick={() => void runPreflight(selectedFile)}
            >
              {preflight
                ? t("wiki.markdownImportRepreflight")
                : t("wiki.markdownImportPreflight")}
            </Button>
          </div>
        )}

        {preflighting && !preflight && (
          <div className="flex min-h-40 items-center justify-center">
            <Spin tip={t("wiki.markdownImportPreflighting")} />
          </div>
        )}

        {preflight && (
          <div className="flex flex-col gap-6">
            <Alert
              showIcon
              type={preflightExpired || preflightStale ? "warning" : "success"}
              message={
                preflightExpired
                  ? t("wiki.markdownImportTokenExpired")
                  : preflightStale
                    ? t("wiki.markdownImportPreviewStale")
                    : t("wiki.markdownImportTokenReady")
              }
              description={
                preflightExpired || preflightStale
                  ? t("wiki.markdownImportRepreflightRequired")
                  : t("wiki.markdownImportSingleUseHint").replace(
                    "{seconds}",
                    String(preflight.expires_in_seconds),
                  )
              }
            />

            <div className="grid grid-cols-2 gap-2 md:grid-cols-5">
              {[
                {
                  label: t("wiki.markdownImportArchiveKind"),
                  value: (
                    <Tag color="geekblue">
                      {archiveKindLabel(preflight.preview.archive_kind)}
                    </Tag>
                  ),
                },
                {
                  label: t("wiki.markdownImportTotal"),
                  value: preflight.preview.counts.total,
                },
                {
                  label: t("wiki.markdownImportCreate"),
                  value: preflight.preview.counts.create,
                },
                {
                  label: t("wiki.markdownImportUpdate"),
                  value: preflight.preview.counts.update,
                },
                {
                  label: t("wiki.markdownImportCandidate"),
                  value: preflight.preview.counts.candidate,
                },
              ].map((item) => (
                <div
                  key={item.label}
                  className="rounded-md border border-[var(--color-border-1)] px-3 py-2"
                >
                  <div className="text-xs text-[var(--color-text-3)]">
                    {item.label}
                  </div>
                  <div className="mt-1 text-lg font-semibold">{item.value}</div>
                </div>
              ))}
            </div>

            {preflight.preview.skipped_entries > 0 && (
              <Alert
                showIcon
                type="warning"
                message={t("wiki.markdownImportSkipped").replace(
                  "{count}",
                  String(preflight.preview.skipped_entries),
                )}
              />
            )}

            {preflight.preview.okf && (
              <section className="space-y-3 rounded-lg border border-[var(--color-border-1)] bg-[var(--color-bg-1)] p-4">
                <div className="text-sm font-medium">
                  {t("wiki.okfImportSummaryTitle")}
                </div>
                <div className="grid grid-cols-2 gap-2 md:grid-cols-4">
                  {[
                    {
                      label: t("wiki.okfImportVersion"),
                      value: preflight.preview.okf.okf_version || "--",
                    },
                    {
                      label: t("wiki.okfImportBundleRoot"),
                      value: preflight.preview.okf.bundle_root || "/",
                    },
                    {
                      label: t("wiki.okfImportLinksRewritten"),
                      value: preflight.preview.okf.links.rewritten,
                    },
                    {
                      label: t("wiki.okfImportLinksUnresolved"),
                      value: preflight.preview.okf.links.unresolved,
                    },
                    {
                      label: t("wiki.okfImportRenamedCount"),
                      value: preflight.preview.okf.renamed_count,
                    },
                    {
                      label: t("wiki.okfImportImagesCount"),
                      value: preflight.preview.okf.images?.count ?? 0,
                    },
                    {
                      label: t("wiki.okfImportImagesBytes"),
                      value: formatArchiveBytes(preflight.preview.okf.images?.bytes),
                    },
                    {
                      label: t("wiki.okfImportImagesPages"),
                      value: preflight.preview.okf.images?.pages ?? 0,
                    },
                  ].map((item) => (
                    <div
                      key={item.label}
                      className="rounded-md border border-[var(--color-border-1)] px-3 py-2"
                    >
                      <div className="text-xs text-[var(--color-text-3)]">
                        {item.label}
                      </div>
                      <div className="mt-1 truncate text-sm font-semibold">
                        {item.value}
                      </div>
                    </div>
                  ))}
                </div>
                {preflight.preview.okf.type_mapping.length > 0 && (
                  <Table
                    size="small"
                    pagination={false}
                    rowKey={(row) => `${row.okf_type}:${row.page_type}`}
                    dataSource={preflight.preview.okf.type_mapping}
                    columns={[
                      {
                        title: t("wiki.okfImportType"),
                        dataIndex: "okf_type",
                        key: "okf_type",
                      },
                      {
                        title: t("wiki.okfImportPageType"),
                        dataIndex: "page_type",
                        key: "page_type",
                        render: (pageType: string) =>
                          formatPageTypeLabel(t, pageType),
                      },
                      {
                        title: t("wiki.okfImportTypeMatched"),
                        dataIndex: "matched",
                        key: "matched",
                        render: (matched: boolean) => (
                          <Tag color={matched ? "green" : "orange"}>
                            {matched
                              ? t("wiki.okfImportMatched")
                              : t("wiki.okfImportUnmatched")}
                          </Tag>
                        ),
                      },
                      {
                        title: t("wiki.okfImportTypeCount"),
                        dataIndex: "count",
                        key: "count",
                        width: 80,
                      },
                    ]}
                  />
                )}
                {Number(preflight.preview.okf.images?.html_unchecked) > 0 && (
                  <Alert
                    showIcon
                    type="info"
                    message={t("wiki.okfImportHtmlImagesHint").replace(
                      "{count}",
                      String(preflight.preview.okf.images?.html_unchecked),
                    )}
                  />
                )}
                {preflight.preview.okf.skipped.length > 0 && (
                  <Collapse
                    ghost
                    size="small"
                    items={[
                      {
                        key: "skipped",
                        label: `${t("wiki.okfImportSkippedList")} (${preflight.preview.okf.skipped.length})`,
                        children: (
                          <div className="space-y-2">
                            {preflight.preview.okf.skipped.some(
                              (item) => item.reason === "reserved",
                            ) && (
                              <Alert
                                showIcon
                                type="info"
                                message={t("wiki.okfImportSkippedReservedHint")}
                              />
                            )}
                            <ul className="max-h-48 overflow-y-auto text-xs">
                              {preflight.preview.okf.skipped.map((item) => (
                                <li
                                  key={`${item.path}:${item.reason}`}
                                  className="border-b border-[var(--color-border-1)] py-1.5 last:border-b-0"
                                >
                                  <div
                                    className="truncate text-[var(--color-text-2)]"
                                    title={item.path}
                                  >
                                    {item.path}
                                  </div>
                                  <div className="mt-0.5 text-[var(--color-text-3)]">
                                    {okfSkippedReasonLabel(t, item.reason)}
                                  </div>
                                </li>
                              ))}
                            </ul>
                          </div>
                        ),
                      },
                    ]}
                  />
                )}
              </section>
            )}

            {preflight.preview.native_structure_available && (
              <Alert
                showIcon
                type="info"
                message={t("wiki.markdownImportNativeStructureAvailable")}
                description={t("wiki.markdownImportRestoreHint")}
                action={
                  <Space>
                    <span className="text-xs">
                      {t("wiki.markdownImportRestoreStructure")}
                    </span>
                    <Switch
                      checked={restoreStructure}
                      disabled={executing}
                      onChange={handleRestoreStructureChange}
                    />
                  </Space>
                }
              />
            )}

            {(preflight.preview.archive_kind === "third_party" ||
              preflight.preview.archive_kind === "okf") && (
              <Alert
                showIcon
                type="warning"
                message={t(
                  preflight.preview.archive_kind === "okf"
                    ? "wiki.okfImportCreateFoldersTitle"
                    : "wiki.markdownImportCreateFoldersTitle",
                )}
                description={t(
                  preflight.preview.archive_kind === "okf"
                    ? "wiki.okfImportCreateFoldersHint"
                    : "wiki.markdownImportCreateFoldersHint",
                )}
                action={
                  <Space>
                    <span className="text-xs">
                      {t("wiki.markdownImportCreateFolders")}
                    </span>
                    <Switch
                      checked={createDirectoriesFromFolders}
                      disabled={executing}
                      onChange={handleCreateFoldersChange}
                    />
                  </Space>
                }
              />
            )}

            {preflight.preview.structure_preview
              ?.create_directories_from_folders && (
              <Alert
                showIcon
                type="info"
                message={t("wiki.markdownImportCreateFoldersPreview").replace(
                  "{count}",
                  String(
                    preflight.preview.structure_preview
                      .create_directory_count ?? 0,
                  ),
                )}
              />
            )}

            <section>
              <div className="mb-2 text-sm font-medium">
                {t("wiki.markdownImportPreviewTitle")}
              </div>
              <Table<WikiMarkdownImportPreviewPage>
                rowKey="archive_path"
                size="small"
                columns={columns}
                dataSource={preflight.preview.pages}
                pagination={{
                  pageSize: 20,
                  showSizeChanger: false,
                  hideOnSinglePage: true,
                }}
                scroll={{ x: 640 }}
              />
            </section>
          </div>
        )}
      </div>
    </Modal>
  );
};

export default WikiMarkdownImportModal;
