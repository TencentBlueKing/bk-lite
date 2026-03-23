import React, { useEffect, useMemo, useRef, useState } from 'react';
import dayjs, { type Dayjs } from 'dayjs';
import { Button, DatePicker, Input, InputNumber, Select } from 'antd';
import { DeleteOutlined, PlusOutlined } from '@ant-design/icons';
import GroupTreeSelector from '@/components/group-tree-select';
import { useTranslation } from '@/utils/i18n';
import { useInstanceApi } from '@/app/cmdb/api/instance';
import { useCommon } from '@/app/cmdb/context/common';
import useAssetDataStore, { type FilterItem } from '@/app/cmdb/store/useAssetDataStore';
import type {
  ConditionFilter,
  FilterType,
  InstancesFilter,
} from '@/app/cmdb/types/subscription';
import type { AttrFieldType, UserItem } from '@/app/cmdb/types/assetManage';
import {
  getFieldType,
  getEnumOptions,
  getTagOptions,
  getUserOptions,
} from '@/app/cmdb/utils/fieldUtils';
import styles from './instanceSelector.module.scss';

type ConditionOperator = 'contains' | 'equals' | 'includes' | 'range';

interface ConditionRow {
  id: string;
  field?: string;
  operator?: ConditionOperator;
  value?: unknown;
}

interface InstanceSelectorProps {
  filterType: FilterType;
  value: ConditionFilter | InstancesFilter;
  onChange: (value: ConditionFilter | InstancesFilter) => void;
  modelId: string;
  modelFields: AttrFieldType[];
}

const MAX_CONDITION_COUNT = 8;
const TIME_FORMAT = 'YYYY-MM-DD HH:mm';
const { RangePicker } = DatePicker;

