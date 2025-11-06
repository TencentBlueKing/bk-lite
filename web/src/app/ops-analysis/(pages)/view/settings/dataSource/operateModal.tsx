'use client';

import React, { useEffect } from 'react';
import dayjs, { Dayjs } from 'dayjs';
import CustomTable from '@/components/custom-table';
import TimeSelector from '@/components/time-selector';
import GroupTreeSelect from '@/components/group-tree-select';
import { v4 as uuidv4 } from 'uuid';
import { getChartTypeList } from '@/app/ops-analysis/constants/common';
import { PlusCircleOutlined, MinusCircleOutlined } from '@ant-design/icons';
import { useDataSourceApi } from '@/app/ops-analysis/api/dataSource';
import { useNamespaceApi } from '@/app/ops-analysis/api/namespace';
import { useOpsAnalysis } from '@/app/ops-analysis/context/common';
import { useUserInfoContext } from '@/context/userInfo';
import { useTranslation } from '@/utils/i18n';
import {
  OperateModalProps,
  ParamItem,
} from '@/app/ops-analysis/types/dataSource';
import { NamespaceItem, TagItem } from '@/app/ops-analysis/types/namespace';
import {
  Drawer,
  Form,
  Input,
  Select,
  Button,
  DatePicker,
  Switch,
  Checkbox,
  Spin,
  message,
  Empty,
} from 'antd';

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

