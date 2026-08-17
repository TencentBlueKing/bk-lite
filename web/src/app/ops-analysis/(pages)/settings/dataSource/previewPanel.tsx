"use client";

import React from "react";
import { Alert, Tabs } from "antd";
import CustomTable from "@/components/custom-table";
import CompactEmptyState from "@/components/compact-empty-state";
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
        <CompactEmptyState description={emptyText} />
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
}) => {
  const { t } = useTranslation();
  const warnings = previewData?.warnings?.length
    ? previewData.warnings
    : rawPreviewData?.warnings || [];
  const formErrorText = previewActionError || transformPreviewError;

  return (
    <div>
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
