'use client';

import React, {
  useState,
  useRef,
  forwardRef,
  useImperativeHandle,
  useEffect,
  useMemo
} from 'react';
import {
  Input,
  Button,
  Form,
  message,
  Select,
  Cascader,
  InputNumber,
  ColorPicker,
  Descriptions,
  Tag,
  theme
} from 'antd';
import { AggregationColor } from 'antd/es/color-picker/color';
import { PlusOutlined, MinusOutlined } from '@ant-design/icons';
import { useCommon } from '@/app/monitor/context/common';
import OperateModal from '@/components/operate-modal';
import type { FormInstance } from 'antd';
import useApiClient from '@/utils/request';
import useMonitorApi from '@/app/monitor/api';
import { ModalRef, ListItem } from '@/app/monitor/types';
import { MetricInfo } from '@/app/monitor/types/integration';
import { DimensionItem, EnumItem } from '@/app/monitor/types/integration';
import { useTranslation } from '@/utils/i18n';
import type { ColorPickerProps } from 'antd';
import { generate, green, presetPalettes, red } from '@ant-design/colors';
import { findCascaderPath } from '@/app/monitor/utils/common';
import { cloneDeep } from 'lodash';
const { Option } = Select;

interface ModalProps {
  onSuccess: () => void;
  groupList: ListItem[];
  monitorObject: number;
  pluginId: number;
}

type Presets = Required<ColorPickerProps>['presets'][number];

const genPresets = (presets = presetPalettes) => {
  return Object.entries(presets).map<Presets>(([label, colors]) => ({
    label,
    colors,
    key: label
  }));
};

const INIT_UNIT_ITEM = { name: null, id: null, color: '#000000' };

