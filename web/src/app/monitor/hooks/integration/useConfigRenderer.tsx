import React from 'react';
import { Form, Input, InputNumber, Select, Checkbox } from 'antd';
import Password from '@/components/password';
import GroupTreeSelector from '@/components/group-tree-select';
import { useTranslation } from '@/utils/i18n';

export const useConfigRenderer = () => {
  const { t } = useTranslation();
  const FORM_WIDGET_WIDTH = 300;
  const FORM_WIDGET_WIDTH_CLASS = 'w-[300px]';

  const renderFormField = (fieldConfig: any) => {
    const {
      name,
      label,
      type,
      required = false,
      default_value,
      widget_props = {},
      options = [],
      dependency,
      rules = [],
      description,
    } = fieldConfig;

    const formRules = [
      ...(required ? [{ required: true, message: t('common.required') }] : []),
      ...rules,
    ];
    const watchField = dependency?.field;

    const shouldUpdate = watchField
      ? (prevValues: any, currentValues: any) => {
        if (typeof watchField === 'string') {
          return prevValues[watchField] !== currentValues[watchField];
        }
        if (Array.isArray(watchField)) {
          return watchField.some(
            (field: string) => prevValues[field] !== currentValues[field]
          );
        }
        return false;
      }
      : undefined;

    const isFieldVisible = (getFieldValue: any) => {
      if (!watchField) return true;
      if (typeof watchField === 'string') {
        const watchValue = getFieldValue(watchField);
        if (dependency.value !== undefined) {
          return watchValue === dependency.value;
        }
      }
      if (Array.isArray(watchField)) {
        return watchField.every((field: string, index: number) => {
          const watchValue = getFieldValue(field);
          const conditions = dependency.conditions?.[index] || [];
          return conditions.some((condition: any) => {
            if (condition.equals !== undefined) {
              return watchValue === condition.equals;
            }
            if (condition.in !== undefined) {
              return condition.in.includes(watchValue);
            }
            return false;
          });
        });
      }
      return true;
    };

    const renderWidget = () => {
      switch (type) {
        case 'input':
          return (
            <Input
              {...widget_props}
              placeholder={widget_props.placeholder || label}
              className={`${FORM_WIDGET_WIDTH_CLASS} mr-[10px]`}
            />
          );

        case 'password':
          return (
            <Password
              {...widget_props}
              placeholder={widget_props.placeholder || label}
              className={`${FORM_WIDGET_WIDTH_CLASS} mr-[10px]`}
            />
          );

        case 'inputNumber':
          const { addonAfter, ...restProps } = widget_props;
          return (
            <InputNumber
              {...restProps}
              placeholder={widget_props.placeholder || label}
              className="mr-[10px]"
              style={{
                width: `${FORM_WIDGET_WIDTH}px`,
                verticalAlign: 'middle',
              }}
              min={widget_props.min || 1}
              precision={
                widget_props.precision !== undefined
                  ? widget_props.precision
                  : 0
              }
              addonAfter={addonAfter ? addonAfter : undefined}
            />
          );

        case 'select':
          return (
            <Select
              {...widget_props}
              placeholder={widget_props.placeholder || label}
              showSearch
              className="mr-[10px]"
              style={{ width: `${FORM_WIDGET_WIDTH}px` }}
            >
              {options.map((option: any) => (
                <Select.Option key={option.value} value={option.value}>
                  {option.label}
                </Select.Option>
              ))}
            </Select>
          );

        case 'textarea':
          return (
            <Input.TextArea
              {...widget_props}
              placeholder={widget_props.placeholder || label}
              className={FORM_WIDGET_WIDTH_CLASS}
              autoSize={{ minRows: 3, maxRows: 6 }}
            />
          );

        case 'checkbox':
          return (
            <Checkbox {...widget_props}>{widget_props.label || ''}</Checkbox>
          );

        case 'checkbox_group':
          return (
            <Checkbox.Group {...widget_props} style={{ width: '100%' }}>
              <div
                style={{
                  display: 'flex',
                  flexDirection: 'column',
                  gap: '12px',
                }}
              >
                {options.map((option: any) => (
                  <Checkbox key={option.value} value={option.value}>
                    <span>
                      <span className="w-[80px] inline-block">
                        {option.label}
                      </span>
                      {option.description && (
                        <span className="text-[var(--color-text-3)] text-[12px]">
                          {option.description}
                        </span>
                      )}
                    </span>
                  </Checkbox>
                ))}
              </div>
            </Checkbox.Group>
          );

        case 'inputNumber_with_unit':
          return (
            <Input.Group compact>
              <InputNumber
                {...widget_props}
                placeholder={widget_props.placeholder || label}
                style={{ width: 'calc(100% - 80px)' }}
              />
              <Select
                defaultValue={widget_props.unit_options?.[0]?.value}
                style={{ width: 80 }}
              >
                {(widget_props.unit_options || []).map((option: any) => (
                  <Select.Option key={option.value} value={option.value}>
                    {option.label}
                  </Select.Option>
                ))}
              </Select>
            </Input.Group>
          );

        default:
          return (
            <Input placeholder={label} className={FORM_WIDGET_WIDTH_CLASS} />
          );
      }
    };

    if (dependency?.field) {
      return (
        <Form.Item noStyle shouldUpdate={shouldUpdate} key={name}>
          {({ getFieldValue }) =>
            isFieldVisible(getFieldValue) ? (
              <Form.Item required={required} label={label}>
                <Form.Item
                  noStyle
                  name={name}
                  rules={formRules}
                  initialValue={default_value}
                >
                  {renderWidget()}
                </Form.Item>
                {description && (
                  <span
                    className="text-[12px] text-[var(--color-text-3)]"
                    style={{ verticalAlign: 'middle' }}
                  >
                    {description}
                  </span>
                )}
              </Form.Item>
            ) : null
          }
        </Form.Item>
      );
    }

    return (
      <Form.Item key={name} required={required} label={label}>
        <Form.Item
          noStyle
          name={name}
          rules={formRules}
          initialValue={default_value}
        >
          {renderWidget()}
        </Form.Item>
        {description && (
          <span
            className="text-[12px] text-[var(--color-text-3)]"
            style={{ verticalAlign: 'middle' }}
          >
            {description}
          </span>
        )}
      </Form.Item>
    );
  };

  const getFilteredOptionsForRow = (
    options: any[],
    enable_row_filter: boolean,
    mode: string | undefined,
    dataSource: any[],
    currentIndex: number,
    fieldName: string
  ) => {
    if (!enable_row_filter) {
      return options;
    }
    const selectedValues = new Set<any>();
    dataSource.forEach((row, i) => {
      if (i !== currentIndex) {
        const value = row[fieldName];
        if (mode === 'multiple') {
          if (Array.isArray(value)) {
            value.forEach((v) => selectedValues.add(v));
          }
        } else {
          value && selectedValues.add(value);
        }
      }
    });
    return options.filter((opt: any) => !selectedValues.has(opt.value));
  };

  const renderTableColumn = (
    columnConfig: any,
    dataSource: any[],
    onTableDataChange: (data: any[]) => void,
    externalOptions?: Record<string, any[]>
  ) => {
    const {
      name,
      label,
      type,
      widget_props = {},
      change_handler,
      options_key,
      enable_row_filter = false,
    } = columnConfig;

    let options = columnConfig.options || [];
    if (!options?.length && externalOptions) {
      let finalOptionsKey = options_key;
      if (!finalOptionsKey && ['node_ids', 'group_ids'].includes(name)) {
        finalOptionsKey = `${name}_option`;
      }
      if (finalOptionsKey) {
        options = externalOptions[finalOptionsKey] || [];
      }
    }

    const column: any = {
      title: label,
      dataIndex: name,
      key: name,
      width: widget_props.width || 200,
    };

    const handleChange = (value: any, record: any, index: number) => {
      const newData = [...dataSource];
      newData[index] = { ...newData[index], [name]: value };
      if (change_handler) {
        const {
          type,
          target_field,
          source_fields = [],
          separator = ':',
        } = change_handler;
        if (type === 'simple') {
          const sourceValue = source_fields[0]
            ? newData[index][source_fields[0]]
            : value;
          newData[index][target_field] = sourceValue;
        } else if (type === 'combine') {
          const values = source_fields.map(
            (field: string) => newData[index][field] || ''
          );
          newData[index][target_field] = values.join(separator);
        }
      }
      onTableDataChange(newData);
    };

    switch (type) {
      case 'input':
        column.render = (text: any, record: any, index: number) => (
          <Input
            value={text}
            onChange={(e) => handleChange(e.target.value, record, index)}
            placeholder={widget_props.placeholder || label}
            {...widget_props}
          />
        );
        break;

      case 'inputNumber':
        column.render = (text: any, record: any, index: number) => (
          <InputNumber
            value={text}
            onChange={(value) => handleChange(value, record, index)}
            placeholder={widget_props.placeholder || label}
            style={{ width: '100%' }}
            {...widget_props}
          />
        );
        break;

      case 'select':
        column.render = (text: any, record: any, index: number) => {
          const filteredOptions = getFilteredOptionsForRow(
            options,
            enable_row_filter,
            widget_props.mode,
            dataSource,
            index,
            name
          );

          return (
            <Select
              value={text}
              onChange={(value) => handleChange(value, record, index)}
              placeholder={widget_props.placeholder || label}
              style={{ width: '100%' }}
              {...widget_props}
            >
              {filteredOptions.map((option: any) => (
                <Select.Option key={option.value} value={option.value}>
                  {option.label}
                </Select.Option>
              ))}
            </Select>
          );
        };
        break;

      case 'group_select':
        column.render = (text: any, record: any, index: number) => {
          const handleGroupChange = (val: number | number[] | undefined) => {
            const groupArray = Array.isArray(val) ? val : val ? [val] : [];
            handleChange(groupArray, record, index);
          };

          return (
            <GroupTreeSelector
              value={text}
              onChange={handleGroupChange}
              {...widget_props}
            />
          );
        };
        break;

      case 'password':
        column.render = (text: any, record: any, index: number) => (
          <Password
            value={text}
            onChange={(value) => handleChange(value, record, index)}
            placeholder={widget_props.placeholder || label}
            {...widget_props}
          />
        );
        break;

      default:
        column.render = (text: any) => text;
    }

    return column;
  };

  return {
    renderFormField,
    renderTableColumn,
  };
};
