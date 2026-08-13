"use client";

import React from "react";
import { Alert, Button } from "antd";
import { useTranslation } from "@/utils/i18n";
import { formatOpsDisplayTime } from "@/app/ops-analysis/utils/dateTime";

export interface ExcelMaterializationState {
  status?: string;
  generation?: number;
  success_slot_id?: number | null;
  candidate_slot_id?: number | null;
  candidate_status?: string | null;
  error_code?: string;
  error_summary?: string;
  success_updated_at?: string | null;
  has_saved_source?: boolean;
  can_retry?: boolean;
}

interface ExcelMaterializationStatusProps {
  state?: ExcelMaterializationState | null;
  readOnly?: boolean;
  retrying?: boolean;
  /** 已选择尚未保存的新文件：有旧结果时提示将替换；否则不刷多余提示。 */
  pendingNewFile?: boolean;
  onRetry?: () => void;
}

function resolveFailedHint(
  t: (key: string, fallback?: string) => string,
  state: ExcelMaterializationState,
): string {
  const code = state.error_code || "";
  if (code === "excel_file_required") {
    return t("dataSource.excelStatus.failedHintReupload");
  }
  if (code.includes("transform") || code.includes("runner")) {
    return t("dataSource.excelStatus.failedHintRunner");
  }
  if (code.includes("internal") || code.includes("storage") || !state.error_summary) {
    return t("dataSource.excelStatus.failedHintGeneric");
  }
  return t("dataSource.excelStatus.failedHintRetry");
}

function formatSuccessTime(value?: string | null): string {
  if (!value) return "";
  return formatOpsDisplayTime(value, "YYYY-MM-DD HH:mm:ss");
}

function CompactAlertMessage({
  title,
  detail,
}: {
  title: string;
  detail?: string;
}) {
  return (
    <div className="text-[13px] leading-5">
      <div className="font-medium text-[var(--color-text-1)]">{title}</div>
      {detail ? (
        <div className="mt-0.5 font-normal text-[12px] leading-5 text-[var(--color-text-3)]">
          {detail}
        </div>
      ) : null}
    </div>
  );
}

const ExcelMaterializationStatus: React.FC<ExcelMaterializationStatusProps> = ({
  state,
  readOnly = false,
  retrying = false,
  pendingNewFile = false,
  onRetry,
}) => {
  const { t } = useTranslation();

  if (pendingNewFile) {
    const hasExistingToReplace =
      Boolean(state?.has_saved_source) || Boolean(state?.success_slot_id);
    if (!hasExistingToReplace) {
      return null;
    }
    return (
      <Alert
        type="info"
        showIcon
        className="mb-3"
        message={
          <CompactAlertMessage
            title={t("dataSource.excelStatus.pendingNewFile")}
            detail={t("dataSource.excelStatus.pendingNewFileHint")}
          />
        }
      />
    );
  }

  if (!state?.status) return null;

  const status = state.status;
  const successTime = formatSuccessTime(state.success_updated_at);
  const showRetry = Boolean(state.can_retry) && !readOnly && Boolean(onRetry);
  const retryAction = showRetry ? (
    <Button size="small" loading={retrying} onClick={onRetry}>
      {t("dataSource.excelStatus.retry")}
    </Button>
  ) : undefined;

  if (status === "ready") {
    return (
      <Alert
        type="success"
        showIcon
        className="mb-3"
        message={
          <CompactAlertMessage
            title={t("dataSource.excelStatus.ready")}
            detail={
              successTime
                ? t("dataSource.excelStatus.successAt", "Imported at {time}", {
                  time: successTime,
                })
                : undefined
            }
          />
        }
      />
    );
  }

  if (status === "processing") {
    return (
      <Alert
        type="info"
        showIcon
        className="mb-3"
        message={
          <CompactAlertMessage
            title={
              state.success_slot_id
                ? t("dataSource.excelStatus.processingWithPrevious")
                : t("dataSource.excelStatus.processing")
            }
            detail={
              successTime
                ? t(
                  "dataSource.excelStatus.usingPreviousAt",
                  "Still using the result from {time}",
                  { time: successTime },
                )
                : t("dataSource.excelStatus.processingHint")
            }
          />
        }
      />
    );
  }

  if (status === "update_failed_using_previous") {
    const detail =
      state.error_summary || t("dataSource.excelStatus.updateFailed");
    const previousAt = successTime
      ? t(
        "dataSource.excelStatus.usingPreviousAt",
        "Still using the result from {time}",
        { time: successTime },
      )
      : "";
    return (
      <Alert
        type="warning"
        showIcon
        className="mb-3"
        message={
          <CompactAlertMessage
            title={t("dataSource.excelStatus.updateFailedUsingPrevious")}
            detail={[detail, previousAt].filter(Boolean).join("；")}
          />
        }
        action={retryAction}
      />
    );
  }

  if (status === "needs_upload") {
    return (
      <Alert
        type="warning"
        showIcon
        className="mb-3"
        message={
          <CompactAlertMessage
            title={t("dataSource.excelStatus.needsUpload")}
            detail={t("dataSource.excelStatus.needsUploadDescription")}
          />
        }
      />
    );
  }

  if (status === "failed") {
    const summary =
      state.error_summary || t("dataSource.excelStatus.failedUnknown");
    return (
      <Alert
        type="error"
        showIcon
        className="mb-3"
        message={
          <CompactAlertMessage
            title={`${t("dataSource.excelStatus.failed")}：${summary}`}
            detail={resolveFailedHint(t, state)}
          />
        }
        action={retryAction}
      />
    );
  }

  return null;
};

export default ExcelMaterializationStatus;