const OperateModal: React.FC<OperateModalProps> = ({
  open,
  currentRow,
  onClose,
  onSuccess,
}) => {
  const { t } = useTranslation();
  const [form] = Form.useForm();
  const { selectedGroup } = useUserInfoContext();
  const [params, setParams] = React.useState<ParamItem[]>([]);
  const [loading, setLoading] = React.useState(false);
  const [duplicateNames, setDuplicateNames] = React.useState<string[]>([]);
  const [emptyNames, setEmptyNames] = React.useState<string[]>([]);
  const [emptyAliases, setEmptyAliases] = React.useState<string[]>([]);
  const [namespaceList, setNamespaceList] = React.useState<NamespaceItem[]>([]);
  const [namespaceLoading, setNamespaceLoading] = React.useState(false);
  const { tagList, tagsLoading, fetchTags } = useOpsAnalysis();
  const { createDataSource, updateDataSource } = useDataSourceApi();
  const { getNamespaceList } = useNamespaceApi();

  const paramTypeOptions = [
    { label: t('dataSource.paramTypes.string'), value: 'string' },
    { label: t('dataSource.paramTypes.number'), value: 'number' },
    { label: t('dataSource.paramTypes.boolean'), value: 'boolean' },
    { label: t('dataSource.paramTypes.date'), value: 'date' },
    { label: t('dataSource.paramTypes.timeRange'), value: 'timeRange' },
  ];

  const filterTypeOptions = [
    { label: t('dataSource.filterTypes.filter'), value: 'filter' },
    { label: t('dataSource.filterTypes.fixed'), value: 'fixed' },
    { label: t('dataSource.filterTypes.params'), value: 'params' },
  ];

  const createDefaultParam = (): ParamItem => ({
    id: uuidv4(),
    name: '',
    value: '',
    type: 'string',
    filterType: 'fixed',
    alias_name: '',
  });

  const fetchNamespaces = async () => {
    try {
      setNamespaceLoading(true);
      const { items } = await getNamespaceList({ page: 1, page_size: 10000 });
      if (items && Array.isArray(items)) {
        setNamespaceList(items);
        if (!currentRow && items.length > 0) {
          form.setFieldsValue({ namespaces: [items[0].id] });
        }
      }
    } finally {
      setNamespaceLoading(false);
    }
  };

  useEffect(() => {
    if (!open) return;

    form.resetFields();
    setDuplicateNames([]);
    setEmptyNames([]);
    setEmptyAliases([]);
    fetchNamespaces();
    fetchTags();

    if (!currentRow) {
      setParams([]);
      // 新增时，如果用户有选中的分组，则设置为默认值
      if (selectedGroup) {
        form.setFieldValue('groups', [selectedGroup.id]);
      }
      return;
    }

    const formValues = {
      ...currentRow,
      namespaces: currentRow.namespaces || [],
      groups: currentRow.groups || [],
    };
    form.setFieldsValue(formValues);

    const hasValidParams =
      currentRow.params &&
      Array.isArray(currentRow.params) &&
      currentRow.params.length > 0;

    if (hasValidParams) {
      setParams(
        currentRow.params.map((param: any) => ({
          ...param,
          type: param.type || 'string',
          filterType:
            param.filterType ||
            (param.type === 'timeRange' ? 'filter' : 'fixed'),
          id: param.id || uuidv4(),
        }))
      );
    } else {
      setParams([]);
    }
  }, [open, currentRow, form, selectedGroup]);

  const checkDuplicateNames = (currentParams: ParamItem[]) => {
    const nameCount: { [key: string]: number } = {};
    const duplicates: string[] = [];

    currentParams.forEach((param) => {
      if (param.name && param.name.trim()) {
        nameCount[param.name] = (nameCount[param.name] || 0) + 1;
      }
    });

    Object.keys(nameCount).forEach((name) => {
      if (nameCount[name] > 1) {
        duplicates.push(name);
      }
    });

    setDuplicateNames(duplicates);
    return duplicates.length === 0;
  };

  const checkEmptyValues = (currentParams: ParamItem[]) => {
    const emptyNameList: string[] = [];
    const emptyAliasList: string[] = [];

    currentParams.forEach((param) => {
      if (!param.name || !param.name.trim()) {
        emptyNameList.push(param.id!);
      }
      if (!param.alias_name || !param.alias_name.trim()) {
        emptyAliasList.push(param.id!);
      }
    });

    setEmptyNames(emptyNameList);
    setEmptyAliases(emptyAliasList);

    return emptyNameList.length === 0 && emptyAliasList.length === 0;
  };

  const handleAliasChange = (val: string, id: string) => {
    setParams((prev: ParamItem[]) =>
      prev.map((item) => (item.id === id ? { ...item, alias_name: val } : item))
    );
  };

  const handleAliasBlur = (val: string, id: string) => {
    const newParams = params.map((item) => {
      if (item.id === id) {
        return { ...item, alias_name: val.trim() };
      }
      return item;
    });
    setParams(newParams);
    checkEmptyValues(newParams);
  };

  const handleDefaultChange = (val: any, id: string, type: string) => {
    setParams((prev: ParamItem[]) =>
      prev.map((item) => {
        if (item.id !== id) return item;
        let newValue = val;
        if (type === 'boolean') {
          newValue = val;
        } else if (type === 'number') {
          newValue = Number(val);
        } else if (type === 'date') {
          if (!val) {
            newValue = '';
          } else if (val.format) {
            newValue = val.format('YYYY-MM-DD HH:mm:ss');
          } else {
            newValue = val;
          }
        } else if (type === 'timeRange') {
          newValue = val;
        }
        return { ...item, value: newValue };
      })
    );
  };

  const handleTypeChange = (val: string, id: string) => {
    setParams((prev: ParamItem[]) =>
      prev.map((item) => {
        if (item.id !== id) return item;
        let newValue: any = '';
        let newFilterType = item.filterType;

        if (val === 'boolean') {
          newValue = false;
        } else if (val === 'number') {
          newValue = 0;
        } else if (val === 'date') {
          newValue = '';
        } else if (val === 'timeRange') {
          newValue = 10080;
        } else {
          newValue = '';
        }

        if (val !== 'timeRange' && newFilterType === 'filter') {
          newFilterType = 'fixed';
        }

        return {
          ...item,
          type: val,
          value: newValue,
          filterType: newFilterType,
        };
      })
    );
  };

  const handleFilterTypeChange = (val: string, id: string) => {
    setParams((prev: ParamItem[]) =>
      prev.map((item) => {
        if (item.id !== id) return item;
        return { ...item, filterType: val };
      })
    );
  };

  const handleAddParamAfter = (index: number) => {
    const newParam = createDefaultParam();
    const newParams = [...params];
    newParams.splice(index + 1, 0, newParam);
    setParams(newParams);
  };

  const handleDeleteParam = (id: string) => {
    const newParams = params.filter((item) => item.id !== id);
    setParams(newParams);
    checkDuplicateNames(newParams);
    checkEmptyValues(newParams);
  };

  const handleParamNameChange = (val: string, id: string) => {
    const newParams = params.map((item) => {
      if (item.id === id) {
        return {
          ...item,
          name: val,
        };
      }
      return item;
    });
    setParams(newParams);
  };

  const handleParamNameBlur = (val: string, id: string) => {
    const newParams = params.map((item) => {
      if (item.id === id) {
        return { ...item, name: val.trim() };
      }
      return item;
    });
    setParams(newParams);
    checkDuplicateNames(newParams);
    checkEmptyValues(newParams);
  };

  const columns = [
    {
      title: t('dataSource.name'),
      dataIndex: 'name',
      key: 'name',
      width: 120,
      render: (_: any, record: ParamItem) => (
        <Input
          value={record.name}
          placeholder={t('dataSource.name')}
          onChange={(e) => handleParamNameChange(e.target.value, record.id!)}
          onBlur={(e) => handleParamNameBlur(e.target.value, record.id!)}
          status={
            duplicateNames.includes(record.name) ||
            emptyNames.includes(record.id!)
              ? 'error'
              : undefined
          }
        />
      ),
    },
    {
      title: t('dataSource.aliasName'),
      dataIndex: 'alias_name',
      key: 'alias_name',
      width: 120,
      render: (_: any, record: ParamItem) => (
        <Input
          value={record.alias_name || ''}
          placeholder={t('dataSource.aliasName')}
          onChange={(e) => handleAliasChange(e.target.value, record.id!)}
          onBlur={(e) => handleAliasBlur(e.target.value, record.id!)}
          status={emptyAliases.includes(record.id!) ? 'error' : undefined}
        />
      ),
    },
    {
      title: t('dataSource.paramType'),
      dataIndex: 'type',
      key: 'type',
      width: 110,
      render: (_: any, record: ParamItem) => (
        <Select
          value={record.type || 'string'}
          options={paramTypeOptions}
          style={{ width: '100%' }}
          onChange={(val) => handleTypeChange(val, record.id!)}
        />
      ),
    },
    {
      title: t('dataSource.filterType'),
      dataIndex: 'filterType',
      key: 'filterType',
      width: 100,
      render: (_: any, record: ParamItem) => {
        const getFilterTypeOptions = (paramType: string) => {
          if (paramType === 'timeRange') {
            return filterTypeOptions;
          } else {
            return filterTypeOptions.filter(
              (option) => option.value === 'fixed' || option.value === 'params'
            );
          }
        };

        return (
          <Select
            value={record.filterType || 'fixed'}
            options={getFilterTypeOptions(record.type || 'string')}
            style={{ width: '100%' }}
            onChange={(val) => handleFilterTypeChange(val, record.id!)}
          />
        );
      },
    },
    {
      title: t('dataSource.defaultValue'),
      dataIndex: 'value',
      key: 'value',
      width: 200,
      render: (text: any, record: ParamItem) => {
        const type = record.type || 'string';
        const isFixed = record.name && record.filterType === 'fixed';
        const commonProps = {
          style: {
            width: '100%',
            ...(isFixed && !text && text !== 0 && text !== false
              ? { borderColor: 'var(--color-fail)' }
              : {}),
          },
        };

        if (type === 'date') {
          return (
            <DatePicker
              showTime
              value={text ? dayjs(text) : undefined}
              onChange={(date: Dayjs | null) =>
                handleDefaultChange(date, record.id!, 'date')
              }
              style={{ width: '100%' }}
              format="YYYY-MM-DD HH:mm:ss"
            />
          );
        }
        if (type === 'timeRange') {
          return (
            <FormTimeSelector
              value={text}
              onChange={(val: any) =>
                handleDefaultChange(val, record.id!, 'timeRange')
              }
            />
          );
        }
        if (type === 'boolean') {
          return (
            <Switch
              checked={!!text}
              onChange={(val: boolean) =>
                handleDefaultChange(val, record.id!, 'boolean')
              }
            />
          );
        }
        if (type === 'number') {
          return (
            <Input
              type="number"
              value={text}
              placeholder={
                isFixed
                  ? t('dataSource.required')
                  : t('dataSource.defaultValue')
              }
              onChange={(e: React.ChangeEvent<HTMLInputElement>) =>
                handleDefaultChange(e.target.value, record.id!, 'number')
              }
              {...commonProps}
            />
          );
        }
        return (
          <Input
            value={text}
            placeholder={
              isFixed ? t('dataSource.required') : t('dataSource.defaultValue')
            }
            onChange={(e: React.ChangeEvent<HTMLInputElement>) =>
              handleDefaultChange(e.target.value, record.id!, 'string')
            }
            {...commonProps}
          />
        );
      },
    },
    {
      title: t('dataSource.operation'),
      key: 'action',
      width: 80,
      render: (_: any, record: ParamItem, index: number) => (
        <div style={{ display: 'flex', gap: '4px', justifyContent: 'center' }}>
          <Button
            type="text"
            size="small"
            icon={<PlusCircleOutlined />}
            onClick={() => handleAddParamAfter(index)}
            style={{
              border: 'none',
              padding: '4px',
            }}
          />
          <Button
            type="text"
            size="small"
            icon={<MinusCircleOutlined />}
            onClick={() => handleDeleteParam(record.id!)}
            style={{
              border: 'none',
              padding: '4px',
            }}
          />
        </div>
      ),
    },
  ];

  const onFinish = async (values: any) => {
    try {
      setLoading(true);

      const validParams = params.filter(
        (param) => param.name && param.name.trim()
      );

      // 检查参数名称和别名是否为空
      if (!checkEmptyValues(params)) {
        setLoading(false);
        return;
      }
      if (!checkDuplicateNames(validParams)) {
        setLoading(false);
        return;
      }

      // 检查fixed类型的参数是否有默认值
      const hasEmptyFixedValue = validParams.some((param) => {
        if (param.filterType === 'fixed') {
          const value = param.value;
          return value === '' || value === null || value === undefined;
        }
        return false;
      });
      if (hasEmptyFixedValue) {
        setLoading(false);
        return;
      }

      const submitData = {
        rest_api: values.rest_api,
        name: values.name.trim(),
        desc: values.desc ? values.desc.trim() : '',
        namespaces: values.namespaces || [],
        tag: values.tag || [],
        chart_type: values.chart_type || [],
        groups: values.groups || [],
        params: params
          .filter((param) => param.name && param.name.trim())
          .map((param) => ({
            name: param.name,
            alias_name: param.alias_name,
            type: param.type,
            filterType: param.filterType,
            value: param.value,
          })),
      };

      if (currentRow) {
        await updateDataSource(currentRow.id, submitData);
        message.success(t('dataSource.updateDataSourceSuccess'));
      } else {
        await createDataSource(submitData);
        message.success(t('dataSource.createDataSourceSuccess'));
      }

      onClose();
      onSuccess && onSuccess();
    } catch (error: any) {
      message.error(error.message || t('dataSource.operationFailed'));
    } finally {
      setLoading(false);
    }
  };

  return (
    <Drawer
      title={
        currentRow
          ? `${t('common.edit')}${t('dataSource.title')} - ${currentRow.name}`
          : `${t('common.add')}${t('dataSource.title')}`
      }
      placement="right"
      width={900}
      open={open}
      onClose={onClose}
      footer={
        <div style={{ textAlign: 'right' }}>
          <Button
            type="primary"
            loading={loading}
            onClick={() => form.submit()}
          >
            {t('common.confirm')}
          </Button>
          <Button style={{ marginLeft: 8 }} onClick={onClose}>
            {t('common.cancel')}
          </Button>
        </div>
      }
    >
      <Form
        form={form}
        layout="horizontal"
        labelCol={{ span: 3 }}
        onFinish={onFinish}
      >
        <Form.Item
          name="rest_api"
          label="NATS"
          rules={[{ required: true, message: t('common.inputMsg') }]}
        >
          <Input placeholder={t('common.inputMsg')} />
        </Form.Item>
        <Form.Item
          name="name"
          label={t('dataSource.name')}
          rules={[{ required: true, message: t('common.inputMsg') }]}
        >
          <Input placeholder={t('common.inputMsg')} />
        </Form.Item>
        <Form.Item
          name="namespaces"
          label={t('namespace.title')}
          rules={[
            {
              required: true,
              type: 'array',
              min: 1,
              message: t('common.selectMsg'),
            },
          ]}
        >
          <Checkbox.Group
            options={namespaceList.map((ns: NamespaceItem) => ({
              label: ns.name,
              value: ns.id,
            }))}
            disabled={namespaceLoading}
          />
          {namespaceLoading && (
            <div style={{ textAlign: 'center', padding: '8px 0' }}>
              <Spin size="small" />
            </div>
          )}
        </Form.Item>
        <Form.Item
          name="tag"
          label={t('dataSource.tag')}
          rules={[
            {
              required: true,
              type: 'array',
              min: 1,
              message: t('common.selectMsg'),
            },
          ]}
        >
          <Checkbox.Group
            options={tagList.map((tag: TagItem) => ({
              label: tag.name,
              value: tag.id,
            }))}
            disabled={tagsLoading}
          />
          {tagsLoading && (
            <div style={{ textAlign: 'center', padding: '8px 0' }}>
              <Spin size="small" />
            </div>
          )}
        </Form.Item>
        <Form.Item
          name="chart_type"
          label={t('dataSource.chartType')}
          rules={[
            {
              required: true,
              type: 'array',
              min: 1,
              message: t('common.selectMsg'),
            },
          ]}
        >
          <Checkbox.Group
            options={getChartTypeList().map((item) => ({
              label: t(item.label),
              value: item.value,
            }))}
          />
        </Form.Item>
        <Form.Item
          name="groups"
          label={t('common.group')}
          rules={[
            {
              required: true,
              message: `${t('common.selectMsg')}${t('common.group')}`,
            },
          ]}
        >
          <GroupTreeSelect
            placeholder={`${t('common.selectMsg')}${t('common.group')}`}
            multiple={true}
            mode="ownership"
          />
        </Form.Item>
        <Form.Item name="desc" label={t('dataSource.describe')}>
          <Input.TextArea
            rows={3}
            placeholder={`${t('common.inputMsg')} ${t('dataSource.describe')}`}
          />
        </Form.Item>
        <div style={{ margin: '0 0 0 66px' }}>
          <div
            style={{
              marginBottom: '8px',
              color: 'var(--color-text-1)',
              fontSize: '14px',
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
            }}
          >
            <span>{t('dataSource.params')}：</span>
            <Button
              type="dashed"
              size="small"
              icon={<PlusCircleOutlined />}
              onClick={() => setParams([...params, createDefaultParam()])}
            >
              {t('dataSource.addParam')}
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
              description={t('common.noData')}
            />
          )}
          {duplicateNames.length > 0 && (
            <div
              style={{
                color: 'var(--color-fail)',
                fontSize: '12px',
                marginTop: '2px',
                padding: '2px 8px',
              }}
            >
              {t('dataSource.duplicateParamNames')}
              {duplicateNames.join('、')}
            </div>
          )}
        </div>
      </Form>
    </Drawer>
  );
};

export default OperateModal;
