"use client";

import React, { useImperativeHandle } from "react";
import dayjs, { Dayjs } from "dayjs";
import { Button, DatePicker, Empty, Input, Select, Switch } from "antd";
import { MinusCircleOutlined, PlusCircleOutlined } from "@ant-design/icons";
import CustomTable from "@/components/custom-table";
import TimeSelector from "@/components/time-selector";
import { useTranslation } from "@/utils/i18n";
import { formatOpsRequestTime } from "@/app/ops-analysis/utils/dateTime";
import type {
  DataSourceParamFilterType,
  ParamItem,
} from "@/app/ops-analysis/types/dataSource";
import { createDefaultParam, validateParams } from "./operateModalUtils";

export interface ParamTableRef {
  validate: () => boolean;
  clearValidation: () => void;
}

interface ParamTableProps {
  params: ParamItem[];
  onChange: (params: ParamItem[]) => void;
}

const FormTimeSelector: React.FC<{
  value?: any;
  onChange?: (value: any) => void;
}> = ({ value, onChange }) => {
  const [selectValue, setSelectValue] = React.useState(10080);
  const [rangeValue, setRangeValue] = React.useState<any>(null);

  React.useEffect(() => {
    if (value !== undefined) {
      if (Array.isArray(value)) {
        setSelectValue(0);
        setRangeValue(value);
      } else {
        setSelectValue(value);
        setRangeValue(null);
      }
    } else {
      onChange?.(10080);
    }
  }, [value, onChange]);

  const handleChange = (range: number[], originValue: number | null) => {
    if (originValue === 0) {
      setSelectValue(0);
      setRangeValue(range);
      onChange?.(range);
    } else if (originValue !== null) {
      setSelectValue(originValue);
      setRangeValue(null);
      onChange?.(originValue);
    }
  };

  const formatRangeValue = (value: any): [dayjs.Dayjs, dayjs.Dayjs] | null => {
    if (Array.isArray(value) && value.length === 2) {
      return [dayjs(value[0]), dayjs(value[1])];
    }
    return null;
  };

  return (
    <div className="w-full">
      <TimeSelector
        onlyTimeSelect
        className="w-full"
        defaultValue={{
          selectValue: selectValue,
          rangePickerVaule: formatRangeValue(rangeValue),
        }}
        onChange={handleChange}
      />
    </div>
  );
};