const createRowId = () => `${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;

const hasValue = (value: unknown) => value !== undefined && value !== null && value !== '';

const hasArrayValue = (value: unknown): value is Array<string | number> => Array.isArray(value) && value.length > 0;

const getDefaultOperator = (field?: AttrFieldType): ConditionOperator => {
  switch (getFieldType(field)) {
    case 'str':
      return 'contains';
    case 'time':
      return 'range';
    case 'user':
    case 'organization':
    case 'tag':
      return 'includes';
    case 'enum':
      return (field as any)?.enum_select_mode === 'multiple' ? 'includes' : 'equals';
    default:
      return 'equals';
  }
};

const getOperatorOptions = (field: AttrFieldType | undefined, t: (key: string) => string) => {
  switch (getFieldType(field)) {
    case 'str':
      return [
        { label: t('subscription.operatorContains'), value: 'contains' },
        { label: t('subscription.operatorEquals'), value: 'equals' },
      ];
    case 'time':
      return [{ label: t('subscription.operatorTimeRange'), value: 'range' }];
    case 'user':
    case 'organization':
    case 'tag':
      return [{ label: t('subscription.operatorContains'), value: 'includes' }];
    case 'enum':
      return [{ label: (field as any)?.enum_select_mode === 'multiple' ? t('subscription.operatorContains') : t('subscription.operatorEquals'), value: getDefaultOperator(field) }];
    default:
      return [{ label: t('subscription.operatorEquals'), value: 'equals' }];
  }
};

const toConditionRow = (filter: FilterItem, modelFields: AttrFieldType[]): ConditionRow => {
  const field = modelFields.find((item) => item.attr_id === filter.field);

  if (filter.start && filter.end) {
    return {
      id: createRowId(),
      field: filter.field,
      operator: 'range',
      value: [dayjs(filter.start), dayjs(filter.end)],
    };
  }

  return {
    id: createRowId(),
    field: filter.field,
    operator: filter.type === 'str*' ? 'contains' : getDefaultOperator(field),
    value: filter.value,
  };
};

const toFilterItem = (row: ConditionRow, field?: AttrFieldType): FilterItem | null => {
  if (!row.field || !row.operator || !field) {
    return null;
  }

  switch (getFieldType(field)) {
    case 'str':
      if (!hasValue(row.value)) {
        return null;
      }
      return {
        field: row.field,
        type: row.operator === 'contains' ? 'str*' : 'str=',
        value: String(row.value),
      };
    case 'int':
      if (!hasValue(row.value)) {
        return null;
      }
      return {
        field: row.field,
        type: 'int=',
        value: Number(row.value),
      };
    case 'bool':
      if (typeof row.value !== 'boolean') {
        return null;
      }
      return {
        field: row.field,
        type: 'bool=',
        value: row.value,
      };
    case 'user':
    case 'organization':
      if (!hasArrayValue(row.value)) {
        return null;
      }
      return {
        field: row.field,
        type: 'list[]',
        value: row.value,
      };
    case 'tag':
    case 'enum': {
      const nextValue = Array.isArray(row.value) ? row.value : hasValue(row.value) ? [row.value] : [];
      if (!nextValue.length) {
        return null;
      }
      return {
        field: row.field,
        type: 'list_any[]',
        value: nextValue as Array<string | number>,
      };
    }
    case 'time': {
      const range = Array.isArray(row.value) ? row.value as [Dayjs | null, Dayjs | null] : [];
      if (!range[0] || !range[1]) {
        return null;
      }
      return {
        field: row.field,
        type: 'time',
        start: dayjs(range[0]).format(TIME_FORMAT),
        end: dayjs(range[1]).format(TIME_FORMAT),
      };
    }
    case 'cloud': {
      if (!hasValue(row.value)) {
        return null;
      }
      const rawValue = Array.isArray(row.value) ? row.value[0] : row.value;
      const isNumeric = typeof rawValue === 'number' || /^\d+$/.test(String(rawValue));
      return {
        field: row.field,
        type: isNumeric ? 'int=' : 'str=',
        value: isNumeric ? Number(rawValue) : String(rawValue),
      };
    }
    default:
      if (!hasValue(row.value)) {
        return null;
      }
      return {
        field: row.field,
        type: 'str=',
        value: String(row.value),
      };
  }
};

function ConditionValueInput({
  row,
  field,
  cloudOptions,
  userList,
  onChange,
  t,
}: {
  row: ConditionRow;
  field?: AttrFieldType;
  cloudOptions: Array<{ proxy_id: string; proxy_name: string }>;
  userList: UserItem[];
  onChange: (value: unknown) => void;
  t: (key: string) => string;
}) {
  const fieldType = getFieldType(field);
  const organizationValue = Array.isArray(row.value)
    ? row.value.map((item) => Number(item)).filter((item) => !Number.isNaN(item))
    : hasValue(row.value)
      ? [Number(row.value)].filter((item) => !Number.isNaN(item))
      : [];

  if (!field) {
    return <Input disabled placeholder={t('subscription.pleaseSelectField')} />;
  }

  switch (fieldType) {
    case 'cloud':
      return (
        <Select
          allowClear
          showSearch
          placeholder={t('subscription.pleaseSelectValue')}
          value={row.value as string | number | undefined}
          options={cloudOptions.map((item) => ({ label: item.proxy_name, value: item.proxy_id }))}
          onChange={(value) => onChange(value)}
        />
      );
    case 'user':
      return (
        <Select
          mode="multiple"
          allowClear
          showSearch
          maxTagCount={1}
          placeholder={t('subscription.pleaseSelectUser')}
          value={Array.isArray(row.value) ? row.value : []}
          options={getUserOptions(userList)}
          onChange={(value) => onChange(value)}
        />
      );
    case 'enum':
      return (
        <Select
          mode={(field as any)?.enum_select_mode === 'multiple' ? 'multiple' : undefined}
          allowClear
          showSearch
          maxTagCount={1}
          placeholder={t('subscription.pleaseSelectValue')}
          value={row.value as string | number | Array<string | number> | undefined}
          options={getEnumOptions(field)}
          onChange={(value) => onChange(value)}
        />
      );
    case 'tag':
      return (
        <Select
          mode="multiple"
          allowClear
          showSearch
          maxTagCount={1}
          placeholder={t('subscription.pleaseSelectTag')}
          value={Array.isArray(row.value) ? row.value : []}
          options={getTagOptions(field)}
          onChange={(value) => onChange(value)}
        />
      );
    case 'bool':
      return (
        <Select
          allowClear
          placeholder={t('subscription.pleaseSelectValue')}
          value={typeof row.value === 'boolean' ? row.value : undefined}
          options={[
            { label: t('yes'), value: true },
            { label: t('no'), value: false },
          ]}
          onChange={(value) => onChange(value)}
        />
      );
    case 'organization':
      return (
        <GroupTreeSelector
          value={organizationValue}
          style={{ width: '100%' }}
          onChange={(value) => onChange(Array.isArray(value) ? value : value ? [value] : [])}
        />
      );
    case 'time':
      return (
        <RangePicker
          showTime={{ format: 'HH:mm' }}
          format={TIME_FORMAT}
          style={{ width: '100%' }}
          value={Array.isArray(row.value) ? row.value as [Dayjs, Dayjs] : null}
          onChange={(value) => onChange(value || [])}
        />
      );
    case 'int':
      return (
        <InputNumber
          style={{ width: '100%' }}
          placeholder={t('subscription.pleaseEnterNumber')}
          value={typeof row.value === 'number' ? row.value : undefined}
          onChange={(value) => onChange(value)}
        />
      );
    default:
      return (
        <Input
          allowClear
          placeholder={t('subscription.pleaseEnterValue')}
          value={typeof row.value === 'string' ? row.value : ''}
          onChange={(event) => onChange(event.target.value)}
        />
      );
  }
}

const InstanceSelector: React.FC<InstanceSelectorProps> = ({
  filterType,
  value,
  onChange,
  modelId,
  modelFields,
}) => {
  const { t } = useTranslation();
  const { searchInstances } = useInstanceApi();
  const common = useCommon();
  const cloudOptions = useAssetDataStore((state) => state.cloud_list);
  const [instanceOptions, setInstanceOptions] = useState<{ label: string; value: number }[]>([]);
  const [loading, setLoading] = useState(false);
  const [conditionRows, setConditionRows] = useState<ConditionRow[]>([]);
  
  const searchInstancesRef = useRef(searchInstances);
  const onChangeRef = useRef(onChange);
  const lastSyncedRef = useRef('[]');
  const userEditedRef = useRef(false);

  const conditionValue = (value as ConditionFilter) || { query_list: [] };
  const queryList = conditionValue.query_list || [];
  const instancesValue = (value as InstancesFilter) || { instance_ids: [] };
  const serializedQueryList = useMemo(() => JSON.stringify(queryList), [queryList]);
  const userList = common?.userList || [];

  useEffect(() => { searchInstancesRef.current = searchInstances; }, [searchInstances]);
  useEffect(() => { onChangeRef.current = onChange; }, [onChange]);

  useEffect(() => {
    if (filterType !== 'condition') {
      if (conditionRows.length > 0) {
        setConditionRows([]);
      }
      lastSyncedRef.current = '[]';
      return;
    }

    if (serializedQueryList !== lastSyncedRef.current) {
      const limitedQueryList = queryList.slice(0, MAX_CONDITION_COUNT);
      setConditionRows(limitedQueryList.map((item) => toConditionRow(item, modelFields)));
      lastSyncedRef.current = serializedQueryList;
    }
  }, [filterType, modelFields, serializedQueryList, queryList, conditionRows.length]);

  useEffect(() => {
    if (filterType !== 'condition' || !userEditedRef.current) {
      return;
    }

    const nextQueryList = conditionRows
      .map((row) => toFilterItem(row, modelFields.find((field) => field.attr_id === row.field)))
      .filter(Boolean) as FilterItem[];
    const limitedQueryList = nextQueryList.slice(0, MAX_CONDITION_COUNT);
    const serialized = JSON.stringify(limitedQueryList);

    if (serialized !== lastSyncedRef.current) {
      onChangeRef.current({ query_list: limitedQueryList });
      lastSyncedRef.current = serialized;
    }
  }, [conditionRows, filterType, modelFields]);

  useEffect(() => {
    if (!modelId || filterType !== 'instances') {
      return;
    }

    setLoading(true);
    searchInstancesRef.current({
      query_list: [],
      page: 1,
      page_size: 200,
      order: '',
      model_id: modelId,
      role: '',
      case_sensitive: false,
    })
      .then((data: any) => {
        const insts = Array.isArray(data?.insts) ? data.insts : [];
        setInstanceOptions(
          insts
            .map((item: any) => ({
              value: Number(item?._id),
              label: item?.inst_name || item?.name || item?.ip_addr || String(item?._id || ''),
            }))
            .filter((item: { label: string; value: number }) => item.label && !Number.isNaN(item.value)),
        );
      })
      .catch(() => {
        setInstanceOptions([]);
      })
      .finally(() => {
        setLoading(false);
      });
  }, [filterType, modelId]);

  const mergedInstanceOptions = useMemo(() => {
    const selectedFallbackOptions = (instancesValue.instance_ids || [])
      .filter((id) => !instanceOptions.some((item) => item.value === id))
      .map((id) => ({ label: String(id), value: id }));

    return [...instanceOptions, ...selectedFallbackOptions];
  }, [instanceOptions, instancesValue.instance_ids]);

  const addConditionRow = () => {
    userEditedRef.current = true;
    setConditionRows((prev) => {
      if (prev.length >= MAX_CONDITION_COUNT) {
        return prev;
      }
      return [...prev, { id: createRowId() }];
    });
  };

  const updateConditionRow = (rowId: string, nextValue: Partial<ConditionRow>) => {
    userEditedRef.current = true;
    setConditionRows((prev) => prev.map((row) => (row.id === rowId ? { ...row, ...nextValue } : row)));
  };

  const removeConditionRow = (rowId: string) => {
    userEditedRef.current = true;
    setConditionRows((prev) => prev.filter((row) => row.id !== rowId));
  };

  if (filterType === 'condition') {
    return (
      <div className={styles.conditionBuilder}>
        <div className={styles.toolbar}>
          <Button
            type="default"
            size="small"
            icon={<PlusOutlined />}
            onClick={addConditionRow}
            disabled={conditionRows.length >= MAX_CONDITION_COUNT}
          >
            {t('subscription.addCondition')}
          </Button>
          <span className={styles.maxConditionHint}>
            {conditionRows.length}/{MAX_CONDITION_COUNT}
          </span>
        </div>

        {conditionRows.length > 0 ? (
          <div className={styles.conditionListWrapper}>
            <div className={styles.headerRow}>
              <div className={styles.logicColumn} />
              <div className={styles.fieldColumn}>{t('subscription.field')}</div>
              <div className={styles.operatorColumn}>{t('subscription.operator')}</div>
              <div className={styles.valueColumn}>{t('subscription.value')}</div>
              <div className={styles.actionColumn} />
            </div>

            <div className={styles.rows}>
              {conditionRows.map((row, index) => {
                const selectedField = modelFields.find((item) => item.attr_id === row.field);
                const operatorOptions = getOperatorOptions(selectedField, t);

                return (
                  <div key={row.id} className={styles.conditionRow}>
                    <div className={styles.logicColumn}>
                      {index > 0 ? <span className={styles.logicTag}>AND</span> : null}
                    </div>

                    <div className={styles.fieldColumn}>
                      <Select
                        allowClear
                        showSearch
                        optionFilterProp="label"
                        placeholder={t('common.selectMsg')}
                        value={row.field}
                        options={modelFields.map((item) => ({ label: item.attr_name, value: item.attr_id }))}
                        style={{ width: '100%' }}
                        onChange={(fieldId) => {
                          const nextField = modelFields.find((item) => item.attr_id === fieldId);
                          updateConditionRow(row.id, {
                            field: fieldId,
                            operator: getDefaultOperator(nextField),
                            value: undefined,
                          });
                        }}
                      />
                    </div>

                    <div className={styles.operatorColumn}>
                      <Select
                        placeholder={t('common.selectMsg')}
                        value={row.operator}
                        options={operatorOptions}
                        style={{ width: '100%' }}
                        onChange={(operator) => updateConditionRow(row.id, { operator, value: undefined })}
                      />
                    </div>

                    <div className={styles.valueColumn}>
                      <ConditionValueInput
                        row={row}
                        field={selectedField}
                        cloudOptions={cloudOptions}
                        userList={userList}
                        onChange={(nextValue) => updateConditionRow(row.id, { value: nextValue })}
                        t={t}
                      />
                    </div>

                    <div className={styles.actionColumn}>
                      <Button
                        type="text"
                        icon={<DeleteOutlined />}
                        onClick={() => removeConditionRow(row.id)}
                      />
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        ) : (
          <div className={styles.emptyState}>{t('subscription.addConditionHint')}</div>
        )}
      </div>
    );
  }

  return (
    <Select
      mode="multiple"
      style={{ width: '100%' }}
      maxTagCount="responsive"
      maxTagTextLength={12}
      placeholder={t('subscription.selectInstances')}
      options={mergedInstanceOptions}
      loading={loading}
      showSearch
      optionFilterProp="label"
      value={instancesValue.instance_ids || []}
      onChange={(vals) =>
        onChange({
          instance_ids: vals.map((item) => Number(item)).filter((item) => !Number.isNaN(item)),
        })
      }
    />
  );
};

export default InstanceSelector;