const MetricModal = forwardRef<ModalRef, ModalProps>(
  ({ onSuccess, groupList, monitorObject, pluginId }, ref) => {
    const { post, put } = useApiClient();
    const { getMetricsGroup } = useMonitorApi();
    const { t } = useTranslation();
    const { token } = theme.useToken();
    const presets = genPresets({
      primary: generate(token.colorPrimary),
      red,
      green
    });
    const formRef = useRef<FormInstance>(null);
    const commonContext = useCommon();
    const unitList = useMemo(
      () =>
        (commonContext?.groupedUnitList || []).map((item: any) => ({
          ...item,
          value: item.label
        })),
      [commonContext?.groupedUnitList]
    );
    const [groupVisible, setGroupVisible] = useState<boolean>(false);
    const [confirmLoading, setConfirmLoading] = useState<boolean>(false);
    const [groupForm, setGroupForm] = useState<MetricInfo>({});
    const [groupOptions, setGroupOptions] = useState<ListItem[]>(groupList);
    const [groupLoading, setGroupLoading] = useState(false);
    const groupSearchTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
    const selectedGroupIdRef = useRef<React.Key | null>(null);
    const allowInheritedGroupsRef = useRef(false);
    const groupRequestGenerationRef = useRef(0);
    const [title, setTitle] = useState<string>('');
    const [type, setType] = useState<string>('');
    const [dimensions, setDimensions] = useState<DimensionItem[]>([
      { name: '' }
    ]);

    const [enumList, setEnumList] = useState<EnumItem[]>([]);
    const isView = type === 'view';

    const loadGroupOptions = async (keyword = '') => {
      const generation = groupRequestGenerationRef.current + 1;
      groupRequestGenerationRef.current = generation;
      setGroupLoading(true);
      try {
        const page = await getMetricsGroup({
          monitor_object_id: monitorObject,
          monitor_plugin_id: pluginId,
          ...(keyword.trim() ? { keyword: keyword.trim() } : {})
        });
        const items = page.items.filter(
          (item) =>
            allowInheritedGroupsRef.current ||
            String(item.monitor_plugin) === String(pluginId)
        ) as ListItem[];
        const selectedGroup = groupList.find(
          (item) => String(item.id) === String(selectedGroupIdRef.current)
        );
        if (groupRequestGenerationRef.current !== generation) return;
        setGroupOptions(
          selectedGroup && !items.some((item) => item.id === selectedGroup.id)
            ? [...items, selectedGroup]
            : items
        );
      } catch {
        if (groupRequestGenerationRef.current === generation) {
          setGroupOptions(groupList);
        }
      } finally {
        if (groupRequestGenerationRef.current === generation) {
          setGroupLoading(false);
        }
      }
    };

    const handleGroupSearch = (value: string) => {
      if (groupSearchTimerRef.current) {
        clearTimeout(groupSearchTimerRef.current);
      }
      groupSearchTimerRef.current = setTimeout(() => {
        loadGroupOptions(value);
      }, 300);
    };

    useEffect(() => () => {
      if (groupSearchTimerRef.current) {
        clearTimeout(groupSearchTimerRef.current);
      }
    }, []);

    useEffect(() => {
      setGroupOptions(groupList);
    }, [groupList]);

    useImperativeHandle(ref, () => ({
      showModal: ({ type, form, title }) => {
        // 开启弹窗的交互
        const formData = cloneDeep(form);
        allowInheritedGroupsRef.current = type === 'view';
        selectedGroupIdRef.current = (formData.metric_group as React.Key) || null;
        setGroupVisible(true);
        void loadGroupOptions();
        setType(type);
        setTitle(title);
        try {
          if (type === 'add') {
            formData.type = 'metric';
            setDimensions([{ name: '' }]);
            setEnumList([INIT_UNIT_ITEM]);
          } else {
            setDimensions(
              (formData.dimensions as DimensionItem[])?.length
                ? (formData.dimensions as DimensionItem[])
                : [{ name: '' }]
            );
            if (formData.data_type === 'Number') {
              formData.unit = findCascaderPath(
                unitList,
                formData.unit as string
              );
            } else {
              formData.data_type = 'Enum';
              const _enumList = JSON.parse(formData.unit as string).map(
                (item: EnumItem) =>
                  Object.assign({ name: null, id: null, color: null }, item)
              );
              setEnumList(_enumList);
            }
          }
          setGroupForm(formData);
        } catch {
          setGroupForm(formData);
          setEnumList([{ name: null, id: null, color: null }]);
        }
      }
    }));

    useEffect(() => {
      if (groupVisible) {
        formRef.current?.resetFields();
        formRef.current?.setFieldsValue(groupForm);
      }
    }, [groupVisible, groupForm]);

    const operateGroup = async (params: MetricInfo) => {
      try {
        setConfirmLoading(true);
        const msg: string = t(
          type === 'add'
            ? 'common.successfullyAdded'
            : 'common.successfullyModified'
        );
        const url: string =
          type === 'add'
            ? '/monitor/api/metrics/'
            : `/monitor/api/metrics/${groupForm.id}/`;
        const requestType = type === 'add' ? post : put;
        await requestType(url, params);
        message.success(msg);
        handleCancel();
        onSuccess();
      } finally {
        setConfirmLoading(false);
      }
    };

    const handleSubmit = () => {
      formRef.current?.validateFields().then((values) => {
        operateGroup({
          ...values,
          dimensions: dimensions.some((item) => !item.name) ? [] : dimensions,
          monitor_object: monitorObject,
          monitor_plugin: pluginId,
          type: 'metric',
          unit:
            values.data_type === 'Enum'
              ? JSON.stringify(enumList)
              : values.unit.at(-1)
        });
      });
    };

    const addDimension = () => {
      const _dimensions = cloneDeep(dimensions);
      _dimensions.push({ name: '' });
      setDimensions(_dimensions);
    };

    const addEnumItem = () => {
      const _enumList = cloneDeep(enumList);
      _enumList.push(INIT_UNIT_ITEM);
      setEnumList(_enumList);
    };

    const handleCancel = () => {
      setGroupVisible(false);
    };

    // 自定义验证枚举列表
    const validateEnumList = async () => {
      if (
        enumList.length &&
        enumList.some((item) => {
          return Object.values(item).some((tex) => !tex && tex !== 0);
        })
      ) {
        return Promise.reject(new Error(t('common.valueValidate')));
      }
      return Promise.resolve();
    };

    const onDimensionValChange = (
      e: React.ChangeEvent<HTMLInputElement>,
      index: number
    ) => {
      const _dimensions = cloneDeep(dimensions);
      _dimensions[index].name = e.target.value;
      setDimensions(_dimensions);
    };

    const handleEnumIdChange = (val: number | null, index: number) => {
      const _enumList = cloneDeep(enumList);
      _enumList[index].id = val;
      setEnumList(_enumList);
    };

    const handleEnumNameChange = (
      e: React.ChangeEvent<HTMLInputElement>,
      index: number
    ) => {
      const _enumList = cloneDeep(enumList);
      _enumList[index].name = e.target.value;
      setEnumList(_enumList);
    };

    const handleEnumColorChange = (value: AggregationColor, index: number) => {
      const _enumList = cloneDeep(enumList);
      _enumList[index].color = value.toHexString();
      setEnumList(_enumList);
    };

    const deleteDimensiontem = (index: number) => {
      const _dimensions = cloneDeep(dimensions);
      _dimensions.splice(index, 1);
      setDimensions(_dimensions);
    };

    const deleteEnumItem = (index: number) => {
      const _enumList = cloneDeep(enumList);
      _enumList.splice(index, 1);
      setEnumList(_enumList);
    };

    return (
      <div>
        <OperateModal
          width={700}
          title={title}
          visible={groupVisible}
          onCancel={handleCancel}
          footer={
            isView ? (
              <Button onClick={handleCancel}>{t('common.close')}</Button>
            ) : (
              <div>
                <Button
                  className="mr-[10px]"
                  type="primary"
                  loading={confirmLoading}
                  onClick={handleSubmit}
                >
                  {t('common.confirm')}
                </Button>
                <Button onClick={handleCancel}>{t('common.cancel')}</Button>
              </div>
            )
          }
        >
          {isView ? (
            <Descriptions bordered column={1} size="small">
              <Descriptions.Item label={t('common.id')}>
                {groupForm.name || '--'}
              </Descriptions.Item>
              <Descriptions.Item label={t('common.name')}>
                <div className="flex items-center gap-2">
                  <span>{groupForm.display_name || '--'}</span>
                  {groupForm.is_ifmib === true && (
                    <Tag className="m-0" color="blue">
                      IF-MIB
                    </Tag>
                  )}
                </div>
              </Descriptions.Item>
              <Descriptions.Item label={t('monitor.integrations.metricGroup')}>
                {groupOptions.find(
                  (item) => String(item.id) === String(groupForm.metric_group)
                )?.display_name || '--'}
              </Descriptions.Item>
              <Descriptions.Item label={t('monitor.integrations.dimension')}>
                {dimensions.some((item) => item.name)
                  ? dimensions
                    .filter((item) => item.name)
                    .map((item) => item.name)
                    .join(', ')
                  : '--'}
              </Descriptions.Item>
              <Descriptions.Item label={t('monitor.integrations.formula')}>
                <div className="whitespace-pre-wrap break-all">
                  {groupForm.query || '--'}
                </div>
              </Descriptions.Item>
              <Descriptions.Item label={t('monitor.integrations.dataType')}>
                {groupForm.data_type || '--'}
              </Descriptions.Item>
              <Descriptions.Item label={t('common.unit')}>
                {groupForm.data_type === 'Enum'
                  ? enumList
                    .map((item) => `${item.id}: ${item.name}`)
                    .join(', ') || '--'
                  : Array.isArray(groupForm.unit)
                    ? groupForm.unit.at(-1) || '--'
                    : groupForm.unit || '--'}
              </Descriptions.Item>
              <Descriptions.Item label={t('common.description')}>
                <div className="whitespace-pre-wrap break-words">
                  {groupForm.description || '--'}
                </div>
              </Descriptions.Item>
            </Descriptions>
          ) : (
            <Form
              ref={formRef}
              name="basic"
              labelCol={{ span: 4 }}
              wrapperCol={{ span: 18 }}
            >
            <Form.Item<MetricInfo>
              label={t('common.id')}
              name="name"
              rules={[{ required: true, message: t('common.required') }]}
            >
              <Input disabled={type === 'edit'} />
            </Form.Item>
            <Form.Item<MetricInfo>
              label={t('common.name')}
              name="display_name"
              rules={[{ required: true, message: t('common.required') }]}
            >
              <Input />
            </Form.Item>
            <Form.Item<MetricInfo>
              label={t('monitor.integrations.metricGroup')}
              name="metric_group"
              rules={[{ required: true, message: t('common.required') }]}
            >
              <Select
                showSearch
                filterOption={false}
                loading={groupLoading}
                onSearch={handleGroupSearch}
                onDropdownVisibleChange={(open) => !open && handleGroupSearch('')}
              >
                {groupOptions.map((item) => (
                  <Option key={item.id} value={item.id}>
                    {item.display_name}
                  </Option>
                ))}
              </Select>
            </Form.Item>
            <Form.Item<MetricInfo>
              label={t('monitor.integrations.dimension')}
              name="dimensions"
            >
              <ul>
                {dimensions.map((item, index) => (
                  <li
                    className={`flex ${
                      index + 1 !== dimensions?.length && 'mb-[10px]'
                    }`}
                    key={index}
                  >
                    <Input
                      className="w-[79%]"
                      value={item.name}
                      onChange={(e) => {
                        onDimensionValChange(e, index);
                      }}
                    />
                    <Button
                      icon={<PlusOutlined />}
                      className="ml-[10px]"
                      onClick={addDimension}
                    ></Button>
                    {!!index && (
                      <Button
                        icon={<MinusOutlined />}
                        className="ml-[10px]"
                        onClick={() => deleteDimensiontem(index)}
                      ></Button>
                    )}
                  </li>
                ))}
              </ul>
            </Form.Item>
            <Form.Item<MetricInfo>
              label={t('monitor.integrations.formula')}
              name="query"
              rules={[{ required: true, message: t('common.required') }]}
            >
              <Input.TextArea rows={4} />
            </Form.Item>
            <Form.Item<MetricInfo>
              label={t('monitor.integrations.dataType')}
              name="data_type"
              rules={[{ required: true, message: t('common.required') }]}
            >
              <Select>
                <Option value="Number">
                  {t('monitor.integrations.number')}
                </Option>
                <Option value="Enum">{t('monitor.integrations.enum')}</Option>
              </Select>
            </Form.Item>
            <Form.Item
              noStyle
              shouldUpdate={(prevValues, currentValues) =>
                prevValues.data_type !== currentValues.data_type
              }
            >
              {({ getFieldValue }) => {
                const dataType = getFieldValue('data_type');
                if (!dataType) return null;
                return dataType === 'Number' ? (
                  <Form.Item<MetricInfo>
                    label={t('common.unit')}
                    name="unit"
                    rules={[{ required: true, message: t('common.required') }]}
                  >
                    <Cascader showSearch options={unitList} />
                  </Form.Item>
                ) : (
                  <Form.Item<MetricInfo>
                    label={t('common.unit')}
                    name="unit"
                    rules={[{ required: true, validator: validateEnumList }]}
                  >
                    <ul>
                      <li className="mb-[6px] text-[var(--color-text-3)] font-[600]">
                        <div className="w-[80%] flex justify-between">
                          <span className="w-[160px]">
                            {t('monitor.integrations.originalValue')}
                          </span>
                          <span className="w-[160px] ml-2">
                            {t('monitor.integrations.mappedValue')}
                          </span>
                          <span className="w-[160px] ml-2">
                            {t('monitor.integrations.color')}
                          </span>
                        </div>
                      </li>
                      {enumList.map((item, index) => (
                        <li
                          className={`flex ${
                            index + 1 !== enumList?.length && 'mb-[10px]'
                          }`}
                          key={index}
                        >
                          <div className="w-[80%] flex justify-between">
                            <InputNumber
                              placeholder={t(
                                'monitor.integrations.originalValue'
                              )}
                              className="w-[160px]"
                              min={0}
                              value={item.id}
                              onChange={(e) => handleEnumIdChange(e, index)}
                            />
                            <Input
                              placeholder={t(
                                'monitor.integrations.mappedValue'
                              )}
                              className="w-[160px] ml-2"
                              value={item.name as string}
                              onChange={(e) => {
                                handleEnumNameChange(e, index);
                              }}
                            />
                            <ColorPicker
                              className="w-[160px] ml-2"
                              value={item.color as string}
                              showText
                              presets={presets}
                              placement="bottom"
                              onChange={(value) => {
                                handleEnumColorChange(value, index);
                              }}
                            />
                          </div>
                          <Button
                            icon={<PlusOutlined />}
                            className="ml-[10px]"
                            onClick={addEnumItem}
                          ></Button>
                          {!!index && (
                            <Button
                              icon={<MinusOutlined />}
                              className="ml-[10px]"
                              onClick={() => deleteEnumItem(index)}
                            ></Button>
                          )}
                        </li>
                      ))}
                    </ul>
                  </Form.Item>
                );
              }}
            </Form.Item>
            <Form.Item<MetricInfo>
              label={t('common.description')}
              name="description"
            >
              <Input.TextArea rows={4} />
            </Form.Item>
            </Form>
          )}
        </OperateModal>
      </div>
    );
  }
);
MetricModal.displayName = 'MetricModal';
export default MetricModal;
