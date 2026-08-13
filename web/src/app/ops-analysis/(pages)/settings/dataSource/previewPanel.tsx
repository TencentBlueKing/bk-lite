"use client";

import React from "react";
import { Alert, Button, Empty, Tabs, Tooltip } from "antd";
import { QuestionCircleOutlined } from "@ant-design/icons";
import CustomTable from "@/components/custom-table";
import { useTranslation } from "@/utils/i18n";
import {
  DataSourcePreviewResult,
  ResponseFieldDefinition,
} from "@/app/ops-analysis/types/dataSource";

interface PreviewPanelProps {
  previewData: DataSourcePreviewResult | null;
  rawPreviewData?: DataSourcePreviewResult | null;
  transformPreviewError?: string | null;
  previewActionError?: string | null;
  showTransformTabs?: boolean;
  previewLoading: boolean;
  onPreview: () => void;
  onApplyPreviewFields: () => void;
  readOnly?: boolean;
}

function buildColumns(previewData: DataSourcePreviewResult | null) {
  const fields = previewData?.fields?.length
    ? previewData.fields
    : Object.keys(previewData?.items?.[0] || {}).map((key) => ({
      key,
      title: key,
      value_type: "string" as ResponseFieldDefinition["value_type"],
    }));

  return fields.map((field) => ({
    title: field.title || field.key,
    dataIndex: field.key,
    key: field.key,
    width: 160,
    ellipsis: true,
    render: (value: unknown) => {
      if (value === null || value === undefined || value === "") return "-";
      if (typeof value === "object") return JSON.stringify(value);
      return String(value);
    },
  }));
}

function PreviewTable({
  previewData,
  emptyText,
}: {
  previewData: DataSourcePreviewResult | null;
  emptyText: string;
}) {
  const columns = React.useMemo(() => buildColumns(previewData), [previewData]);

  if (!previewData?.items?.length) {
    return (
      <div className="grid min-h-[72px] place-items-center rounded-md border border-[var(--color-border-1)] bg-[var(--color-bg)] py-2">
        <Empty
          image={Empty.PRESENTED_IMAGE_SIMPLE}
          description={emptyText}
          className="!my-0"
          styles={{ image: { height: 36 } }}
        />
      </div>
    );
  }

  return (
    <CustomTable
      rowKey={(_, index) => String(index)}
      columns={columns}
      dataSource={previewData.items}
      pagination={false}
      scroll={{ x: "max-content", y: 240 }}
      size="small"
      bordered
    />
  );
}

const PreviewPanel: React.FC<PreviewPanelProps> = ({
  previewData,
  rawPreviewData = null,
  transformPreviewError = null,
  previewActionError = null,
  showTransformTabs = false,
  previewLoading,
  onPreview,
  onApplyPreviewFields,
  readOnly = false,
}) => {
  const { t } = useTranslation();
  const warnings = previewData?.warnings?.length
    ? previewData.warnings
    : rawPreviewData?.warnings || [];
  const formErrorText = previewActionError || transformPreviewError;

  return (
    <div>
      <div className="mb-3 flex min-h-[22px] items-center justify-between gap-3">
        <h4 className="m-0 text-sm font-semibold leading-[22px] text-[var(--color-text-1)]">
          {t("dataSource.previewData")}
        </h4>
        {readOnly ? null : (
          <div className="flex shrink-0 items-center gap-3">
            {previewData?.fields?.length ? (
              <span className="inline-flex items-center gap-1">
                <Button
                  type="link"
                  size="small"
                  onClick={onApplyPreviewFields}
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
              onClick={onPreview}
            >
              {t("dataSource.samplePreview")}
            </Button>
          </div>
        )}
      </div>
      {warnings.length ? (
        <Alert
          type="warning"
          showIcon
          className="mb-3"
          message={warnings.join("；")}
        />
      ) : null}
      {formErrorText ? (
        <div className="mb-2 px-0.5 text-[12px] leading-5 text-[var(--color-fail)]">
          {previewActionError
            ? formErrorText
            : `${t("dataSource.transform.previewFailed")}：${formErrorText}`}
        </div>
      ) : null}
      {showTransformTabs ? (
        <Tabs
          size="small"
          items={[
            {
              key: "raw",
              label: t("dataSource.transform.rawSample"),
              children: (
                <PreviewTable
                  previewData={rawPreviewData}
                  emptyText={t("common.noData")}
                />
              ),
            },
            {
              key: "transformed",
              label: t("dataSource.transform.transformedSample"),
              children: (
                <PreviewTable
                  previewData={transformPreviewError ? null : previewData}
                  emptyText={t("common.noData")}
                />
              ),
            },
          ]}
        />
      ) : (
        <PreviewTable previewData={previewData} emptyText={t("common.noData")} />
      )}
    </div>
  );
};

export default PreviewPanel;
