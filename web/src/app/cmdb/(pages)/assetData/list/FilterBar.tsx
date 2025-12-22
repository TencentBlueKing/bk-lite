"use client";

import React, { useState } from 'react';
import { Tag, Button, Popover, Form, Input, InputNumber, Select, DatePicker, Checkbox, Space } from 'antd';
import { FunnelPlotFilled, CloseOutlined } from '@ant-design/icons';
import type { AttrFieldType } from '@/app/cmdb/types/assetManage';
import dayjs from 'dayjs';
import customParseFormat from 'dayjs/plugin/customParseFormat';
import styles from './FilterBar.module.scss';
import { useTranslation } from '@/utils/i18n';
dayjs.extend(customParseFormat);
import { useAssetDataStore, type FilterItem } from '@/app/cmdb/store';

const { RangePicker } = DatePicker;

// 筛选条件的数据格式（兼容旧代码，实际使用 FilterItem）
export interface FilterCondition {
  field: string;
  type: string;
  value?: any; // 值（时间类型时可能为空，使用 start 和 end）
  start?: string; // 时间范围开始
  end?: string; // 时间范围结束
}

export interface FilterBarProps {
  attrList?: AttrFieldType[];
  userList?: Array<{ id: string; username: string; display_name?: string }>;
  proxyOptions?: Array<{ proxy_id: string; proxy_name: string }>;
  onChange?: (filters: FilterItem[]) => void;
  onFilterChange?: (filters: FilterItem[]) => void;
}

