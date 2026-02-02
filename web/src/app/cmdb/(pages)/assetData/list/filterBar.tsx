"use client";

import React, { useState } from 'react';
import { Tag, Button, Popover, Form, Input, InputNumber, Select, DatePicker, Checkbox, Space, Modal, message } from 'antd';
import { FunnelPlotFilled, CloseOutlined, StarOutlined } from '@ant-design/icons';
import type { AttrFieldType } from '@/app/cmdb/types/assetManage';
import dayjs from 'dayjs';
import customParseFormat from 'dayjs/plugin/customParseFormat';
import styles from './filterBar.module.scss';
import { useTranslation } from '@/utils/i18n';
dayjs.extend(customParseFormat);
import { useAssetDataStore, type FilterItem } from '@/app/cmdb/store';
import { useSavedFiltersApi, type SavedFiltersConfigValue, type SavedFilterItem } from '@/app/cmdb/api/userConfig';

const { RangePicker } = DatePicker;

const SAVED_FILTERS_CONFIG_KEY = 'cmdb_saved_filters';

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
  modelId?: string;
  onChange?: (filters: FilterItem[]) => void;
  onFilterChange?: (filters: FilterItem[]) => void;
}

const FilterBar: React.FC<FilterBarProps> = ({
  attrList = [],
  userList = [],
  proxyOptions = [],
  modelId = '',
  onChange,
  onFilterChange,
}) => {
  const { t } = useTranslation();
  const queryList = useAssetDataStore((state) => state.query_list);
  const remove = useAssetDataStore((state) => state.remove);
  const clear = useAssetDataStore((state) => state.clear);
  const update = useAssetDataStore((state) => state.update);
  const userConfigs = useAssetDataStore((state) => state.user_configs);
  const updateUserConfig = useAssetDataStore((state) => state.updateUserConfig);

  const { saveFilters } = useSavedFiltersApi();

  const [editPopoverVisible, setEditPopoverVisible] = useState(false);
  const [editingFilter, setEditingFilter] = useState<FilterItem | null>(null);
  const [editingIndex, setEditingIndex] = useState<number>(-1);
  const [clickedTagIndex, setClickedTagIndex] = useState<number>(-1);
  const [form] = Form.useForm();

  const [saveModalVisible, setSaveModalVisible] = useState(false);
  const [saveFilterName, setSaveFilterName] = useState('');
  const [saving, setSaving] = useState(false);

  // 根据 field 获取字段信息
  const getFieldInfo = (field: string): AttrFieldType | undefined => {
    return attrList.find((attr) => attr.attr_id === field);
  };

  // 根据 type 和 value 推断字段类型（用于没有 attrList 时）
  const inferFieldType = (filter: FilterItem): string => {
    // 如果有 attrList，优先使用
    const fieldInfo = getFieldInfo(filter.field);
    if (fieldInfo?.attr_type) {
      // 如果 type 是 list 且字段类型是 user，返回 user
      if (filter.type === 'list[]' && fieldInfo.attr_type === 'user') {
        return 'user';
      }
      // 兼容旧代码：如果 type 是 user[]，直接返回 user[]
      if (filter.type === 'user[]') {
        return 'user[]';
      }
      return fieldInfo.attr_type;
    }

    // 兼容旧代码：如果 type 是 user[]，返回 user[]
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
      // 处理 user 类型（type 为 list 且字段类型是 user）
      const fieldInfo = getFieldInfo(filter.field);
      if ((filter.type === 'list[]' && fieldInfo?.attr_type === 'user') || filter.type === 'user[]') {
        const userNames = filter.value
          .map((userId) => {
            const user = userList.find((u) => String(u.id) === String(userId));
            // 筛选条件的user值显示，显示用户名和显示名
            return `${user?.display_name}(${user?.username})` || String(userId);
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
    } else if (fieldType === 'user' || filter.type === 'list[]' || filter.type === 'user[]') {
      // 处理 user 类型：支持 type 为 'list' 或 'user[]'（兼容旧代码）
      const fieldInfo = getFieldInfo(filter.field);
      if (fieldType === 'user' || fieldInfo?.attr_type === 'user' || filter.type === 'user[]') {
        form.setFieldsValue({
          value: Array.isArray(filter.value) ? filter.value : filter.value ? [filter.value] : [],
        });
      }
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
      } else if (fieldType === 'user') {
        // 如果为用户字段user，则类型为list
        updatedFilter.value = Array.isArray(values.value) ? values.value : [values.value];
        updatedFilter.type = 'list[]';
      } else if (editingFilter?.type === 'user[]') {
        // 兼容旧代码：如果原来是 user[]，保持 user[]
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

  const generateDefaultFilterName = (): string => {
    if (queryList.length === 1) {
      const filter = queryList[0];
      const value = filter.start && filter.end 
        ? `${filter.start}~${filter.end}`
        : Array.isArray(filter.value) 
          ? filter.value.join(',') 
          : String(filter.value || '');
      return `${value}`.substring(0, 50);
    }
    return '';
  };

  const handleOpenSaveModal = () => {
    if (queryList.length === 0) {
      message.warning(t('FilterBar.noFiltersToSave'));
      return;
    }
    setSaveFilterName(generateDefaultFilterName());
    setSaveModalVisible(true);
  };

  const handleSaveFilter = async () => {
    if (!saveFilterName.trim()) {
      message.warning(t('FilterBar.filterNameRequired'));
      return;
    }
    setSaving(true);
    try {
      const allSavedFilters = (userConfigs.cmdb_saved_filters || {}) as SavedFiltersConfigValue;
      const currentFilters = allSavedFilters[modelId] || [];
      const newItem: SavedFilterItem = {
        id: `${Date.now()}_${Math.random().toString(36).substring(2, 9)}`,
        name: saveFilterName.trim(),
        filters: queryList,
      };
      const updatedFilters = [...currentFilters, newItem];
      const updatedAllFilters: SavedFiltersConfigValue = { ...allSavedFilters, [modelId]: updatedFilters };
      const isNew = !userConfigs.cmdb_saved_filters;

      await saveFilters(SAVED_FILTERS_CONFIG_KEY, updatedAllFilters, isNew);
      updateUserConfig(SAVED_FILTERS_CONFIG_KEY, updatedAllFilters);

      message.success(t('FilterBar.saveSuccess'));
      setSaveModalVisible(false);
      setSaveFilterName('');
    } catch {
      message.error(t('FilterBar.saveFailed'));
    } finally {
      setSaving(false);
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
            {/* 筛选项中，用户字段为多选 */}
            <Select
              mode="multiple"
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
                  {/* 筛选项的修改弹窗，显示用户名和显示名 */}
                  {user.display_name}({user.username})
                </Select.Option>
              ))}
            </Select>
          </Form.Item>
        );
      case 'user':
        return (
          <Form.Item name="value" rules={[{ required: true, message: t('FilterBar.pleaseSelectUser') }]}>
            <Select mode="multiple" placeholder={t('FilterBar.pleaseSelectUser')} allowClear showSearch style={{ width: '100%' }}>
              {userList.map((user) => {
                // 筛选项的修改弹窗
                return (
                  <Select.Option key={user.id} value={user.id}>
                    {/* 筛选项的修改弹窗 */}
                    {user.display_name}({user.username})
                  </Select.Option>
                )
              })}
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

  const hasActiveFilters = queryList.length > 0;

  // 只显示当前激活的筛选条件，不显示收藏的筛选条件
  if (!hasActiveFilters) return null;

  return (
    <>
      <div className={styles.filterBarWrapper}>
        {hasActiveFilters && (
          <div className={styles.filterBar}>
            <div className={styles.header}>
              <FunnelPlotFilled className={styles.headerIcon} />
              <span className={styles.headerLabel}>{t('FilterBar.filterItems')}</span>
            </div>
            <div className={styles.tagsContainer}>
              {queryList.map((filter, index) => (
                <Popover
                  key={`${filter.field}-${index}`}
                  open={editPopoverVisible && clickedTagIndex === index}
                  onOpenChange={handlePopoverOpenChange}
                  trigger="click"
                  placement="bottomLeft"
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
            <Button type="link" onClick={handleClear} className={styles.clearButton}>
              {t('FilterBar.clearConditions')}
            </Button>
            <Button type="link" onClick={handleOpenSaveModal} className={styles.saveButton}>
              <StarOutlined />
              {t('FilterBar.saveFilters')}
            </Button>
          </div>
        )}
      </div>

      <Modal
        title={t('FilterBar.saveFilters')}
        open={saveModalVisible}
        onOk={handleSaveFilter}
        onCancel={() => setSaveModalVisible(false)}
        okText={t('common.confirm')}
        cancelText={t('common.cancel')}
        confirmLoading={saving}
        centered
        width={400}
      >
        <Form layout="vertical">
          <Form.Item label={t('FilterBar.filterName')} required>
            <Input
              value={saveFilterName}
              onChange={(e) => setSaveFilterName(e.target.value)}
              placeholder={t('FilterBar.filterName')}
              maxLength={50}
            />
          </Form.Item>
        </Form>
      </Modal>
    </>
  );
};

export default FilterBar;