const ParamTable = React.forwardRef<ParamTableRef, ParamTableProps>(
  ({ params, onChange }, ref) => {
    const { t } = useTranslation();
    const [duplicateNames, setDuplicateNames] = React.useState<string[]>([]);
    const [emptyNames, setEmptyNames] = React.useState<string[]>([]);
    const [emptyAliases, setEmptyAliases] = React.useState<string[]>([]);

    const clearValidation = () => {
      setDuplicateNames([]);
      setEmptyNames([]);
      setEmptyAliases([]);
    };

    const paramTypeOptions = [
      { label: t("dataSource.paramTypes.string"), value: "string" },
      { label: t("dataSource.paramTypes.number"), value: "number" },
      { label: t("dataSource.paramTypes.boolean"), value: "boolean" },
      { label: t("dataSource.paramTypes.date"), value: "date" },
      { label: t("dataSource.paramTypes.timeRange"), value: "timeRange" },
    ];

    const filterTypeOptions: Array<{
      label: string;
      value: DataSourceParamFilterType;
    }> = [
      { label: t("dataSource.filterTypes.filter"), value: "filter" },
      { label: t("dataSource.filterTypes.fixed"), value: "fixed" },
      { label: t("dataSource.filterTypes.params"), value: "params" },
      { label: t("dataSource.filterTypes.widget"), value: "widget" },
    ];

    const applyValidation = (nextParams: ParamItem[]) => {
      const result = validateParams(nextParams);
      setDuplicateNames(result.duplicateNames);
      setEmptyNames(result.emptyNames);
      setEmptyAliases(result.emptyAliases);
      return result.isValid;
    };

    useImperativeHandle(ref, () => ({
      validate: () => applyValidation(params),
      clearValidation,
    }));

    const handleAliasChange = (val: string, id: string) => {
      onChange(
        params.map((item) =>
          item.id === id ? { ...item, alias_name: val } : item,
        ),
      );
    };

    const handleAliasBlur = (val: string, id: string) => {
      const newParams = params.map((item) => {
        if (item.id === id) {
          return { ...item, alias_name: val.trim() };
        }
        return item;
      });
      onChange(newParams);
      applyValidation(newParams);
    };

    const handleDefaultChange = (val: any, id: string, type: string) => {
      onChange(
        params.map((item) => {
          if (item.id !== id) return item;
          let newValue = val;
          if (type === "boolean") {
            newValue = val;
          } else if (type === "number") {
            newValue = Number(val);
          } else if (type === "date") {
            if (!val) {
              newValue = "";
            } else if (val.format) {
              newValue = formatOpsRequestTime(val);
            } else {
              newValue = val;
            }
          } else if (type === "timeRange") {
            newValue = val;
          }
          return { ...item, value: newValue };
        }),
      );
    };

    const handleTypeChange = (val: string, id: string) => {
      onChange(
        params.map((item) => {
          if (item.id !== id) return item;
          let newValue: any = "";
          const newFilterType = item.filterType;

          if (val === "boolean") {
            newValue = false;
          } else if (val === "number") {
            newValue = 0;
          } else if (val === "date") {
            newValue = "";
          } else if (val === "timeRange") {
            newValue = 10080;
          } else {
            newValue = "";
          }

          return {
            ...item,
            type: val,
            value: newValue,
            filterType: newFilterType,
          };
        }),
      );
    };

    const handleFilterTypeChange = (
      val: DataSourceParamFilterType,
      id: string,
    ) => {
      onChange(
        params.map((item) =>
          item.id === id ? { ...item, filterType: val } : item,
        ),
      );
    };

    const handleAddParamAfter = (index: number) => {
      const newParam = createDefaultParam();
      const newParams = [...params];
      newParams.splice(index + 1, 0, newParam);
      onChange(newParams);
    };

    const handleDeleteParam = (id: string) => {
      const newParams = params.filter((item) => item.id !== id);
      onChange(newParams);
      applyValidation(newParams);
    };

    const handleParamNameChange = (val: string, id: string) => {
      onChange(
        params.map((item) =>
          item.id === id
            ? {
              ...item,
              name: val,
            }
            : item,
        ),
      );
    };

    const handleParamNameBlur = (val: string, id: string) => {
      const newParams = params.map((item) => {
        if (item.id === id) {
          return { ...item, name: val.trim() };
        }
        return item;
      });
      onChange(newParams);
      applyValidation(newParams);
    };

    const columns = [
      {
        title: t("dataSource.name"),
        dataIndex: "name",
        key: "name",
        width: 120,
        render: (_: any, record: ParamItem) => (
          <Input
            value={record.name}
            placeholder={t("dataSource.name")}
            onChange={(e) => handleParamNameChange(e.target.value, record.id!)}
            onBlur={(e) => handleParamNameBlur(e.target.value, record.id!)}
            status={
              duplicateNames.includes(record.name) ||
              emptyNames.includes(record.id!)
                ? "error"
                : undefined
            }
          />
        ),
      },
      {
        title: t("dataSource.aliasName"),
        dataIndex: "alias_name",
        key: "alias_name",
        width: 120,
        render: (_: any, record: ParamItem) => (
          <Input
            value={record.alias_name || ""}
            placeholder={t("dataSource.aliasName")}
            onChange={(e) => handleAliasChange(e.target.value, record.id!)}
            onBlur={(e) => handleAliasBlur(e.target.value, record.id!)}
            status={emptyAliases.includes(record.id!) ? "error" : undefined}
          />
        ),
      },
      {
        title: t("dataSource.paramType"),
        dataIndex: "type",
        key: "type",
        width: 110,
        render: (_: any, record: ParamItem) => (
          <Select
            value={record.type || "string"}
            options={paramTypeOptions}
            style={{ width: "100%" }}
            onChange={(val) => handleTypeChange(val, record.id!)}
          />
        ),
      },
      {
        title: t("dataSource.filterType"),
        dataIndex: "filterType",
        key: "filterType",
        width: 100,
        render: (_: any, record: ParamItem) => {
          return (
            <Select
              value={record.filterType || "fixed"}
              options={filterTypeOptions}
              style={{ width: "100%" }}
              onChange={(val) => handleFilterTypeChange(val, record.id!)}
            />
          );
        },
      },
      {
        title: t("dataSource.defaultValue"),
        dataIndex: "value",
        key: "value",
        width: 200,
        render: (text: any, record: ParamItem) => {
          const type = record.type || "string";
          const isFixed = record.name && record.filterType === "fixed";
          const commonProps = {
            style: {
              width: "100%",
              ...(isFixed && !text && text !== 0 && text !== false
                ? { borderColor: "var(--color-fail)" }
                : {}),
            },
          };

          if (type === "date") {
            return (
              <DatePicker
                showTime
                value={text ? dayjs(text) : undefined}
                onChange={(date: Dayjs | null) =>
                  handleDefaultChange(date, record.id!, "date")
                }
                style={{ width: "100%" }}
                format="YYYY-MM-DD HH:mm:ss"
              />
            );
          }
          if (type === "timeRange") {
            return (
              <FormTimeSelector
                value={text}
                onChange={(val: any) =>
                  handleDefaultChange(val, record.id!, "timeRange")
                }
              />
            );
          }
          if (type === "boolean") {
            return (
              <Switch
                checked={!!text}
                onChange={(val: boolean) =>
                  handleDefaultChange(val, record.id!, "boolean")
                }
              />
            );
          }
          if (type === "number") {
            return (
              <Input
                type="number"
                value={text}
                placeholder={
                  isFixed
                    ? t("dataSource.required")
                    : t("dataSource.defaultValue")
                }
                onChange={(e: React.ChangeEvent<HTMLInputElement>) =>
                  handleDefaultChange(e.target.value, record.id!, "number")
                }
                {...commonProps}
              />
            );
          }
          return (
            <Input
              value={text}
              placeholder={
                isFixed
                  ? t("dataSource.required")
                  : t("dataSource.defaultValue")
              }
              onChange={(e: React.ChangeEvent<HTMLInputElement>) =>
                handleDefaultChange(e.target.value, record.id!, "string")
              }
              {...commonProps}
            />
          );
        },
      },
      {
        title: t("dataSource.operation"),
        key: "action",
        width: 80,
        render: (_: any, record: ParamItem, index: number) => (
          <div
            style={{ display: "flex", gap: "4px", justifyContent: "center" }}
          >
            <Button
              type="text"
              size="small"
              icon={<PlusCircleOutlined />}
              onClick={() => handleAddParamAfter(index)}
              style={{
                border: "none",
                padding: "4px",
              }}
            />
            <Button
              type="text"
              size="small"
              icon={<MinusCircleOutlined />}
              onClick={() => handleDeleteParam(record.id!)}
              style={{
                border: "none",
                padding: "4px",
              }}
            />
          </div>
        ),
      },
    ];

    return (
      <div style={{ margin: "0 0 0 42px" }}>
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
          <span>{t("dataSource.params")}：</span>
          <Button
            type="dashed"
            size="small"
            icon={<PlusCircleOutlined />}
            onClick={() => onChange([...params, createDefaultParam()])}
          >
            {t("dataSource.addParam")}
          </Button>
        </div>
        {params.length > 0 ? (
          <CustomTable
            rowKey="id"
            columns={columns}
            dataSource={params}
            pagination={false}
          />
        ) : (
          <Empty
            image={Empty.PRESENTED_IMAGE_SIMPLE}
            description={t("common.noData")}
          />
        )}
        {duplicateNames.length > 0 && (
          <div
            style={{
              color: "var(--color-fail)",
              fontSize: "12px",
              marginTop: "2px",
              padding: "2px 8px",
            }}
          >
            {t("dataSource.duplicateParamNames")}
            {duplicateNames.join("、")}
          </div>
        )}
      </div>
    );
  },
);

ParamTable.displayName = "ParamTable";

export default ParamTable;
