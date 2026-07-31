import React from 'react';
import {
  Form,
  Input,
  InputNumber,
  Select,
  Checkbox,
  Button,
  Tooltip,
  Switch
} from 'antd';
import { ExclamationCircleFilled, MinusCircleOutlined, PlusOutlined } from '@ant-design/icons';
import Password from '@/components/password';
import GroupTreeSelector from '@/components/group-tree-select';
import { useTranslation } from '@/utils/i18n';
import FieldGuideTip from '@/app/monitor/(pages)/integration/list/detail/configure/fieldGuideTip';
import { applyTableChangeHandler } from './tableChangeHandler';
import {
  FILTER_MUTEX_PEERS,
  getSnmpFilterMutexLastKey,
  normalizeIfTypeTags,
  normalizeMutexValues
} from './snmpFilterMutex';

const mutexValuesEqual = (left: any, right: any) => {
  if (left === right) return true;
  if (Array.isArray(left) || Array.isArray(right)) {
    const leftList = Array.isArray(left) ? left : left == null || left === '' ? [] : [left];
    const rightList = Array.isArray(right)
      ? right
      : right == null || right === ''
        ? []
        : [right];
    if (leftList.length !== rightList.length) return false;
    return leftList.every((item, index) => String(item) === String(rightList[index]));
  }
  return false;
};

