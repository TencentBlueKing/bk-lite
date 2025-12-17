import React from 'react';
import { Input, InputNumber, Select, Button, Tooltip } from 'antd';
import {
  PlusCircleOutlined,
  MinusCircleOutlined,
  ExclamationCircleFilled,
} from '@ant-design/icons';
import { useTranslation } from '@/utils/i18n';
import GroupSelect from '@/components/group-tree-select';

/**
 * 表格渲染器 - 用于渲染控制器安装表格的列
 */
export const useTableRenderer = () => {
  const { t } = useTranslation();

  const renderTableColumn = (
    columnConfig: any,
    dataSource: any[],
    onTableDataChange: (data: any[]) => void
  ) => {
    const {
      name,
      label,
      type,
      widget_props = {},
      required = false,
      rules = [],
    } = columnConfig;

    const column: any = {
      title: label,
      dataIndex: name,
      key: name,
      width: widget_props.width || 150,
    };

    const handleChange = (value: any, record: any, index: number) => {
      const newData = [...dataSource];
      newData[index] = {
        ...newData[index],
        [name]: value,
      };

      // onChange时触发验证
      let errorMsg: string | null = null;

      // 必填验证
      if (required) {
        if (
          value === undefined ||
          value === null ||
          value === '' ||
          (Array.isArray(value) && value.length === 0)
        ) {
          errorMsg = t('common.required');
        }
      }

      // 正则验证（只在有值时验证）
      if (rules.length > 0 && !errorMsg) {
        for (const rule of rules) {
          if (rule.type === 'pattern') {
            if (value !== undefined && value !== null && value !== '') {
              const regex = new RegExp(rule.pattern);
              if (!regex.test(String(value))) {
                errorMsg = rule.message || t('common.formatError');
                break;
              }
            }
          }
        }
      }

      // 更新错误状态
      newData[index] = {
        ...newData[index],
        [`${name}_error`]: errorMsg,
      };

      onTableDataChange(newData);
    };

    switch (type) {
      case 'input':
        column.render = (text: any, record: any, index: number) => {
          const errorMsg = record[`${name}_error`];
          return (
            <div className="flex items-center gap-[8px]">
              <Input
                value={record[name]}
                placeholder={widget_props.placeholder}
                onChange={(e) => handleChange(e.target.value, record, index)}
                status={errorMsg ? 'error' : ''}
                className="flex-1"
              />
              {errorMsg && (
                <Tooltip title={errorMsg}>
                  <ExclamationCircleFilled className="text-[#ff4d4f] text-[14px] cursor-pointer flex-shrink-0" />
                </Tooltip>
              )}
            </div>
          );
        };
        break;

      case 'password':
        column.render = (text: any, record: any, index: number) => {
          const errorMsg = record[`${name}_error`];
          return (
            <div className="flex items-center gap-[8px]">
              <Input.Password
                value={record[name]}
                placeholder={widget_props.placeholder}
                onChange={(e) => handleChange(e.target.value, record, index)}
                status={errorMsg ? 'error' : ''}
                className="flex-1"
              />
              {errorMsg && (
                <Tooltip title={errorMsg}>
                  <ExclamationCircleFilled className="text-[#ff4d4f] text-[14px] cursor-pointer flex-shrink-0" />
                </Tooltip>
              )}
            </div>
          );
        };
        break;

      case 'inputNumber':
        column.render = (text: any, record: any, index: number) => {
          const errorMsg = record[`${name}_error`];
          return (
            <div className="flex items-center gap-[8px]">
              <InputNumber
                className="flex-1"
                value={record[name]}
                min={widget_props.min}
                precision={widget_props.precision}
                placeholder={widget_props.placeholder}
                onChange={(value) => handleChange(value, record, index)}
                status={errorMsg ? 'error' : ''}
              />
              {errorMsg && (
                <Tooltip title={errorMsg}>
                  <ExclamationCircleFilled className="text-[#ff4d4f] text-[14px] cursor-pointer flex-shrink-0" />
                </Tooltip>
              )}
            </div>
          );
        };
        break;

      case 'select':
        column.render = (text: any, record: any, index: number) => {
          const errorMsg = record[`${name}_error`];
          return (
            <div className="flex items-center gap-[8px]">
              <Select
                value={record[name]}
                mode={widget_props.mode}
                placeholder={widget_props.placeholder}
                options={widget_props.options || []}
                onChange={(value) => handleChange(value, record, index)}
                status={errorMsg ? 'error' : ''}
                className="flex-1"
              />
              {errorMsg && (
                <Tooltip title={errorMsg}>
                  <ExclamationCircleFilled className="text-[#ff4d4f] text-[14px] cursor-pointer flex-shrink-0" />
                </Tooltip>
              )}
            </div>
          );
        };
        break;

      case 'group_select':
        column.render = (text: any, record: any, index: number) => {
          const errorMsg = record[`${name}_error`];
          return (
            <div className="flex items-center gap-[8px]">
              <div className="flex-1">
                <GroupSelect
                  value={record[name]}
                  mode={widget_props.mode}
                  placeholder={widget_props.placeholder}
                  onChange={(value) => handleChange(value, record, index)}
                />
              </div>
              {errorMsg && (
                <Tooltip title={errorMsg}>
                  <ExclamationCircleFilled className="text-[#ff4d4f] text-[14px] cursor-pointer flex-shrink-0" />
                </Tooltip>
              )}
            </div>
          );
        };
        break;

      default:
        column.render = (text: any) => text;
    }

    return column;
  };

  const renderActionColumn = (
    dataSource: any[],
    onAdd: (row: any) => void,
    onDelete: (row: any) => void
  ) => {
    return {
      title: t('common.actions'),
      dataIndex: 'action',
      width: 80,
      fixed: 'right' as const,
      key: 'action',
      render: (value: string, row: any, index: number) => {
        return (
          <>
            <Button
              type="link"
              icon={<PlusCircleOutlined />}
              onClick={() => onAdd(row)}
            ></Button>
            {!!index && (
              <Button
                type="link"
                icon={<MinusCircleOutlined />}
                onClick={() => onDelete(row)}
              ></Button>
            )}
          </>
        );
      },
    };
  };

  return {
    renderTableColumn,
    renderActionColumn,
  };
};
