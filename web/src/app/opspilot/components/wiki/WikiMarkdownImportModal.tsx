"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import {
  Alert,
  Button,
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

type ImportRouteMode = "auto" | "target" | "classification";

interface WikiMarkdownImportModalProps {
  kbId: number;
  open: boolean;
  directories: WikiDirectoryNode[];
  directoryEnabled: boolean;
  onCancel: () => void;
  onCompleted: (
    result: WikiMarkdownImportExecuteResult,
  ) => void | Promise<void>;
}

const MARKDOWN_ARCHIVE_PATTERN = /\.(?:md|markdown|zip)$/iu;
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
  onCancel,
  onCompleted,
}: WikiMarkdownImportModalProps) => {
  const { t } = useTranslation();
  const { preflightKnowledgeBaseMarkdown, executeKnowledgeBaseMarkdown } =
    useWikiApi();
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [fileList, setFileList] = useState<UploadFile[]>([]);
  const [routeMode, setRouteMode] = useState<ImportRouteMode>("auto");
  const [targetDirectoryId, setTargetDirectoryId] = useState<number>();
  const [classificationRootId, setClassificationRootId] = useState<number>();
  const [restoreStructure, setRestoreStructure] = useState(false);
  const [createDirectoriesFromFolders, setCreateDirectoriesFromFolders] =
    useState(false);
  const [preflight, setPreflight] =
    useState<WikiMarkdownImportPreflightResult | null>(null);
  const [preflightExpiresAt, setPreflightExpiresAt] = useState<number | null>(
    null,
  );
  const [preflightExpired, setPreflightExpired] = useState(false);
  const [preflightStale, setPreflightStale] = useState(false);
  const [preflighting, setPreflighting] = useState(false);
  const [executing, setExecuting] = useState(false);
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
    setCreateDirectoriesFromFolders(false);
    setPreflight(null);
    setPreflightExpiresAt(null);
    setPreflightExpired(false);
    setPreflightStale(false);
    setPreflighting(false);
    setExecuting(false);
  };

  useEffect(() => {
    resetState();
    // resetState 仅重置当前弹窗状态；知识库变化必须丢弃旧 token。
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [kbId]);

  useEffect(() => {
    if (!open) resetState();
    // eslint-disable-next-line react-hooks/exhaustive-deps
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
    try {
      const result = await preflightKnowledgeBaseMarkdown(kbId, file, options);
      if (sequence !== preflightSequenceRef.current) return;
      setPreflight(result);
      setPreflightExpiresAt(
        Date.now() + Math.max(result.expires_in_seconds, 0) * 1000,
      );
      setPreflightExpired(result.expires_in_seconds <= 0);
      setPreflightStale(false);
    } catch (error) {
      if (sequence !== preflightSequenceRef.current) return;
      setPreflight(null);
      setPreflightExpiresAt(null);
      setPreflightStale(false);
      if (!(error instanceof HandledRequestError)) {
        message.error(t("wiki.markdownImportPreflightFailed"));
      }
    } finally {
      if (sequence === preflightSequenceRef.current) setPreflighting(false);
    }
  };

  const handleFileSelect = (file: RcFile) => {
    if (!MARKDOWN_ARCHIVE_PATTERN.test(file.name)) {
      message.error(t("wiki.markdownImportFileTypeInvalid"));
      return Upload.LIST_IGNORE;
    }
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
    setCreateDirectoriesFromFolders(false);
    setPreflight(null);
    setPreflightExpiresAt(null);
    setPreflightExpired(false);
    setPreflightStale(false);
    void runPreflight(file, {
      ...preflightOptions,
      restore_structure: false,
      create_directories_from_folders: false,
    });
    return false;
  };

  const handleRemoveFile = () => {
    preflightSequenceRef.current += 1;
    setSelectedFile(null);
    setFileList([]);
    setRestoreStructure(false);
    setCreateDirectoriesFromFolders(false);
    setPreflight(null);
    setPreflightExpiresAt(null);
    setPreflightExpired(false);
    setPreflightStale(false);
    setPreflighting(false);
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
      setPreflightExpiresAt(null);
      message.success(
        t("wiki.markdownImportDone")
          .replace("{created}", String(created))
          .replace("{updated}", String(updated))
          .replace("{candidate}", String(candidate)),
      );
      await onCompleted(result);
    } catch (error) {
      setPreflightStale(true);
      setPreflightExpired(
        error instanceof HandledRequestError && error.status === 409,
      );
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
    {
      title: t("wiki.markdownImportRouteTrace"),
      key: "route",
      width: 340,
      render: (_: unknown, record) => {
        const directory = record.directory;
        if (!directory) return "--";
        const trace = directory.trace.join(" → ") || directory.source;
        const detail = [
          directory.route_reason,
          directory.suggestion?.reason,
          directory.redirect_chain.length
            ? directory.redirect_chain.join(" → ")
            : "",
        ]
          .filter(Boolean)
          .join(" · ");
        return (
          <div className="min-w-0">
            <div className="break-words text-xs" title={trace}>
              {trace}
            </div>
            {detail && (
              <div
                className="mt-1 break-words text-xs text-[var(--color-text-3)]"
                title={detail}
              >
                {detail}
              </div>
            )}
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
      title={t("wiki.markdownImportTitle")}
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
          accept=".md,.markdown,.zip"
          maxCount={1}
          fileList={fileList}
          disabled={preflighting || executing}
          beforeUpload={handleFileSelect}
          onRemove={handleRemoveFile}
        >
          <p className="ant-upload-drag-icon">
            <InboxOutlined />
          </p>
          <p className="ant-upload-text">{t("wiki.markdownImportDropHint")}</p>
          <p className="ant-upload-hint">
            {t("wiki.markdownImportSecurityHint")}
          </p>
        </Upload.Dragger>

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
          <>
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

            {preflight.preview.archive_kind === "third_party" && (
              <Alert
                showIcon
                type="warning"
                message={t("wiki.markdownImportCreateFoldersTitle")}
                description={t("wiki.markdownImportCreateFoldersHint")}
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
                scroll={{ x: 980 }}
              />
            </section>
          </>
        )}
      </div>
    </Modal>
  );
};

export default WikiMarkdownImportModal;
