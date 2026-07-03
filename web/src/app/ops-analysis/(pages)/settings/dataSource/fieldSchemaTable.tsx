"use client";

import React, { useImperativeHandle } from "react";
import { Button, Empty, Input, Select, Tooltip } from "antd";
import {
  MinusCircleOutlined,
  PlusCircleOutlined,
  QuestionCircleOutlined,
} from "@ant-design/icons";
import CustomTable from "@/components/custom-table";
import { useTranslation } from "@/utils/i18n";
import { ResponseFieldDefinition } from "@/app/ops-analysis/types/dataSource";
import {
  createDefaultSchemaField,
  SchemaField,
  validateSchemaFields,
} from "./operateModalUtils";

export interface FieldSchemaTableRef {
  validate: () => boolean;
  clearValidation: () => void;
}

interface FieldSchemaTableProps {
  schemaFields: SchemaField[];
  onChange: (schemaFields: SchemaField[]) => void;
}

const FieldSchemaTable = React.forwardRef<
  FieldSchemaTableRef,
  FieldSchemaTableProps
>(({ schemaFields, onChange }, ref) => {
  const { t } = useTranslation();
  const [duplicateFieldKeys, setDuplicateFieldKeys] = React.useState<string[]>(
    [],
  );
  const [emptyFieldKeys, setEmptyFieldKeys] = React.useState<string[]>([]);

  const valueTypeOptions = [
    { label: t("dataSource.valueTypes.string"), value: "string" },
    { label: t("dataSource.valueTypes.number"), value: "number" },
    { label: t("dataSource.valueTypes.boolean"), value: "boolean" },
    { label: t("dataSource.valueTypes.datetime"), value: "datetime" },
  ];

  const clearValidation = () => {
    setDuplicateFieldKeys([]);
    setEmptyFieldKeys([]);
  };

  const applyValidation = (fields: SchemaField[]) => {
    const result = validateSchemaFields(fields);
    setDuplicateFieldKeys(result.duplicateFieldKeys);
    setEmptyFieldKeys(result.emptyFieldKeys);
    return result.isValid;
  };

  useImperativeHandle(ref, () => ({
    validate: () => applyValidation(schemaFields),
    clearValidation,
  }));

  const handleSchemaFieldChange = (
    id: string,
    fieldName: keyof ResponseFieldDefinition,
    value: string,
  ) => {
    const newFields = schemaFields.map((field) =>
      field.id === id ? { ...field, [fieldName]: value } : field,
    );
    onChange(newFields);
    if (fieldName === "key") {
      applyValidation(newFields);
    }
  };

  const handleAddSchemaField = (index: number) => {
    const newField = createDefaultSchemaField();
    const newFields = [...schemaFields];
    newFields.splice(index + 1, 0, newField);
    onChange(newFields);
  };

  const handleDeleteSchemaField = (id: string) => {
    const newFields = schemaFields.filter((field) => field.id !== id);
    onChange(newFields);
    applyValidation(newFields);
  };

  const handleSchemaFieldDragEnd = (targetTableData: SchemaField[]) => {
    const nextFields = (targetTableData || []).map((field) => ({
      ...field,
    }));
    onChange(nextFields);
    applyValidation(nextFields);
  };

  const schemaFieldColumns = [
    {
      title: t("dataSource.fieldKey"),
      dataIndex: "key",
      key: "key",
      width: 140,
      render: (_: unknown, record: SchemaField) => (
        <Input
          value={record.key}
          placeholder={t("dataSource.fieldKey")}
          onChange={(e) =>
            handleSchemaFieldChange(record.id, "key", e.target.value)
          }
          status={
            duplicateFieldKeys.includes(record.key) ||
            emptyFieldKeys.includes(record.id)
              ? "error"
              : undefined
          }
        />
      ),
    },
    {
      title: t("dataSource.fieldTitle"),
      dataIndex: "title",
      key: "title",
      width: 140,
      render: (_: unknown, record: SchemaField) => (
        <Input
          value={record.title}
          placeholder={t("dataSource.fieldTitle")}
          onChange={(e) =>
            handleSchemaFieldChange(record.id, "title", e.target.value)
          }
        />
      ),
    },
    {
      title: t("dataSource.fieldValueType"),
      dataIndex: "value_type",
      key: "value_type",
      width: 120,
      render: (_: unknown, record: SchemaField) => (
        <Select
          value={record.value_type}
          options={valueTypeOptions}
          style={{ width: "100%" }}
          onChange={(val) =>
            handleSchemaFieldChange(
              record.id,
              "value_type",
              val as ResponseFieldDefinition["value_type"],
            )
          }
        />
      ),
    },
    {
      title: t("dataSource.fieldDescription"),
      dataIndex: "description",
      key: "description",
      width: 160,
      render: (_: unknown, record: SchemaField) => (
        <Input
          value={record.description || ""}
          placeholder={t("dataSource.fieldDescription")}
          onChange={(e) =>
            handleSchemaFieldChange(record.id, "description", e.target.value)
          }
        />
      ),
    },
    {
      title: t("dataSource.operation"),
      key: "action",
      width: 80,
      render: (_: unknown, record: SchemaField, index: number) => (
        <div style={{ display: "flex", gap: "4px", justifyContent: "center" }}>
          <Button
            type="text"
            size="small"
            icon={<PlusCircleOutlined />}
            onClick={() => handleAddSchemaField(index)}
            style={{ border: "none", padding: "4px" }}
          />
          <Button
            type="text"
            size="small"
            icon={<MinusCircleOutlined />}
            onClick={() => handleDeleteSchemaField(record.id)}
            style={{ border: "none", padding: "4px" }}
          />
        </div>
      ),
    },
  ];

  return (
    <div style={{ margin: "24px 0 0 42px" }}>
      <div
        style={{
          marginBottom: "8px",
          color: "var(--color-text-1)",
          fontSize: "14px",
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
        }}
      >
        <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
          <span>{t("dataSource.responseFieldSchemaConfig")}</span>
          <Tooltip title={t("dataSource.schemaOptionalAutoGenTip")}>
            <QuestionCircleOutlined
              style={{ color: "var(--color-text-3)", fontSize: 14 }}
            />
          </Tooltip>
        </span>
        <Button
          type="dashed"
          size="small"
          icon={<PlusCircleOutlined />}
          onClick={() =>
            onChange([...schemaFields, createDefaultSchemaField()])
          }
        >
          {t("dataSource.addField")}
        </Button>
      </div>
      {schemaFields.length > 0 ? (
        <CustomTable
          rowKey="id"
          columns={schemaFieldColumns}
          dataSource={schemaFields}
          pagination={false}
          rowDraggable
          onRowDragEnd={(targetTableData) =>
            handleSchemaFieldDragEnd((targetTableData || []) as SchemaField[])
          }
        />
      ) : (
        <Empty
          image={Empty.PRESENTED_IMAGE_SIMPLE}
          description={t("common.noData")}
        />
      )}
      {duplicateFieldKeys.length > 0 && (
        <div
          style={{
            color: "var(--color-fail)",
            fontSize: "12px",
            marginTop: "2px",
            padding: "2px 8px",
          }}
        >
          {t("dataSource.duplicateFieldKeys")}
          {duplicateFieldKeys.join("、")}
        </div>
      )}
    </div>
  );
});

FieldSchemaTable.displayName = "FieldSchemaTable";

export default FieldSchemaTable;
