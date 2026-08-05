"use client";

import { useEffect, useMemo, useState } from "react";
import {
  Alert,
  Button,
  Descriptions,
  Divider,
  Drawer,
  List,
  Select,
  Space,
  Tag,
  message,
} from "antd";
import { useWikiApi } from "@/app/opspilot/api/wiki";
import type {
  WikiDirectoryOperationAction,
  WikiDirectoryOperationPreview,
  WikiExistingStructureDirectory,
} from "@/app/opspilot/types/wiki";
import { useTranslation } from "@/utils/i18n";
import { HandledRequestError } from "@/utils/request";

const REPREVIEW_ERROR_CODES = new Set([
  "operation_token_expired",
  "operation_token_invalid",
  "operation_token_binding_mismatch",
  "operation_token_replayed",
  "directory_operation_stale",
]);

const requiresFreshPreview = (error: unknown) => {
  if (!(error instanceof HandledRequestError)) return false;
  const payload = error.payload as { retryable?: boolean } | undefined;
  return Boolean(
    REPREVIEW_ERROR_CODES.has(error.code ?? "") ||
    (error.status === 409 && payload?.retryable),
  );
};

interface WikiDirectoryImpactDrawerProps {
  open: boolean;
  kbId: number;
  structureVersion: number | null;
  baseGenerationId: number | null;
  directories: WikiExistingStructureDirectory[];
  onClose: () => void;
  onCompleted: () => void | Promise<void>;
}

