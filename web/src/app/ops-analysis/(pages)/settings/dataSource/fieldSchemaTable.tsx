"use client";

import React, { useImperativeHandle } from "react";
import { Button, Input, Select } from "antd";
import {
  MinusCircleOutlined,
  PlusCircleOutlined,
} from "@ant-design/icons";
import CustomTable from "@/components/custom-table";
import CompactEmptyState from "@/components/compact-empty-state";
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
  readOnly?: boolean;
}

const FieldSchemaTable = React.forwardRef<
  FieldSchemaTableRef,
  FieldSchemaTableProps
>(({ schemaFields, onChange, readOnly = false }, ref) => {
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
  const roleOptions = [
    { label: t("dataSource.fieldRoles.dimension"), value: "dimension" },
    { label: t("dataSource.fieldRoles.measure"), value: "measure" },
    { label: t("dataSource.fieldRoles.identity"), value: "identity" },
  ];
  const modeOptions = ["detail", "count", "distribution", "aggregate", "series", "value"].map((mode) => ({
    label: t(`dataSource.analysisModes.${mode}`),
    value: mode,
  }));

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
    value: string | string[] | undefined,
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
          size="small"
          disabled={readOnly}
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
          size="small"
          disabled={readOnly}
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
          size="small"
          disabled={readOnly}
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
      title: t("dataSource.fieldRole"),
      dataIndex: "role",
      key: "role",
      width: 120,
      render: (_: unknown, record: SchemaField) => (
        <Select
          size="small"
          allowClear
          disabled={readOnly}
          value={record.role}
          options={roleOptions}
          placeholder={t("dataSource.fieldRolePlaceholder")}
          style={{ width: "100%" }}
          onChange={(val) =>
            handleSchemaFieldChange(record.id, "role", val)
          }
        />
      ),
    },
    {
      title: t("dataSource.fieldModes"),
      dataIndex: "modes",
      key: "modes",
      width: 180,
      render: (_: unknown, record: SchemaField) => (
        <Select
          size="small"
          mode="multiple"
          allowClear
          disabled={readOnly}
          value={record.modes}
          options={modeOptions}
          placeholder={t("dataSource.fieldModesPlaceholder")}
          style={{ width: "100%" }}
          onChange={(val) =>
            handleSchemaFieldChange(record.id, "modes", val)
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
          size="small"
          disabled={readOnly}
          value={record.description || ""}
          placeholder={t("dataSource.fieldDescription")}
          onChange={(e) =>
            handleSchemaFieldChange(record.id, "description", e.target.value)
          }
        />
      ),
    },
    ...(readOnly
      ? []
      : [
        {
          title: t("dataSource.operation"),
          key: "action",
          width: 80,
          render: (_: unknown, record: SchemaField, index: number) => (
              <div
                style={{
                  display: "flex",
                  gap: "4px",
                  justifyContent: "center",
                }}
              >
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
      ]),
  ];

  return (
    <div>
      <CustomTable
        rowKey="id"
        size="small"
        columns={schemaFieldColumns}
        dataSource={schemaFields}
        pagination={false}
        bordered
        locale={{
          emptyText: (
            <CompactEmptyState description={t("common.noData")} />
          ),
        }}
        rowDraggable={!readOnly && schemaFields.length > 0}
        onRowDragEnd={(targetTableData) =>
          handleSchemaFieldDragEnd((targetTableData || []) as SchemaField[])
        }
      />
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