export const useConfigRenderer = () => {
  const { t } = useTranslation();
  const FORM_WIDGET_WIDTH = 300;
  const FORM_WIDGET_WIDTH_CLASS = 'w-[300px]';

  const renderFormField = (fieldConfig: any, mode?: string) => {
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
      editable,
      guide_short,
      tooltip
    } = fieldConfig;
    const guideTip = guide_short || tooltip || description;
    const hasGuideTip = Boolean(guideTip);
    // 悬浮提示已承载说明时，不再在控件旁重复展示同一段 description
    const showInlineDescription = Boolean(description && description !== guideTip);

    if (type === 'hidden') {
      return (
        <Form.Item key={name} name={name} initialValue={default_value} hidden>
          <Input type="hidden" />
        </Form.Item>
      );
    }

    if (type === 'key_value_list') {
      const tipText = guideTip || description;
      const addLabel =
        name === 'request_params'
          ? t('monitor.integrations.addRequestParam')
          : name === 'request_headers'
            ? t('monitor.integrations.addRequestHeader')
            : t('common.add');

      return (
        <Form.Item
          key={name}
          className="mb-3"
        >
          <Form.List name={name}>
            {(fields, { add, remove }) => (
              <div className="w-full max-w-[640px] overflow-hidden rounded-md border border-[var(--color-border)] bg-[var(--color-bg)]">
                <div className="flex items-center justify-between gap-3 border-b border-[var(--color-border)] bg-[var(--color-fill-1)] px-3 py-2">
                  <div className="inline-flex min-w-0 items-center text-[13px] font-medium leading-5 text-[var(--color-text-1)]">
                    <span className="truncate">{label}</span>
                    {tipText ? <FieldGuideTip short={tipText} /> : null}
                  </div>
                  <div className="shrink-0 text-[12px] leading-[18px] text-[var(--color-text-3)]">
                    {t('common.name')} / {t('common.value')}
                  </div>
                </div>
                <div className="space-y-2 px-3 py-2.5">
                  {fields.length === 0 && (
                    <div className="px-1 py-2 text-[12px] leading-[18px] text-[var(--color-text-3)]">
                      {t('monitor.integrations.keyValueEmpty')}
                    </div>
                  )}
                  {fields.map((field) => (
                    <div
                      key={field.key}
                      className="grid grid-cols-[minmax(0,1fr)_minmax(0,1.35fr)_28px] items-start gap-2"
                    >
                      <Form.Item
                        {...field}
                        name={[field.name, 'key']}
                        className="mb-0"
                        rules={[
                          ({ getFieldValue }) => ({
                            validator: async (_, value) => {
                              const key = String(value ?? '').trim();
                              const rowValue = String(
                                getFieldValue([name, field.name, 'value']) ?? ''
                              ).trim();
                              if (!key && rowValue) {
                                throw new Error(t('common.name') + t('common.required'));
                              }
                            },
                          }),
                        ]}
                      >
                        <Input placeholder={t('common.name')} className="w-full" />
                      </Form.Item>
                      <Form.Item {...field} name={[field.name, 'value']} className="mb-0">
                        <Input placeholder={t('common.value')} className="w-full" />
                      </Form.Item>
                      <button
                        type="button"
                        aria-label={t('common.delete')}
                        className="mt-[6px] inline-flex h-5 w-5 cursor-pointer items-center justify-center rounded text-[var(--color-text-3)] transition-colors duration-150 hover:bg-[var(--color-fill-2)] hover:text-[var(--color-fail)]"
                        onClick={() => remove(field.name)}
                      >
                        <MinusCircleOutlined />
                      </button>
                    </div>
                  ))}
                  <Button
                    type="link"
                    size="small"
                    icon={<PlusOutlined />}
                    className="!px-0"
                    onClick={() => add({ key: '', value: '' })}
                  >
                    {addLabel}
                  </Button>
                </div>
              </div>
            )}
          </Form.List>
        </Form.Item>
      );
    }

    const mutexPeerField = (FILTER_MUTEX_PEERS[name] ||
      (rules || []).find((rule: any) => rule?.type === 'mutex_with' && rule.field)?.field) as
      | string
      | undefined;
    const mutexPeerFields = mutexPeerField ? [mutexPeerField] : [];
    const mutexLastKey = mutexPeerField ? getSnmpFilterMutexLastKey(name) : undefined;
    const mutexPeerLabel = mutexPeerField
      ? t(`monitor.integrations.filterMutexFields.${mutexPeerField}`)
      : '';
    // react-intl 使用 ICU `{peer}`，不是 `{{peer}}`
    const mutexPeerOccupiedTip = mutexPeerLabel
      ? t('monitor.integrations.filterMutexPeerOccupied', '', { peer: mutexPeerLabel })
      : '';
    const isIfTypeFilterField =
      name === 'iftype_exclude' || name === 'iftype_include';

    const formRules = [
      ...(required ? [{ required: true, message: t('common.required') }] : []),
      ...(isIfTypeFilterField
        ? [
          {
            validator: async (_: unknown, value: unknown) => {
              const { rejected } = normalizeIfTypeTags(value);
              if (rejected.length) {
                throw new Error(
                  t('monitor.integrations.filterIfTypeInvalid', '', {
                    values: rejected.join(', ')
                  })
                );
              }
            }
          }
        ]
        : []),
      ...rules.flatMap((rule: any) => {
        if (rule?.type === 'mutex_with') {
          return [];
        }
        if (rule?.type === 'pattern' && rule.pattern) {
          return [
            {
              pattern: new RegExp(rule.pattern),
              message: rule.message || t('common.required')
            }
          ];
        }
        return [rule];
      })
      // 冲突仅在后填写侧右侧红字提示；保存仍由后端校验
    ];
    const watchField = dependency?.field;

    const shouldUpdate = (prevValues: any, currentValues: any) => {
      if (mutexPeerField) {
        if (!mutexValuesEqual(prevValues[mutexPeerField], currentValues[mutexPeerField])) {
          return true;
        }
        if (!mutexValuesEqual(prevValues[name], currentValues[name])) {
          return true;
        }
        if (
          mutexLastKey &&
          prevValues[mutexLastKey] !== currentValues[mutexLastKey]
        ) {
          return true;
        }
      }
      if (!watchField) return false;
      if (typeof watchField === 'string') {
        return prevValues[watchField] !== currentValues[watchField];
      }
      if (Array.isArray(watchField)) {
        return watchField.some(
          (field: string) => prevValues[field] !== currentValues[field]
        );
      }
      return false;
    };

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

    const locked = mode === 'edit' && editable === false;

    const renderLabel = () =>
      hasGuideTip ? (
        <span className="inline-flex items-center">
          {label}
          <FieldGuideTip short={guideTip} />
        </span>
      ) : (
        label
      );

    const renderWidget = () => {
      switch (type) {
        case 'input':
          return (
            <Input
              {...widget_props}
              disabled={Boolean(locked || widget_props.disabled)}
              placeholder={widget_props.placeholder || label}
              className={`${FORM_WIDGET_WIDTH_CLASS} mr-[10px]`}
            />
          );

        case 'password':
          return (
            <Password
              {...widget_props}
              clickToEdit={mode === 'edit' && editable !== false}
              placeholder={widget_props.placeholder || label}
              className={`${FORM_WIDGET_WIDTH_CLASS} mr-[10px]`}
            />
          );

        case 'inputNumber': {
          const { addonAfter, ...restProps } = widget_props;
          return (
            <InputNumber
              {...restProps}
              placeholder={widget_props.placeholder || label}
              className="mr-[10px]"
              style={{
                width: `${FORM_WIDGET_WIDTH}px`,
                verticalAlign: 'middle'
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
        }

        case 'select': {
          const allowCustomTags =
            name === 'iftype_exclude' || name === 'iftype_include';
          return (
            <Select
              {...widget_props}
              mode={allowCustomTags ? 'tags' : widget_props.mode}
              tokenSeparators={
                allowCustomTags
                  ? widget_props.tokenSeparators || [',']
                  : widget_props.tokenSeparators
              }
              disabled={Boolean(locked || widget_props.disabled)}
              placeholder={
                allowCustomTags
                  ? widget_props.placeholder ||
                    t('monitor.integrations.filterIfTypeTagsPlaceholder')
                  : widget_props.placeholder || label
              }
              showSearch
              optionFilterProp="label"
              className="mr-[10px]"
              style={{ width: `${FORM_WIDGET_WIDTH}px` }}
            >
              {options.map((option: any) => (
                <Select.Option key={option.value} value={option.value} label={option.label}>
                  {option.label}
                </Select.Option>
              ))}
            </Select>
          );
        }

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

        case 'switch':
          return <Switch {...widget_props} className="mr-[10px]" />;

        case 'checkbox_group':
          return (
            <Checkbox.Group {...widget_props} style={{ width: '100%' }}>
              <div
                style={{
                  display: 'flex',
                  flexDirection: 'column',
                  gap: '12px'
                }}
              >
                {options.map((option: any) => (
                  <Checkbox key={option.value} value={option.value}>
                    <span>
                      <span className="w-[80px] inline-block">
                        {option.label}
                      </span>
                      {option.description && (
                        <span className="text-[12px] text-[var(--color-text-3)]">
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

    const renderNamedControl = () => (
      <Form.Item
        noStyle
        name={name}
        rules={formRules}
        dependencies={mutexPeerFields}
        initialValue={default_value}
        valuePropName={type === 'switch' ? 'checked' : 'value'}
      >
        {renderWidget()}
      </Form.Item>
    );

    if (dependency?.field || mutexPeerField) {
      return (
        <Form.Item noStyle shouldUpdate={shouldUpdate} key={name}>
          {({ getFieldValue }) => {
            if (dependency?.field && !isFieldVisible(getFieldValue)) {
              return null;
            }
            const selfOccupied = normalizeMutexValues(getFieldValue(name)).length > 0;
            const peerOccupied = mutexPeerField
              ? normalizeMutexValues(getFieldValue(mutexPeerField)).length > 0
              : false;
            const lastChanged = mutexLastKey
              ? getFieldValue(mutexLastKey)
              : undefined;
            // 仅后填写的一侧展示提示
            const showMutexConflict = Boolean(
              mutexPeerField &&
                selfOccupied &&
                peerOccupied &&
                lastChanged === name
            );
            return (
              <Form.Item required={required} label={renderLabel()}>
                {renderNamedControl()}
                {showMutexConflict ? (
                  <span
                    className="text-[12px] leading-[18px] text-[var(--color-fail)]"
                    style={{ verticalAlign: 'middle' }}
                  >
                    {mutexPeerOccupiedTip}
                  </span>
                ) : null}
                {showInlineDescription && !showMutexConflict && (
                  <span
                    className="text-[12px] text-[var(--color-text-3)]"
                    style={{ verticalAlign: 'middle' }}
                  >
                    {description}
                  </span>
                )}
              </Form.Item>
            );
          }}
        </Form.Item>
      );
    }

    return (
      <Form.Item key={name} required={required} label={renderLabel()}>
        <Form.Item
          noStyle
          name={name}
          rules={formRules}
          initialValue={default_value}
          valuePropName={type === 'switch' ? 'checked' : 'value'}
        >
          {renderWidget()}
        </Form.Item>
        {showInlineDescription && (
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
      rules = [],
      required = false
    } = columnConfig;
    const { width: columnWidth, ...componentProps } = widget_props;

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
      width: columnWidth || 200
    };

    // 验证函数
    const validateField = (value: any): string | null => {
      // 如果字段标记为required，进行必填验证
      if (required) {
        if (
          value === undefined ||
          value === null ||
          value === '' ||
          (Array.isArray(value) && value.length === 0)
        ) {
          return t('common.required');
        }
      }
      // 如果有rules配置，按照rules验证（只支持pattern类型）
      if (rules.length > 0) {
        for (const rule of rules) {
          // 正则验证（只在有值时验证）
          if (rule.type === 'pattern') {
            if (value !== undefined && value !== null && value !== '') {
              const regex = new RegExp(rule.pattern);
              if (!regex.test(String(value))) {
                return rule.message || t('common.required');
              }
            }
          }
        }
      }
      return null;
    };

    const handleChange = (value: any, record: any, index: number) => {
      const newData = [...dataSource];
      newData[index] = { ...newData[index], [name]: value };
      // 验证当前字段
      const errorMsg = validateField(value);
      newData[index][`${name}_error`] = errorMsg;
      if (change_handler) {
        const changedRow = applyTableChangeHandler(
          newData[index],
          value,
          options,
          change_handler
        );
        if (changedRow !== newData[index]) {
          newData[index] = changedRow;
          // 清除目标字段的错误状态（因为值已经被更新了）
          newData[index][`${change_handler.target_field}_error`] = null;
        }
      }
      onTableDataChange(newData);
    };

    switch (type) {
      case 'input':
        column.render = (text: any, record: any, index: number) => {
          const errorMsg = record[`${name}_error`];
          return (
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <Input
                value={text}
                onChange={(e) => handleChange(e.target.value, record, index)}
                placeholder={componentProps.placeholder || label}
                status={errorMsg ? 'error' : ''}
                style={{ flex: 1 }}
                {...componentProps}
              />
              {errorMsg && (
                <Tooltip title={errorMsg}>
                  <ExclamationCircleFilled
                    style={{ color: 'var(--color-fail)', fontSize: '14px' }}
                  />
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
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <InputNumber
                value={text}
                onChange={(value) => handleChange(value, record, index)}
                placeholder={componentProps.placeholder || label}
                style={{ flex: 1 }}
                status={errorMsg ? 'error' : ''}
                {...componentProps}
              />
              {errorMsg && (
                <Tooltip title={errorMsg}>
                  <ExclamationCircleFilled
                    style={{ color: 'var(--color-fail)', fontSize: '14px' }}
                  />
                </Tooltip>
              )}
            </div>
          );
        };
        break;

      case 'select':
        column.render = (text: any, record: any, index: number) => {
          const errorMsg = record[`${name}_error`];
          const filteredOptions = getFilteredOptionsForRow(
            options,
            enable_row_filter,
            componentProps.mode,
            dataSource,
            index,
            name
          );

          return (
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <Select
                value={text}
                onChange={(value) => handleChange(value, record, index)}
                placeholder={componentProps.placeholder || label}
                style={{ flex: 1 }}
                status={errorMsg ? 'error' : ''}
                showSearch
                optionFilterProp="label"
                {...componentProps}
              >
                {filteredOptions.map((option: any) => (
                  <Select.Option
                    key={option.value}
                    value={option.value}
                    label={option.label}
                    disabled={option.disabled}
                  >
                    <Tooltip
                      title={
                        option.disabledReason
                          ? `${option.label} · ${option.disabledReason}`
                          : option.label
                      }
                    >
                      <span className="flex w-full min-w-0 items-center justify-between gap-2">
                        <span className="min-w-0 truncate">{option.label}</span>
                        {option.disabledReason && (
                          <span className="shrink-0 text-[12px] text-[var(--color-text-3)]">
                            {option.disabledReason}
                          </span>
                        )}
                      </span>
                    </Tooltip>
                  </Select.Option>
                ))}
              </Select>
              {errorMsg && (
                <Tooltip title={errorMsg}>
                  <ExclamationCircleFilled
                    style={{ color: 'var(--color-fail)', fontSize: '14px' }}
                  />
                </Tooltip>
              )}
            </div>
          );
        };
        break;

      case 'group_select':
        column.render = (text: any, record: any, index: number) => {
          const errorMsg = record[`${name}_error`];
          const handleGroupChange = (val: number | number[] | undefined) => {
            const groupArray = Array.isArray(val) ? val : val ? [val] : [];
            handleChange(groupArray, record, index);
          };

          return (
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <GroupTreeSelector
                value={text}
                onChange={handleGroupChange}
                status={errorMsg ? 'error' : ''}
                style={{ flex: 1 }}
                {...componentProps}
              />
              {errorMsg && (
                <Tooltip title={errorMsg}>
                  <ExclamationCircleFilled
                    style={{ color: 'var(--color-fail)', fontSize: '14px' }}
                  />
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
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <Password
                value={text}
                clickToEdit={false}
                onChange={(value) => handleChange(value, record, index)}
                placeholder={componentProps.placeholder || label}
                status={errorMsg ? 'error' : ''}
                style={{ flex: 1 }}
                {...componentProps}
              />
              {errorMsg && (
                <Tooltip title={errorMsg}>
                  <ExclamationCircleFilled
                    style={{ color: 'var(--color-fail)', fontSize: '14px' }}
                  />
                </Tooltip>
              )}
            </div>
          );
        };
        break;

      case 'switch':
        column.render = (text: any, record: any, index: number) => (
          <div style={{ display: 'flex', alignItems: 'center', minHeight: 32 }}>
            <Switch
              checked={Boolean(text)}
              onChange={(checked) => handleChange(checked, record, index)}
              {...componentProps}
            />
          </div>
        );
        break;

      default:
        column.render = (text: any) => text;
    }

    return column;
  };

  return {
    renderFormField,
    renderTableColumn
  };
};