const WikiDirectoryImpactDrawer = ({
  open,
  kbId,
  structureVersion,
  baseGenerationId,
  directories,
  onClose,
  onCompleted,
}: WikiDirectoryImpactDrawerProps) => {
  const { t } = useTranslation();
  const { previewDirectoryOperation, executeDirectoryOperation } = useWikiApi();
  const [action, setAction] = useState<WikiDirectoryOperationAction>("merge");
  const [sourceId, setSourceId] = useState<number>();
  const [targetId, setTargetId] = useState<number>();
  const [preview, setPreview] = useState<WikiDirectoryOperationPreview | null>(
    null,
  );
  const [previewing, setPreviewing] = useState(false);
  const [executing, setExecuting] = useState(false);
  const [previewExpired, setPreviewExpired] = useState(false);

  const activeDirectories = useMemo(
    () => directories.filter((directory) => directory.status === "active"),
    [directories],
  );
  const sourceOptions = useMemo(
    () =>
      activeDirectories
        .filter((directory) => directory.origin !== "system")
        .map((directory) => ({
          value: directory.id,
          label: directory.name,
        })),
    [activeDirectories],
  );
  const targetOptions = useMemo(
    () =>
      activeDirectories
        .filter((directory) => directory.id !== sourceId)
        .map((directory) => ({
          value: directory.id,
          label: directory.name,
        })),
    [activeDirectories, sourceId],
  );
  const source = activeDirectories.find(
    (directory) => directory.id === sourceId,
  );
  const target = activeDirectories.find(
    (directory) => directory.id === targetId,
  );
  const pointersReady = structureVersion !== null && baseGenerationId !== null;

  useEffect(() => {
    if (!open) {
      setAction("merge");
      setSourceId(undefined);
      setTargetId(undefined);
      setPreview(null);
    }
  }, [open]);

  useEffect(() => {
    if (!open) return;
    setPreview(null);
  }, [baseGenerationId, open, structureVersion]);

  useEffect(() => {
    setPreviewExpired(false);
    if (!preview) return;
    const expiresAt = Date.parse(preview.expires_at);
    if (!Number.isFinite(expiresAt) || expiresAt <= Date.now()) {
      setPreviewExpired(true);
      return;
    }
    const timeout = window.setTimeout(
      () => setPreviewExpired(true),
      Math.min(expiresAt - Date.now() + 50, 2_147_483_647),
    );
    return () => window.clearTimeout(timeout);
  }, [preview]);

  const resetPreview = () => setPreview(null);

  const handleActionChange = (value: WikiDirectoryOperationAction) => {
    setAction(value);
    setTargetId(undefined);
    resetPreview();
  };

  const handlePreview = async () => {
    if (structureVersion === null || baseGenerationId === null || !source)
      return;
    if ((action === "merge" || action === "retire") && !target) return;
    setPreview(null);
    setPreviewing(true);
    try {
      const result = await previewDirectoryOperation(kbId, {
        structure_version: structureVersion,
        base_generation_id: baseGenerationId,
        action,
        source: { id: source.id, key: source.key },
        ...(target ? { target: { id: target.id, key: target.key } } : {}),
      });
      setPreview(result);
    } finally {
      setPreviewing(false);
    }
  };

  const handleExecute = async () => {
    if (!preview) return;
    if (previewExpired) {
      setPreview(null);
      message.warning(t("wiki.directoryOperationPreviewRequired"));
      return;
    }
    let operationCompleted = false;
    setExecuting(true);
    try {
      const binding = preview.binding;
      await executeDirectoryOperation(kbId, {
        structure_version: binding.structure_version,
        base_generation_id: binding.base_generation_id,
        action: binding.action,
        source: binding.source,
        ...(binding.target ? { target: binding.target } : {}),
        operation_token: preview.operation_token,
        impact_hash: preview.impact_hash,
      });
      operationCompleted = true;
      setPreview(null);
      message.success(t("wiki.directoryOperationDone"));
      await onCompleted();
      onClose();
    } catch (error) {
      if (!operationCompleted && requiresFreshPreview(error)) {
        setPreview(null);
        message.warning(t("wiki.directoryOperationPreviewRequired"));
      }
    } finally {
      setExecuting(false);
    }
  };

  const previewDisabled =
    !pointersReady ||
    !source ||
    ((action === "merge" || action === "retire") && !target) ||
    previewing ||
    executing;

  return (
    <Drawer
      title={t("wiki.directoryImpactTitle")}
      open={open}
      width="min(680px, calc(100vw - 24px))"
      destroyOnHidden
      maskClosable={!executing}
      closable={!executing}
      onClose={onClose}
      extra={
        <Space>
          <Button disabled={executing} onClick={onClose}>
            {t("common.cancel")}
          </Button>
          <Button
            type="primary"
            danger
            loading={executing}
            disabled={!preview?.can_execute || previewExpired}
            onClick={() => void handleExecute()}
          >
            {t("wiki.directoryOperationExecute")}
          </Button>
        </Space>
      }
    >
      <div className="space-y-4">
        <Alert
          showIcon
          type="warning"
          message={t("wiki.directoryOperationWarning")}
          description={t("wiki.directoryOperationWarningDesc")}
        />
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          <Select
            value={action}
            options={[
              { value: "merge", label: t("wiki.directoryOperationMerge") },
              { value: "retire", label: t("wiki.directoryOperationRetire") },
              { value: "archive", label: t("wiki.directoryOperationArchive") },
            ]}
            onChange={handleActionChange}
          />
          <Select
            value={sourceId}
            options={sourceOptions}
            placeholder={t("wiki.directoryOperationSource")}
            showSearch
            optionFilterProp="label"
            onChange={(value) => {
              setSourceId(value);
              setTargetId(undefined);
              resetPreview();
            }}
          />
          {(action === "merge" || action === "retire") && (
            <Select
              value={targetId}
              options={targetOptions}
              placeholder={t("wiki.directoryOperationTarget")}
              showSearch
              optionFilterProp="label"
              onChange={(value) => {
                setTargetId(value);
                resetPreview();
              }}
            />
          )}
        </div>
        <Button
          loading={previewing}
          disabled={previewDisabled}
          onClick={() => void handlePreview()}
        >
          {t("wiki.directoryOperationPreview")}
        </Button>

        {preview && (
          <>
            <Divider className="my-3" />
            <Descriptions bordered size="small" column={2}>
              <Descriptions.Item label={t("wiki.directoryDirectPages")}>
                {preview.impact.direct_page_count}
              </Descriptions.Item>
              <Descriptions.Item label={t("wiki.directoryDescendantPages")}>
                {preview.impact.descendant_page_count}
              </Descriptions.Item>
              <Descriptions.Item label={t("wiki.directoryManualPages")}>
                {preview.impact.manual_page_count}
              </Descriptions.Item>
              <Descriptions.Item label={t("wiki.directoryChildCount")}>
                {preview.impact.child_directory_count}
              </Descriptions.Item>
              <Descriptions.Item
                label={t("wiki.directoryOperationExpires")}
                span={2}
              >
                {preview.expires_at}
                <Tag className="ml-2">
                  {t("wiki.directoryOperationSingleUse")}
                </Tag>
              </Descriptions.Item>
            </Descriptions>
            {preview.impact.redirect && (
              <Alert
                showIcon
                type="info"
                message={
                  <span>
                    {preview.impact.redirect.source.key}
                    <span className="px-1">→</span>
                    {preview.impact.redirect.target.key}
                  </span>
                }
              />
            )}
            {!!preview.impact.conflicts.length && (
              <List
                header={t("wiki.directoryOperationConflicts")}
                dataSource={preview.impact.conflicts}
                renderItem={(item) => <List.Item>{item.details}</List.Item>}
              />
            )}
            {!!preview.impact.block_reasons.length && (
              <List
                header={t("wiki.directoryOperationBlocked")}
                dataSource={preview.impact.block_reasons}
                renderItem={(item) => (
                  <List.Item>
                    <Tag color="red">{item.code}</Tag>
                    {item.details}
                  </List.Item>
                )}
              />
            )}
            <Alert
              showIcon
              type={
                previewExpired
                  ? "warning"
                  : preview.can_execute
                    ? "success"
                    : "error"
              }
              message={
                previewExpired
                  ? t("wiki.directoryOperationExpired")
                  : preview.can_execute
                    ? t("wiki.directoryOperationReady")
                    : t("wiki.directoryOperationCannotExecute")
              }
            />
          </>
        )}
      </div>
    </Drawer>
  );
};

export default WikiDirectoryImpactDrawer;
