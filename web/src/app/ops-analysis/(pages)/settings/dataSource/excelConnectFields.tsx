"use client";

import React from "react";
import { Form, Upload, Button } from "antd";
import { UploadOutlined } from "@ant-design/icons";
import type { RcFile, UploadFile } from "antd/es/upload/interface";
import { useTranslation } from "@/utils/i18n";
import ExcelMaterializationStatus, {
  ExcelMaterializationState,
} from "@/app/ops-analysis/components/ops-analysis-excel-materialization-status";

interface ExcelConnectFieldsProps {
  definitionReadOnly: boolean;
  sourceInlineError: string | null;
  excelFileList: UploadFile[];
  excelMaterialization: ExcelMaterializationState | null;
  excelRetryLoading: boolean;
  pendingNewFile: boolean;
  onFile: (file: RcFile) => void;
  onRemove: () => void;
  onRetry?: () => void;
}

export const ExcelConnectFields: React.FC<ExcelConnectFieldsProps> = ({
  definitionReadOnly,
  sourceInlineError,
  excelFileList,
  excelMaterialization,
  excelRetryLoading,
  pendingNewFile,
  onFile,
  onRemove,
  onRetry,
}) => {
  const { t } = useTranslation();

  return (
    <Form.Item
      validateStatus={sourceInlineError ? "error" : undefined}
      help={sourceInlineError || undefined}
    >
      <div>
        <Upload
          disabled={definitionReadOnly}
          accept=".xlsx"
          maxCount={1}
          beforeUpload={(file) => {
            onFile(file);
            return false;
          }}
          onRemove={() => {
            onRemove();
          }}
          fileList={excelFileList}
        >
          <Button icon={<UploadOutlined />}>
            {t("dataSource.selectExcelFile")}
          </Button>
        </Upload>
        <div className="mt-3">
          <ExcelMaterializationStatus
            state={excelMaterialization}
            readOnly={definitionReadOnly}
            retrying={excelRetryLoading}
            pendingNewFile={pendingNewFile}
            onRetry={onRetry}
          />
        </div>
      </div>
    </Form.Item>
  );
};
