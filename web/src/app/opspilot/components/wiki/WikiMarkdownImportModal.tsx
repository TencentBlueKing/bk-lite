"use client";

import { useEffect, useState } from "react";
import { Alert, Modal, Upload, message } from "antd";
import { InboxOutlined } from "@ant-design/icons";
import type { RcFile, UploadFile } from "antd/es/upload/interface";
import { useWikiApi } from "@/app/opspilot/api/wiki";
import type { WikiMarkdownImportExecuteResult } from "@/app/opspilot/types/wiki";
import { HandledRequestError } from "@/utils/request";
import { useTranslation } from "@/utils/i18n";
import {
  markdownImportGovernanceErrorView,
  initialCreateDirectoriesFromFolders,
  isBackgroundMarkdownImport,
  markdownImportAccept,
  markdownImportFilePattern,
  unwrapMarkdownImportExecuteResult,
  type MarkdownImportGovernanceErrorView,
} from "@/app/opspilot/utils/wikiMarkdownImport";

interface WikiMarkdownImportModalProps {
  kbId: number;
  open: boolean;
  onCancel: () => void;
  onCompleted: (
    result: WikiMarkdownImportExecuteResult,
  ) => void | Promise<void>;
}

const WikiMarkdownImportModal = ({
  kbId,
  open,
  onCancel,
  onCompleted,
}: WikiMarkdownImportModalProps) => {
  const { t } = useTranslation();
  const {
    preflightKnowledgeBaseMarkdown,
    executeKnowledgeBaseMarkdown,
  } = useWikiApi();
  const archivePattern = markdownImportFilePattern();
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [fileList, setFileList] = useState<UploadFile[]>([]);
  const [executing, setExecuting] = useState(false);
  const [importError, setImportError] =
    useState<MarkdownImportGovernanceErrorView | null>(null);

  const resetState = () => {
    setSelectedFile(null);
    setFileList([]);
    setExecuting(false);
    setImportError(null);
  };

  useEffect(() => {
    resetState();
  }, [kbId]);

  useEffect(() => {
    if (!open) resetState();
  }, [open]);

  const handleFileSelect = (file: RcFile) => {
    if (!archivePattern.test(file.name)) {
      message.error(t("wiki.okfImportFileTypeInvalid"));
      return Upload.LIST_IGNORE;
    }
    setSelectedFile(file);
    setFileList([
      {
        uid: file.uid,
        name: file.name,
        status: "done",
        originFileObj: file,
      },
    ]);
    setImportError(null);
    return false;
  };

  const handleRemoveFile = () => {
    setSelectedFile(null);
    setFileList([]);
    setImportError(null);
    return true;
  };

  const showRequestError = (error: unknown, fallbackKey: string) => {
    if (error instanceof HandledRequestError) {
      const view = markdownImportGovernanceErrorView(t, error);
      setImportError(view);
      message.error(view.title);
      return;
    }
    setImportError(null);
    message.error(t(fallbackKey));
  };

  const finishImport = async (result: WikiMarkdownImportExecuteResult) => {
    const created = result.counts?.created ?? result.created ?? 0;
    const updated = result.counts?.updated ?? result.updated ?? 0;
    const candidate = result.counts?.candidate ?? 0;
    const skipped = result.skipped_documents?.length ?? 0;
    const summary = t("wiki.markdownImportDone")
      .replace("{created}", String(created))
      .replace("{updated}", String(updated))
      .replace("{candidate}", String(candidate));
    message.success(
      skipped
        ? `${summary}${t("wiki.markdownImportPartialSkipped").replace("{count}", String(skipped))}`
        : summary,
    );
    await onCompleted(result);
  };

  const handleExecute = async () => {
    if (!selectedFile) return;
    setExecuting(true);
    setImportError(null);
    try {
      const preflight = await preflightKnowledgeBaseMarkdown(kbId, selectedFile, {
        import_format: "okf",
        create_directories_from_folders: initialCreateDirectoriesFromFolders(),
      });
      const result = unwrapMarkdownImportExecuteResult(
        await executeKnowledgeBaseMarkdown(kbId, selectedFile, preflight.token),
      );
      if (isBackgroundMarkdownImport(result)) {
        message.info(t("wiki.markdownImportRunning"));
        onCancel();
        return;
      }
      await finishImport(result);
    } catch (error) {
      showRequestError(error, "wiki.markdownImportExecuteFailed");
    } finally {
      setExecuting(false);
    }
  };

  return (
    <Modal
      title={t("wiki.okfImportTitle")}
      open={open}
      width={640}
      okText={t("wiki.markdownImportExecute")}
      cancelText={t("common.cancel")}
      cancelButtonProps={{ disabled: executing }}
      okButtonProps={{ disabled: !selectedFile || executing }}
      confirmLoading={executing}
      maskClosable={!executing}
      closable={!executing}
      destroyOnHidden
      onCancel={onCancel}
      onOk={() => void handleExecute()}
    >
      <div className="space-y-4 py-2">
        <Upload.Dragger
          accept={markdownImportAccept()}
          maxCount={1}
          fileList={fileList}
          disabled={executing}
          beforeUpload={handleFileSelect}
          onRemove={handleRemoveFile}
        >
          <p className="ant-upload-drag-icon">
            <InboxOutlined />
          </p>
          <p className="ant-upload-text">{t("wiki.okfImportDropHint")}</p>
          <p className="ant-upload-hint">{t("wiki.markdownImportSizeHint")}</p>
        </Upload.Dragger>

        {importError && (
          <Alert
            showIcon
            type="error"
            message={importError.title}
            description={
              <div className="space-y-2">
                {importError.description ? (
                  <div className="whitespace-pre-wrap">{importError.description}</div>
                ) : null}
                {importError.example ? (
                  <pre className="mb-0 overflow-x-auto rounded-md bg-[var(--color-fill-2)] px-3 py-2 text-xs text-[var(--color-text-2)]">
                    {importError.example}
                  </pre>
                ) : null}
              </div>
            }
          />
        )}
      </div>
    </Modal>
  );
};

export default WikiMarkdownImportModal;
