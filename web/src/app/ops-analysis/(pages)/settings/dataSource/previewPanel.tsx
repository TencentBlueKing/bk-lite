"use client";

import React from "react";
import { Button, Empty } from "antd";
import CustomTable from "@/components/custom-table";
import { useTranslation } from "@/utils/i18n";
import {
  DataSourcePreviewResult,
  ResponseFieldDefinition,
} from "@/app/ops-analysis/types/dataSource";

interface PreviewPanelProps {
  previewData: DataSourcePreviewResult | null;
  previewLoading: boolean;
  onPreview: () => void;
  onApplyPreviewFields: () => void;
}

const PreviewPanel: React.FC<PreviewPanelProps> = ({
  previewData,
  previewLoading,
  onPreview,
  onApplyPreviewFields,
}) => {
  const { t } = useTranslation();
  const previewColumns = React.useMemo(() => {
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
  }, [previewData]);

  return (
    <div style={{ margin: "24px 0 0 42px" }}>
      <div
        style={{
          marginBottom: 8,
          color: "var(--color-text-1)",
          fontSize: 14,
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
        }}
      >
        <span>{t("dataSource.previewData")}：</span>
        <div>
          {previewData?.fields?.length ? (
            <Button
              type="link"
              size="small"
              onClick={onApplyPreviewFields}
              style={{ paddingInline: 4 }}
            >
              {t("dataSource.applyPreviewFields")}
            </Button>
          ) : null}
          <Button
            type="primary"
            size="small"
            loading={previewLoading}
            onClick={onPreview}
            style={{ marginLeft: 10 }}
          >
            {t("dataSource.samplePreview")}
          </Button>
        </div>
      </div>
      {previewData?.items?.length ? (
        <CustomTable
          rowKey={(_, index) => String(index)}
          columns={previewColumns}
          dataSource={previewData.items}
          pagination={false}
          scroll={{ x: "max-content", y: 240 }}
          size="small"
        />
      ) : (
        <Empty
          image={Empty.PRESENTED_IMAGE_SIMPLE}
          description={t("common.noData")}
        />
      )}
    </div>
  );
};

export default PreviewPanel;