const FilterBar: React.FC<FilterBarProps> = ({
  attrList = [],
  userList = [],
  proxyOptions = [],
  onChange,
  onFilterChange,
}) => {
  const { t } = useTranslation();
  const queryList = useAssetDataStore((state) => state.query_list);
  const remove = useAssetDataStore((state) => state.remove);
  const clear = useAssetDataStore((state) => state.clear);
  const update = useAssetDataStore((state) => state.update);

  const [editPopoverVisible, setEditPopoverVisible] = useState(false);
  const [editingFilter, setEditingFilter] = useState<FilterItem | null>(null);
  const [editingIndex, setEditingIndex] = useState<number>(-1);
  const [clickedTagIndex, setClickedTagIndex] = useState<number>(-1);
  const [form] = Form.useForm();

  // 根据 field 获取字段信息
  const getFieldInfo = (field: string): AttrFieldType | undefined => {
    return attrList.find((attr) => attr.attr_id === field);
  };

  // 根据 type 和 value 推断字段类型（用于没有 attrList 时）
  const inferFieldType = (filter: FilterItem): string => {
    // 如果有 attrList，优先使用
    const fieldInfo = getFieldInfo(filter.field);
    if (fieldInfo?.attr_type) {
      // 如果 type 是 user[]，直接返回 user[]
      if (filter.type === 'user[]') {
        return 'user[]';
      }
      return fieldInfo.attr_type;
    }

    if (filter.type === 'user[]') {
      return 'user[]';
    }
    if (filter.type.includes('int') || filter.type === 'int=') {
      return 'int';
    }
    if (filter.type.includes('time') || filter.start || filter.end) {
      return 'time';
    }
    if (filter.type.includes('bool') || typeof filter.value === 'boolean') {
      return 'bool';
    }
    return 'str';
  };

  // 格式化筛选条件的显示文本（用于标签显示）
  const formatFilterLabel = (filter: FilterItem): string => {
    const fieldInfo = getFieldInfo(filter.field);
    const fieldName = fieldInfo?.attr_name || filter.field;

    const getOperatorText = (type: string): string => {
      if (type.includes('*')) return t('FilterBar.fuzzy');
      if (type.includes('=')) return t('FilterBar.exact');
      return '';
    };

    const operator = getOperatorText(filter.type);
    return operator ? `${fieldName} ${operator}` : fieldName;
  };

  // 格式化筛选条件的显示文本（用于 Popover 中）
  const formatFilterLabelForPopover = (filter: FilterItem): string => {
    const fieldInfo = getFieldInfo(filter.field);
    return fieldInfo?.attr_name || filter.field;
  };

  // 格式化筛选条件的值显示
  const formatFilterValue = (filter: FilterItem): string => {
    if (filter.start && filter.end) {
      return `${filter.start} ~ ${filter.end}`;
    }
    if (Array.isArray(filter.value)) {
      if (filter.type === 'user[]') {
        const userNames = filter.value
          .map((userId) => {
            const user = userList.find((u) => String(u.id) === String(userId));
            return user?.display_name || user?.username || String(userId);
          })
          .filter(Boolean);
        return userNames.join(', ');
      }
      return filter.value.join(', ');
    }
    if (typeof filter.value === 'boolean') {
      return filter.value ? t('yes') : t('no');
    }
    return String(filter.value || '');
  };

  // 处理删除单个标签
  const handleClose = (index: number, e?: React.MouseEvent) => {
    if (e) {
      e.preventDefault();
      e.stopPropagation();
    }

    const newFilters = remove(index);
    onChange?.(newFilters);
    onFilterChange?.(newFilters);
  };

  const handleClear = () => {
    const newFilters = clear();
    onChange?.(newFilters);
    onFilterChange?.(newFilters);
  };

  const handleTagClick = (filter: FilterItem, index: number) => {
    // 同步切换搜索框的选项
    // console.log("test4:filter", filter);

    setEditingFilter({ ...filter });
    setEditingIndex(index);
    setClickedTagIndex(index);
    setEditPopoverVisible(true);

    // 根据类型设置表单初始值
    const fieldType = inferFieldType(filter);
    if (fieldType === 'time' && filter.start && filter.end) {
      // 解析时间字符串，使用严格模式确保格式正确
      const startDate = dayjs(filter.start, 'YYYY-MM-DD HH:mm', true);
      const endDate = dayjs(filter.end, 'YYYY-MM-DD HH:mm', true);

      // 验证解析是否成功
      if (startDate.isValid() && endDate.isValid()) {
        form.setFieldsValue({
          value: [startDate, endDate],
        });
      } else {
        form.setFieldsValue({
          value: [dayjs(filter.start), dayjs(filter.end)],
        });
      }
    } else if (filter.type === 'user[]') {
      form.setFieldsValue({
        value: Array.isArray(filter.value) ? filter.value[0] : filter.value,
      });
    } else if (fieldType === 'int') {
      form.setFieldsValue({
        value: typeof filter.value === 'number' ? filter.value : Number(filter.value) || 0,
      });
    } else if (fieldType === 'bool') {
      let boolValue = false;
      if (typeof filter.value === 'boolean') {
        boolValue = filter.value;
      } else if (typeof filter.value === 'string') {
        boolValue = filter.value === 'true';
      } else if (typeof filter.value === 'number') {
        boolValue = filter.value !== 0;
      }
      form.setFieldsValue({
        value: boolValue,
      });
    } else {
      form.setFieldsValue({
        value: filter.value,
        isExact: filter.type.includes('=') && !filter.type.includes('*'),
      });
    }
  };

  const handleEditConfirm = async () => {
    try {
      const values = await form.validateFields();
      const fieldType = inferFieldType(editingFilter!);

      const updatedFilter: FilterItem = {
        ...editingFilter!,
        value: values.value,
      };

      if (fieldType === 'time') {
        if (Array.isArray(values.value) && values.value.length === 2) {
          // 统一转换为 dayjs 对象进行处理
          const startValue = values.value[0];
          const endValue = values.value[1];

          // 转换为 dayjs 对象（dayjs 可以处理多种输入类型）
          const startDate = startValue ? dayjs(startValue) : null;
          const endDate = endValue ? dayjs(endValue) : null;

          // 确保 dayjs 对象存在且有效
          if (startDate && endDate && startDate.isValid() && endDate.isValid()) {
            updatedFilter.start = startDate.format('YYYY-MM-DD HH:mm');
            updatedFilter.end = endDate.format('YYYY-MM-DD HH:mm');
            delete updatedFilter.value;
            updatedFilter.type = 'time';
          } else {
            throw new Error(t('FilterBar.pleaseSelectValidTimeRange'));
          }
        }
      } else if (editingFilter?.type === 'user[]') {
        updatedFilter.value = Array.isArray(values.value) ? values.value : [values.value];
        updatedFilter.type = 'user[]';
      } else if (fieldType === 'int') {
        updatedFilter.value = Number(values.value) || 0;
        updatedFilter.type = 'int=';
      } else if (fieldType === 'bool') {
        updatedFilter.value = Boolean(values.value);
        updatedFilter.type = 'bool=';
      } else if (fieldType === 'str') {
        updatedFilter.value = String(values.value || '');
        updatedFilter.type = values.isExact ? 'str=' : 'str*';
      }

      const newFilters = update(editingIndex, updatedFilter);
      onChange?.(newFilters);
      onFilterChange?.(newFilters);
      setEditPopoverVisible(false);
      form.resetFields();
    } catch (error) {
      console.error('Validation failed:', error);
    }
  };

  const handleCancel = () => {
    form.resetFields();
    setEditPopoverVisible(false);
  };

  const handlePopoverOpenChange = (visible: boolean) => {
    if (!visible && editPopoverVisible) {
      return;
    }
  };

  const renderEditInput = () => {
    if (!editingFilter) return null;
    const fieldType = inferFieldType(editingFilter);
    const fieldInfo = getFieldInfo(editingFilter.field);

    // 特殊处理-云区域
    if (fieldInfo?.attr_id === 'cloud' && proxyOptions.length) {
      return (
        <Form.Item name="value" rules={[{ required: true, message: t('FilterBar.pleaseSelectValue') }]}>
          <Select placeholder={t('FilterBar.pleaseSelect')} allowClear showSearch style={{ width: '100%' }}>
            {proxyOptions.map((opt) => (
              <Select.Option key={opt.proxy_id} value={opt.proxy_id}>
                {opt.proxy_name}
              </Select.Option>
            ))}
          </Select>
        </Form.Item>
      );
    }

    // 根据字段类型渲染不同的输入组件：字符串、数字、布尔值、日期
    switch (fieldType) {
      case 'user[]':
        return (
          <Form.Item name="value" rules={[{ required: true, message: t('FilterBar.pleaseSelectUser') }]}>
            <Select
              placeholder={t('FilterBar.pleaseSelectUser')}
              allowClear
              showSearch
              style={{ width: '100%' }}
              filterOption={(input, opt: any) => {
                if (typeof opt?.children?.props?.text === 'string') {
                  return opt?.children?.props?.text
                    ?.toLowerCase()
                    .includes(input.toLowerCase());
                }
                return true;
              }}
            >
              {userList.map((user) => (
                <Select.Option key={user.id} value={user.id}>
                  {user.display_name || user.username}
                </Select.Option>
              ))}
            </Select>
          </Form.Item>
        );
      case 'user':
        return (
          <Form.Item name="value" rules={[{ required: true, message: t('FilterBar.pleaseSelectUser') }]}>
            <Select placeholder={t('FilterBar.pleaseSelectUser')} allowClear showSearch style={{ width: '100%' }}>
              {userList.map((user) => (
                <Select.Option key={user.id} value={user.id}>
                  {user.display_name || user.username}
                </Select.Option>
              ))}
            </Select>
          </Form.Item>
        );
      case 'enum':
        return (
          <Form.Item name="value" rules={[{ required: true, message: t('FilterBar.pleaseSelectValue') }]}>
            <Select placeholder={t('FilterBar.pleaseSelect')} allowClear showSearch style={{ width: '100%' }}>
              {fieldInfo?.option?.map((opt) => (
                <Select.Option key={opt.id} value={opt.id}>
                  {opt.name}
                </Select.Option>
              ))}
            </Select>
          </Form.Item>
        );
      case 'bool':
        return (
          <Form.Item name="value" rules={[{ required: true, message: t('FilterBar.pleaseSelectValue') }]}>
            <Select placeholder={t('FilterBar.pleaseSelect')} allowClear style={{ width: '100%' }}>
              <Select.Option value={true}>{t('yes')}</Select.Option>
              <Select.Option value={false}>{t('no')}</Select.Option>
            </Select>
          </Form.Item>
        );
      case 'time':
        return (
          <Form.Item name="value" rules={[{ required: true, message: t('FilterBar.pleaseSelectTimeRange') }]}>
            <RangePicker
              showTime={{ format: 'HH:mm' }}
              format="YYYY-MM-DD HH:mm"
              style={{ width: '100%' }}
            />
          </Form.Item>
        );
      case 'int':
        return (
          <Form.Item name="value" rules={[{ required: true, message: t('FilterBar.pleaseEnterNumber') }]}>
            <InputNumber style={{ width: '100%' }} placeholder={t('FilterBar.pleaseEnterNumber')} />
          </Form.Item>
        );
      case 'str':
      default:
        return (
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, width: '100%' }}>
            <Form.Item
              name="value"
              rules={[{ required: true, message: t('FilterBar.pleaseEnterValue') }]}
              style={{ marginBottom: 0, flex: 1 }}
            >
              <Input placeholder={t('FilterBar.pleaseEnterValue')} allowClear className={styles.filterInput} />
            </Form.Item>
            <Form.Item
              name="isExact"
              valuePropName="checked"
              style={{ marginBottom: 0 }}
              className={styles.exactMatchCheckbox}
            >
              <Checkbox>{t('FilterBar.exactMatch')}</Checkbox>
            </Form.Item>
          </div>
        );
    }
  };

  // 如果没有筛选条件，返回空状态
  if (queryList.length === 0) return null;

  return (
    <>
      <div className={styles.filterBar}>
        {/* 左侧：标题区域 */}
        <div className={styles.header}>
          <FunnelPlotFilled className={styles.headerIcon} />
          <span className={styles.headerLabel}>{t('FilterBar.filterItems')}</span>
        </div>
        {/* 中间：标签列表区域 */}
        <div className={styles.tagsContainer}>
          {queryList.map((filter, index) => (
            <Popover
              key={`${filter.field}-${index}`}
              open={editPopoverVisible && clickedTagIndex === index}
              onOpenChange={handlePopoverOpenChange}
              trigger="click"
              placement="bottomLeft"
              destroyTooltipOnHide={false}
              content={
                <div className={styles.popoverContent}>
                  <Form form={form} layout="horizontal">
                    <Form.Item label={formatFilterLabelForPopover(filter)}>
                      {renderEditInput()}
                    </Form.Item>
                    <Form.Item style={{ marginBottom: 0, textAlign: 'right' }}>
                      <Space>
                        <span className={styles.actionLinkPrimary} onClick={handleEditConfirm}>
                          {t('common.confirm')}
                        </span>
                        <span className={styles.actionLink} onClick={handleCancel}>
                          {t('common.cancel')}
                        </span>
                      </Space>
                    </Form.Item>
                  </Form>
                </div>
              }
            >
              <Tag
                closable
                onClose={(e) => handleClose(index, e)}
                onClick={() => handleTagClick(filter, index)}
                className={styles.tag}
                closeIcon={<CloseOutlined className={styles.tagCloseIcon} />}
              >
                <span className={styles.tagLabel}>{formatFilterLabel(filter)} : </span>
                <span className={styles.tagValue} title={formatFilterValue(filter)}>
                  {formatFilterValue(filter)}
                </span>
              </Tag>
            </Popover>
          ))}
        </div>
        {/* 右侧：操作区域 */}
        <Button type="link" onClick={handleClear} className={styles.clearButton}>
          {t('FilterBar.clearConditions')}
        </Button>
      </div>
    </>
  );
};

export default FilterBar;
