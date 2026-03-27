'use client';

import React, {
  useState,
  useEffect,
  useRef,
  forwardRef,
  useImperativeHandle,
} from 'react';
import {
  Input,
  Button,
  Form,
  message,
  Select,
  Radio,
  Checkbox,
  Table,
  Tooltip,
} from 'antd';
import { DndContext, closestCenter, PointerSensor, useSensor, useSensors } from '@dnd-kit/core';
import { SortableContext, verticalListSortingStrategy, arrayMove } from '@dnd-kit/sortable';
import OperateModal from '@/components/operate-modal';
import SortableItem from '@/app/cmdb/components/sortable-item';
import type { FormInstance } from 'antd';
import {
  PlusOutlined,
  MinusOutlined,
  HolderOutlined,
  SettingOutlined,
} from '@ant-design/icons';
import { deepClone } from '@/app/cmdb/utils/common';
import { useSearchParams } from 'next/navigation';
import {
  AttrFieldType,
  EnumList,
  AttrGroup,
  TagAttrOption,
  StrAttrOption,
  TimeAttrOption,
  IntAttrOption,
  TableColumnSpec,
  EnumRuleType,
  PublicEnumLibraryItem,
} from '@/app/cmdb/types/assetManage';
import { useTranslation } from '@/utils/i18n';
import { useModelApi } from '@/app/cmdb/api';
const { Option } = Select;

const TAG_VALUE_REGEX = /^[^\s:\n\r]+$/;

interface AttrModalProps {
  onSuccess: (type?: unknown) => void;
  attrTypeList: Array<{ id: string; name: string }>;
  groups: AttrGroup[];
  hasTagAttr: boolean;
  onManagePublicLibrary?: (libraryId?: string) => void;
}

interface AttrConfig {
  type: string;
  attrInfo: any;
  subTitle: string;
  title: string;
}

export interface AttrModalRef {
  showModal: (info: AttrConfig) => void;
  refreshPublicLibraries: () => void;
}

const AttributesModal = forwardRef<AttrModalRef, AttrModalProps>(
  (props, ref) => {
    const {
      onSuccess,
      attrTypeList,
      groups,
      hasTagAttr,
      onManagePublicLibrary,
    } = props;
    const [modelVisible, setModelVisible] = useState<boolean>(false);
    const [subTitle, setSubTitle] = useState<string>('');
    const [title, setTitle] = useState<string>('');
    const [type, setType] = useState<string>('');
    const [attrInfo, setAttrInfo] = useState<any>({});
    const [enumList, setEnumList] = useState<EnumList[]>([
      {
        id: '',
        name: '',
      },
    ]);
    const [tableColumnList, setTableColumnList] = useState<TableColumnSpec[]>([
      {
        column_id: '',
        column_name: '',
        column_type: 'str',
        order: 1,
      },
    ]);
    const [tagList, setTagList] = useState<Array<{ key: string; value: string }>>([
      { key: '', value: '' },
    ]);
    const [isTagBatchEdit, setIsTagBatchEdit] = useState<boolean>(false);
    const [tagBatchText, setTagBatchText] = useState<string>('');
    const [tagBatchError, setTagBatchError] = useState<string>('');
    const [tagErrors, setTagErrors] = useState<Record<number, { key?: boolean; value?: boolean }>>({});
    const [confirmLoading, setConfirmLoading] = useState<boolean>(false);
    const [enumRuleType, setEnumRuleType] = useState<EnumRuleType>('custom');
    const [publicLibraryId, setPublicLibraryId] = useState<string>('');
    const [publicLibraries, setPublicLibraries] = useState<PublicEnumLibraryItem[]>([]);
    const [enumSelectMode, setEnumSelectMode] = useState<'single' | 'multiple'>('single');
    const formRef = useRef<FormInstance>(null);
    const searchParams = useSearchParams();

    const { createModelAttr, updateModelAttr, getPublicEnumLibraries } = useModelApi();

    const modelId: string = searchParams.get('model_id') || '';
    const { t } = useTranslation();


    useEffect(() => {
      if (modelVisible) {
        formRef.current?.resetFields();
        const selectedGroup = groups.find(
          (group) => group.group_name === attrInfo.attr_group
        );
        formRef.current?.setFieldsValue({
          ...attrInfo,
          group_id: selectedGroup?.id,
        });
      }
    }, [modelVisible, attrInfo, groups]);

    useImperativeHandle(ref, () => ({
      showModal: ({ type, attrInfo, subTitle, title }) => {
        setModelVisible(true);
        setSubTitle(subTitle);
        setType(type);
        setTitle(title);
        // Load public libraries for enum type
        getPublicEnumLibraries().then((res: any) => {
          setPublicLibraries(res || []);
        }).catch(() => {
          setPublicLibraries([]);
        });
        if (type === 'add') {
          Object.assign(attrInfo, {
            is_required: false,
            editable: true,
            is_only: false,
          });
          setEnumList([
            {
              id: '',
              name: '',
            },
          ]);
          setTableColumnList([
            {
              column_id: '',
              column_name: '',
              column_type: 'str',
              order: 1,
            },
          ]);
          setTagList([{ key: '', value: '' }]);
          setIsTagBatchEdit(false);
          setTagBatchText('');
          setEnumRuleType('custom');
          setPublicLibraryId('');
          setEnumSelectMode('single');
        } else {
          const option = attrInfo.option;
          if (attrInfo.attr_type === 'enum') {
            // Handle enum_rule_type for edit mode
            const ruleType = attrInfo.enum_rule_type || 'custom';
            setEnumRuleType(ruleType);
            setEnumSelectMode(attrInfo.enum_select_mode || 'single');
            if (ruleType === 'public_library') {
              setPublicLibraryId(attrInfo.public_library_id || '');
              setEnumList([{ id: '', name: '' }]);
            } else if (Array.isArray(option)) {
              setEnumList(option.length > 0 ? option : [{ id: '', name: '' }]);
            } else {
              setEnumList([{ id: '', name: '' }]);
            }
          } else {
            setEnumList([{ id: '', name: '' }]);
            setEnumRuleType('custom');
            setPublicLibraryId('');
            setEnumSelectMode('single');
          }
          if (attrInfo.attr_type === 'table' && Array.isArray(option)) {
            setTableColumnList(option.length > 0 ? option : [{ column_id: '', column_name: '', column_type: 'str', order: 1 }]);
          } else {
            setTableColumnList([{ column_id: '', column_name: '', column_type: 'str', order: 1 }]);
          }
          if (attrInfo.attr_type === 'tag' && option && typeof option === 'object' && !Array.isArray(option)) {
            const tagOption = option as TagAttrOption;
            const opt = Array.isArray(tagOption.options) ? tagOption.options : [];
            setTagList(opt.length > 0 ? opt : [{ key: '', value: '' }]);
            attrInfo.tag_mode = tagOption.mode || 'free';
          } else {
            setTagList([{ key: '', value: '' }]);
          }
          setIsTagBatchEdit(false);
          setTagBatchText('');
          if (attrInfo.attr_type === 'str' && option && typeof option === 'object' && !Array.isArray(option)) {
            const strOption = option as StrAttrOption;
            attrInfo.validation_type = strOption.validation_type;
            attrInfo.custom_regex = strOption.custom_regex;
            attrInfo.widget_type = strOption.widget_type;
          } else if (attrInfo.attr_type === 'time' && option && typeof option === 'object' && !Array.isArray(option)) {
            const timeOption = option as TimeAttrOption;
            attrInfo.display_format = timeOption.display_format;
          } else if (attrInfo.attr_type === 'int' && option && typeof option === 'object' && !Array.isArray(option)) {
            const intOption = option as IntAttrOption;
            attrInfo.min_value = intOption.min_value;
            attrInfo.max_value = intOption.max_value;
          }
        }
        setAttrInfo(attrInfo);
      },
      refreshPublicLibraries: () => {
        getPublicEnumLibraries().then((res: any) => {
          setPublicLibraries(res || []);
        }).catch(() => {
          setPublicLibraries([]);
        });
      },
    }));

    const handleSubmit = () => {
      formRef.current?.validateFields().then((values) => {
        const selectedGroup = groups.find(
          (group) => group.id === values.group_id,
        );

        let option:
          | EnumList[]
          | StrAttrOption
          | TimeAttrOption
          | IntAttrOption
          | TableColumnSpec[]
          | TagAttrOption
          | Record<string, unknown> = {};

        if (values.attr_type === 'enum') {
          if (enumRuleType === 'public_library') {
            option = [];
          } else {
            const enumArray = Array.isArray(enumList) ? enumList : [];
            const flag = enumArray.every((item) => !!item.id && !!item.name);
            option = flag ? enumArray : [];
          }
        } else if (values.attr_type === 'table') {
          const tableArray = Array.isArray(tableColumnList) ? tableColumnList : [];
          const flag = tableArray.every((item) => !!item.column_id && !!item.column_name);
          option = flag ? tableArray.map((col, idx) => ({ ...col, order: idx + 1 })) : [];
        } else if (values.attr_type === 'str') {
          option = {
            validation_type: values.validation_type || 'unrestricted',
            custom_regex: values.custom_regex || '',
            widget_type: values.widget_type || 'single_line',
          } as StrAttrOption;
        } else if (values.attr_type === 'time') {
          option = {
            display_format: values.display_format || 'datetime',
          } as TimeAttrOption;
        } else if (values.attr_type === 'int') {
          option = {
            min_value: values.min_value || '',
            max_value: values.max_value || '',
          } as IntAttrOption;
        } else if (values.attr_type === 'tag') {
          option = {
            mode: values.tag_mode || 'free',
            options: (Array.isArray(tagList) ? tagList : [])
              .filter((item) => item.key && item.value)
              .map((item) => ({ key: item.key.trim(), value: item.value.trim() })),
          } as TagAttrOption;
          values.attr_id = 'tag';
          values.is_required = false;
          values.editable = true;
          values.is_only = false;
        }

        const restValues = { ...values };
        delete restValues.validation_type;
        delete restValues.custom_regex;
        delete restValues.widget_type;
        delete restValues.display_format;
        delete restValues.min_value;
        delete restValues.max_value;
        delete restValues.tag_mode;

        const submitParams: Record<string, unknown> = {
          ...restValues,
          option,
          attr_group: selectedGroup?.group_name || '',
          model_id: modelId,
        };

        if (values.attr_type === 'enum') {
          submitParams.enum_rule_type = enumRuleType;
          submitParams.enum_select_mode = enumSelectMode;
          if (enumRuleType === 'public_library') {
            submitParams.public_library_id = publicLibraryId;
          }
        }

        operateAttr(submitParams as AttrFieldType);
      });
    };

    // 自定义验证枚举列表
    const validateEnumList = async () => {
      if (enumRuleType === 'public_library') {
        if (!publicLibraryId) {
          return Promise.reject(new Error(t('PublicEnumLibrary.publicLibraryRequired')));
        }
        return Promise.resolve();
      }
      const enumArray = Array.isArray(enumList) ? enumList : [];
      if (enumArray.some((item) => !item.id || !item.name)) {
        return Promise.reject(new Error(t('valueValidate')));
      }
      return Promise.resolve();
    };

    const handleCancel = () => {
      setModelVisible(false);
    };

    const addEnumItem = () => {
      const enumTypeList = deepClone(enumList);
      enumTypeList.push({
        id: '',
        name: '',
      });
      setEnumList(enumTypeList);
    };

    const deleteEnumItem = (index: number) => {
      const enumTypeList = deepClone(enumList);
      enumTypeList.splice(index, 1);
      setEnumList(enumTypeList);
    };

    const onEnumKeyChange = (
      e: React.ChangeEvent<HTMLInputElement>,
      index: number
    ) => {
      const enumTypeList = deepClone(enumList);
      enumTypeList[index].id = e.target.value;
      setEnumList(enumTypeList);
    };
    const onEnumValChange = (
      e: React.ChangeEvent<HTMLInputElement>,
      index: number
    ) => {
      const enumTypeList = deepClone(enumList);
      enumTypeList[index].name = e.target.value;
      setEnumList(enumTypeList);
    };

    const validateTableColumns = async () => {
      const columnArray = Array.isArray(tableColumnList) ? tableColumnList : [];
      if (columnArray.some((item) => !item.column_id || !item.column_name)) {
        return Promise.reject(new Error(t('required')));
      }
      const columnIds = columnArray.map(c => c.column_id);
      if (new Set(columnIds).size !== columnIds.length) {
        return Promise.reject(new Error(t('Model.columnIdsMustBeUnique')));
      }
      return Promise.resolve();
    };

    const validateSingleTagItem = (key: string, value: string): string | null => {
      if (!key || !value) {
        return t('required');
      }
      if (!TAG_VALUE_REGEX.test(value)) {
        return t('Model.tagValueFormatError');
      }
      return null;
    };

    const validateTagList = async () => {
      if (isTagBatchEdit) return Promise.resolve();
      const list = Array.isArray(tagList) ? tagList : [];
      const seen = new Set<string>();
      const errors: Record<number, { key?: boolean; value?: boolean }> = {};
      let firstErr: string | null = null;
      for (let i = 0; i < list.length; i++) {
        const item = list[i];
        const key = (item.key || '').trim();
        const value = (item.value || '').trim();
        if (!key || !value) {
          errors[i] = { key: !key, value: !value };
          if (!firstErr) firstErr = t('required');
        } else if (!TAG_VALUE_REGEX.test(value)) {
          if (!firstErr) firstErr = t('Model.tagValueFormatError');
        }
        const pair = `${key}:${value}`;
        if (seen.has(pair)) {
          if (!firstErr) firstErr = t('Model.tagDuplicateError');
        }
        seen.add(pair);
      }
      if (firstErr) {
        setTagErrors(errors);
        return Promise.reject(new Error(firstErr));
      }
      setTagErrors({});
      return Promise.resolve();
    };

    const addTagItem = () => {
      const list = deepClone(tagList);
      list.push({ key: '', value: '' });
      setTagList(list);
    };

    const serializeTagList = (list: Array<{ key: string; value: string }>) => {
      return (Array.isArray(list) ? list : [])
        .filter((item) => item.key || item.value)
        .map((item) => `${(item.key || '').trim()}:${(item.value || '').trim()}`)
        .join('\n');
    };

    const parseTagBatchText = (text: string) => {
      const lines = (text || '')
        .split(/\r?\n/)
        .map((line) => line.trim())
        .filter(Boolean);

      if (lines.length === 0) {
        return [{ key: '', value: '' }];
      }

      const parsed: Array<{ key: string; value: string }> = [];
      const seen = new Set<string>();
      for (const line of lines) {
        const splitIndex = line.indexOf(':');
        if (splitIndex <= 0 || splitIndex === line.length - 1) {
          throw new Error(t('Model.tagBatchFormatError'));
        }
        const key = line.slice(0, splitIndex).trim();
        const value = line.slice(splitIndex + 1).trim();
        const err = validateSingleTagItem(key, value);
        if (err) {
          throw new Error(err);
        }
        const pair = `${key}:${value}`;
        if (seen.has(pair)) {
          throw new Error(t('Model.tagDuplicateError'));
        }
        seen.add(pair);
        parsed.push({ key, value });
      }
      return parsed;
    };

    const onOpenTagBatchEdit = () => {
      setTagBatchText(serializeTagList(tagList));
      setTagBatchError('');
      formRef.current?.setFields([{ name: 'option', errors: [] }]);
      setIsTagBatchEdit(true);
    };

    const onApplyTagBatchEdit = () => {
      try {
        const parsed = parseTagBatchText(tagBatchText);
        setTagList(parsed);
        setTagBatchError('');
        setIsTagBatchEdit(false);
      } catch (error) {
        setTagBatchError(
          error instanceof Error
            ? error.message
            : t('Model.tagBatchFormatError'),
        );
      }
    };

    const onCancelTagBatchEdit = () => {
      setIsTagBatchEdit(false);
      setTagBatchText('');
      setTagBatchError('');
    };

    const deleteTagItem = (index: number) => {
      const list = deepClone(tagList);
      list.splice(index, 1);
      setTagList(list.length ? list : [{ key: '', value: '' }]);
    };

    const onTagChange = (field: 'key' | 'value', value: string, index: number) => {
      const list = deepClone(tagList);
      list[index][field] = value;
      setTagList(list);
      if (tagErrors[index]?.[field]) {
        setTagErrors((prev) => {
          const next = { ...prev };
          if (next[index]) {
            next[index] = { ...next[index], [field]: false };
          }
          return next;
        });
      }
    };

    const addTableColumn = () => {
      const columnList = deepClone(tableColumnList);
      columnList.push({
        column_id: '',
        column_name: '',
        column_type: 'str',
        order: columnList.length + 1,
      });
      setTableColumnList(columnList);
    };

    const deleteTableColumn = (index: number) => {
      const columnList = deepClone(tableColumnList);
      columnList.splice(index, 1);
      setTableColumnList(columnList);
    };

    const onTableColumnChange = (
      field: keyof TableColumnSpec,
      value: string,
      index: number
    ) => {
      const columnList = deepClone(tableColumnList);
      if (field === 'column_type') {
        columnList[index][field] = value as 'str' | 'number';
      } else {
        columnList[index][field] = value as any;
      }
      setTableColumnList(columnList);
    };

    const onTableDragEnd = (event: any) => {
      const { active, over } = event;
      if (!over) return;
      const oldIndex = parseInt(active.id as string, 10);
      const newIndex = parseInt(over.id as string, 10);
      if (oldIndex !== newIndex) {
        setTableColumnList((items) => arrayMove(items, oldIndex, newIndex));
      }
    };

    const sensors = useSensors(useSensor(PointerSensor));

    const onDragEnd = (event: any) => {
      const { active, over } = event;
      if (!over) return;
      const oldIndex = parseInt(active.id as string, 10);
      const newIndex = parseInt(over.id as string, 10);
      if (oldIndex !== newIndex) {
        setEnumList((items) => arrayMove(items, oldIndex, newIndex));
      }
    };

    const operateAttr = async (params: AttrFieldType) => {
      try {
        setConfirmLoading(true);
        const msg: string = t(
          type === 'add' ? 'successfullyAdded' : 'successfullyModified'
        );
        const requestParams = deepClone(params);

        if (type === 'add') {
          await createModelAttr(params.model_id!, requestParams);
        } else {
          await updateModelAttr(params.model_id!, requestParams);
        }

        message.success(msg);
        onSuccess();
        handleCancel();
      } catch (error) {
        console.log(error);
      } finally {
        setConfirmLoading(false);
      }
    };

    return (
      <div>
        <OperateModal
          width={650}
          title={title}
          subTitle={subTitle}
          visible={modelVisible}
          onCancel={handleCancel}
          footer={
            <div>
              <Button
                type="primary"
                className="mr-[10px]"
                loading={confirmLoading}
                onClick={handleSubmit}
              >
                {t('common.confirm')}
              </Button>
              <Button onClick={handleCancel}> {t('common.cancel')}</Button>
            </div>
          }
        >
          <Form
            ref={formRef}
            name="basic"
            labelCol={{ span: 4 }}
            wrapperCol={{ span: 20 }}
            onValuesChange={(changedValues) => {
              if (changedValues.attr_type === 'tag') {
                formRef.current?.setFieldsValue({
                  attr_id: 'tag',
                  is_required: false,
                  editable: true,
                  is_only: false,
                  tag_mode: 'free',
                });
              } else if (
                Object.prototype.hasOwnProperty.call(
                  changedValues,
                  'attr_type',
                ) &&
                type === 'add'
              ) {
                const currentAttrId = formRef.current?.getFieldValue('attr_id');
                if (currentAttrId === 'tag') {
                  formRef.current?.setFieldsValue({ attr_id: '' });
                }
                setIsTagBatchEdit(false);
                setTagBatchText('');
              }
            }}
          >
            <Form.Item<AttrFieldType>
              label={t('name')}
              name="attr_name"
              rules={[{ required: true, message: t('required') }]}
            >
              <Input />
            </Form.Item>
            <Form.Item
              noStyle
              shouldUpdate={(prevValues, currentValues) =>
                prevValues.attr_type !== currentValues.attr_type
              }
            >
              {({ getFieldValue }) => (
                <Form.Item<AttrFieldType>
                  label={t('id')}
                  name="attr_id"
                  rules={[
                    { required: true, message: t('required') },
                    {
                      pattern: /^[A-Za-z][A-Za-z0-9_]*$/,
                      message: t('Model.attrIdPattern'),
                    },
                  ]}
                >
                  <Input
                    disabled={
                      type === 'edit' || getFieldValue('attr_type') === 'tag'
                    }
                  />
                </Form.Item>
              )}
            </Form.Item>
            <Form.Item<AttrFieldType>
              label={t('Model.attrGroup')}
              name="group_id"
              rules={[{ required: true, message: t('required') }]}
            >
              <Select placeholder={t('common.selectMsg')}>
                {props.groups.map((group) => (
                  <Option value={group.id} key={group.id}>
                    {group.group_name}
                  </Option>
                ))}
              </Select>
            </Form.Item>
            <div className="border-t border-[var(--color-border-1)] my-4" />
            <Form.Item<AttrFieldType>
              label={t('type')}
              name="attr_type"
              rules={[{ required: true, message: t('required') }]}
            >
              <Select disabled={type === 'edit'}>
                {attrTypeList.map((item) => {
                  return (
                    <Option
                      value={item.id}
                      key={item.id}
                      disabled={
                        item.id === 'tag' && type === 'add' && hasTagAttr
                      }
                    >
                      {item.name}
                    </Option>
                  );
                })}
              </Select>
            </Form.Item>
            <Form.Item
              noStyle
              shouldUpdate={(prevValues, currentValues) =>
                prevValues.attr_type !== currentValues.attr_type
              }
            >
              {({ getFieldValue }) =>
                getFieldValue('attr_type') === 'enum' ? (
                  <Form.Item<AttrFieldType>
                    label=" "
                    colon={false}
                    name="option"
                    rules={[{ validator: validateEnumList }]}
                  >
                    <div className="bg-[var(--color-fill-1)] p-4 rounded">
                      <div className="text-sm text-[var(--color-text-secondary)] mb-3">
                        {t('Model.validationRules')}
                      </div>
                      <div className="flex items-center gap-3 mb-5">
                        <span className="text-sm text-[var(--color-text-secondary)] shrink-0">
                          {t('Model.enumSelectMode')}：
                        </span>
                        <Radio.Group
                          value={enumSelectMode}
                          onChange={(e) => setEnumSelectMode(e.target.value)}
                          disabled={type === 'edit'}
                        >
                          <Radio value="single">{t('Model.singleSelect')}</Radio>
                          <Radio value="multiple">{t('Model.multipleSelect')}</Radio>
                        </Radio.Group>
                      </div>
                      <div className="flex items-center gap-3 mb-3">
                        <span className="text-sm text-[var(--color-text-secondary)] shrink-0">
                          {t('PublicEnumLibrary.enumRuleType')}：
                        </span>
                        <Radio.Group
                          value={enumRuleType}
                          onChange={(e) => {
                            setEnumRuleType(e.target.value);
                            if (e.target.value === 'custom') {
                              setPublicLibraryId('');
                            }
                          }}
                          disabled={type === 'edit'}
                        >
                          <Radio value="custom">{t('PublicEnumLibrary.enumRuleTypeCustom')}</Radio>
                          <Radio value="public_library">{t('PublicEnumLibrary.enumRuleTypePublicLibrary')}</Radio>
                        </Radio.Group>
                      </div>
                      {enumRuleType === 'public_library' ? (
                        <div className="pl-[72px]">
                          <div className="flex items-center gap-2 mb-3">
                            <Select
                              value={publicLibraryId || undefined}
                            onChange={(value) => {
                              setPublicLibraryId(value);
                              formRef.current?.validateFields(['option']);
                            }}
                              placeholder={t(
                                'PublicEnumLibrary.selectPublicLibraryPlaceholder',
                              )}
                              className="flex-1"
                              allowClear
                            >
                              {publicLibraries.map((lib) => (
                                <Option
                                  key={lib.library_id}
                                  value={lib.library_id}
                                >
                                  {lib.name}
                                </Option>
                              ))}
                            </Select>
                            {onManagePublicLibrary && (
                              <Tooltip title={t('PublicEnumLibrary.managePublicLibrary')}>
                                <Button
                                  type="text"
                                  icon={<SettingOutlined />}
                                  onClick={() => onManagePublicLibrary?.(publicLibraryId)}
                                  className="shrink-0"
                                />
                              </Tooltip>
                            )}
                          </div>
                          {publicLibraryId &&
                            (() => {
                              const selectedLib = publicLibraries.find(
                                (lib) => lib.library_id === publicLibraryId,
                              );
                              if (!selectedLib) return null;
                              if (selectedLib.options.length === 0) {
                                return (
                                  <div className="mt-2 text-sm text-[var(--color-text-tertiary)]">
                                    {t('PublicEnumLibrary.noOptions')}
                                  </div>
                                );
                              }
                              return (
                                <Table
                                  size="small"
                                  bordered
                                  dataSource={selectedLib.options}
                                  rowKey="id"
                                  pagination={false}
                                  className="mt-3 [&_.ant-table-cell]:!py-1.5" style={{ width: 'calc(100% - 40px)' }}
                                  columns={[
                                    {
                                      title: t('PublicEnumLibrary.optionId'),
                                      dataIndex: 'id',
                                      key: 'id',
                                    },
                                    {
                                      title: t('PublicEnumLibrary.optionName'),
                                      dataIndex: 'name',
                                      key: 'name',
                                    },
                                  ]}
                                />
                              );
                            })()}
                        </div>
                      ) : (
                        <DndContext
                          sensors={sensors}
                          collisionDetection={closestCenter}
                          onDragEnd={onDragEnd}
                        >
                          <SortableContext
                            items={enumList.map((_, idx) => idx.toString())}
                            strategy={verticalListSortingStrategy}
                          >
                            <ul className="pl-[72px]">
                              <li className="flex items-center mb-2 text-sm text-[var(--color-text-secondary)]">
                                <span className="mr-[4px] w-[14px]"></span>
                                <span className="mr-[10px] w-2/5">
                                  {t('PublicEnumLibrary.optionId')}
                                </span>
                                <span className="mr-[10px] w-2/5">
                                  {t('PublicEnumLibrary.optionName')}
                                </span>
                              </li>
                              {enumList.map((enumItem, index) => (
                                <SortableItem
                                  key={index}
                                  id={index.toString()}
                                  index={index}
                                >
                                  <HolderOutlined className="mr-[4px]" />
                                  <Input
                                    placeholder={
                                      t('common.inputTip') + t('PublicEnumLibrary.optionId')
                                    }
                                    className="mr-[10px] w-2/5"
                                    value={enumItem.id}
                                    onChange={(e) => onEnumKeyChange(e, index)}
                                  />
                                  <Input
                                    placeholder={
                                      t('common.inputTip') + t('PublicEnumLibrary.optionName')
                                    }
                                    className="mr-[10px] w-2/5"
                                    value={enumItem.name}
                                    onChange={(e) => onEnumValChange(e, index)}
                                  />
                                  <PlusOutlined
                                    className="edit mr-[10px] cursor-pointer text-[var(--color-primary)]"
                                    onClick={addEnumItem}
                                  />
                                  {enumList.length > 1 && (
                                    <MinusOutlined
                                      className="delete cursor-pointer text-[var(--color-primary)]"
                                      onClick={() => deleteEnumItem(index)}
                                    />
                                  )}
                                </SortableItem>
                              ))}
                            </ul>
                          </SortableContext>
                        </DndContext>
                      )}
                    </div>
                  </Form.Item>
                ) : getFieldValue('attr_type') === 'time' ? (
                  <Form.Item label=" " colon={false}>
                    <div className="bg-[var(--color-fill-1)] p-4 rounded">
                      <div className="text-sm text-[var(--color-text-secondary)] mb-3">
                        {t('Model.validationRules')}
                      </div>
                      <Form.Item<AttrFieldType>
                        name="display_format"
                        initialValue="datetime"
                        className="mb-0"
                      >
                        <Radio.Group>
                          <Radio value="datetime">{t('Model.datetime')}</Radio>
                          <Radio value="date">{t('Model.date')}</Radio>
                        </Radio.Group>
                      </Form.Item>
                    </div>
                  </Form.Item>
                ) : getFieldValue('attr_type') === 'int' ? (
                  <Form.Item label=" " colon={false}>
                    <div className="bg-[var(--color-fill-1)] p-4 rounded">
                      <div className="text-sm text-[var(--color-text-secondary)] mb-3">
                        {t('Model.validationRules')}
                      </div>
                      <div className="flex items-center gap-4">
                        <Form.Item<AttrFieldType>
                          label={t('Model.min')}
                          name="min_value"
                          className="mb-0 flex-1"
                        >
                          <Input placeholder={t('Model.emptyMeansNoLimit')} />
                        </Form.Item>
                        <span>—</span>
                        <Form.Item<AttrFieldType>
                          label={t('Model.max')}
                          name="max_value"
                          className="mb-0 flex-1"
                        >
                          <Input placeholder={t('Model.emptyMeansNoLimit')} />
                        </Form.Item>
                      </div>
                    </div>
                  </Form.Item>
                ) : getFieldValue('attr_type') === 'table' ? (
                  <Form.Item<AttrFieldType>
                    label=" "
                    colon={false}
                    name="option"
                    rules={[{ validator: validateTableColumns }]}
                  >
                    <div className="bg-[var(--color-fill-1)] p-4 rounded">
                      <div className="text-sm text-[var(--color-text-secondary)] mb-3">
                        {t('Model.validationRules')}
                      </div>
                      <DndContext
                        sensors={sensors}
                        collisionDetection={closestCenter}
                        onDragEnd={onTableDragEnd}
                      >
                        <SortableContext
                          items={tableColumnList.map((_, idx) => idx.toString())}
                          strategy={verticalListSortingStrategy}
                        >
                          <ul className="ml-6">
                            <li className="flex items-center mb-2 text-sm text-[var(--color-text-secondary)]">
                              <span className="mr-[4px] w-[14px]"></span>
                              <span
                                style={{
                                  width: 120,
                                  marginRight: 10,
                                  flexShrink: 0,
                                }}
                              >
                                {t('Model.columnId')}
                              </span>
                              <span
                                style={{
                                  width: 120,
                                  marginRight: 10,
                                  flexShrink: 0,
                                }}
                              >
                                {t('Model.columnName')}
                              </span>
                              <span style={{ width: 100, flexShrink: 0 }}>
                                {t('type')}
                              </span>
                            </li>
                            {tableColumnList.map((column, index) => (
                              <SortableItem
                                key={index}
                                id={index.toString()}
                                index={index}
                              >
                                <HolderOutlined className="mr-[4px]" />
                                <Input
                                  placeholder={t('Model.enterColumnId')}
                                  style={{
                                    width: 120,
                                    marginRight: 10,
                                    flexShrink: 0,
                                  }}
                                  value={column.column_id}
                                  onChange={(e) =>
                                    onTableColumnChange(
                                      'column_id',
                                      e.target.value,
                                      index,
                                    )
                                  }
                                />
                                <Input
                                  placeholder={t('Model.enterColumnName')}
                                  style={{
                                    width: 120,
                                    marginRight: 10,
                                    flexShrink: 0,
                                  }}
                                  value={column.column_name}
                                  onChange={(e) =>
                                    onTableColumnChange(
                                      'column_name',
                                      e.target.value,
                                      index,
                                    )
                                  }
                                />
                                <Select
                                  style={{
                                    width: 100,
                                    marginRight: 10,
                                    flexShrink: 0,
                                  }}
                                  value={column.column_type}
                                  onChange={(value) =>
                                    onTableColumnChange(
                                      'column_type',
                                      value,
                                      index,
                                    )
                                  }
                                >
                                  <Option value="str">{t('string')}</Option>
                                  <Option value="number">{t('number')}</Option>
                                </Select>
                                <PlusOutlined
                                  className="mr-[10px] cursor-pointer text-[var(--color-primary)]"
                                  onClick={addTableColumn}
                                />
                                {tableColumnList.length > 1 && (
                                  <MinusOutlined
                                    className="cursor-pointer text-[var(--color-primary)]"
                                    onClick={() => deleteTableColumn(index)}
                                  />
                                )}
                              </SortableItem>
                            ))}
                          </ul>
                        </SortableContext>
                      </DndContext>
                    </div>
                  </Form.Item>
                ) : getFieldValue('attr_type') === 'str' ? (
                  <Form.Item label=" " colon={false}>
                    <div className="bg-[var(--color-fill-1)] p-4 rounded">
                      <div className="text-sm text-[var(--color-text-secondary)] mb-3">
                        {t('Model.validationRules')}
                      </div>
                      <Form.Item<AttrFieldType>
                        name="validation_type"
                        initialValue="unrestricted"
                        className="mb-3"
                      >
                        <Select>
                          <Option value="unrestricted">
                            {t('Model.unrestricted')}
                          </Option>
                          <Option value="ipv4">{t('Model.ipv4')}</Option>
                          <Option value="ipv6">{t('Model.ipv6')}</Option>
                          <Option value="email">{t('Model.email')}</Option>
                          <Option value="mobile_phone">
                            {t('Model.mobile_phone')}
                          </Option>
                          <Option value="url">{t('Model.url')}</Option>
                          <Option value="json">{t('Model.json')}</Option>
                          <Option value="custom">
                            {t('Model.customRegex')}
                          </Option>
                        </Select>
                      </Form.Item>
                      <Form.Item
                        noStyle
                        shouldUpdate={(prevValues, currentValues) =>
                          prevValues.validation_type !==
                          currentValues.validation_type
                        }
                      >
                        {({ getFieldValue: getFieldVal }) =>
                          getFieldVal('validation_type') === 'custom' ? (
                            <Form.Item<AttrFieldType>
                              name="custom_regex"
                              className="mb-3"
                              rules={[
                                {
                                  required: true,
                                  message: t('Model.customRegexRequired'),
                                },
                              ]}
                            >
                              <Input
                                placeholder={t('Model.customRegexRequired')}
                              />
                            </Form.Item>
                          ) : null
                        }
                      </Form.Item>
                      <div className="text-sm text-[var(--color-text-secondary)] mb-2">
                        {t('Model.widgetType')}
                      </div>
                      <Form.Item<AttrFieldType>
                        name="widget_type"
                        initialValue="single_line"
                        className="mb-0"
                      >
                        <Radio.Group>
                          <Radio value="single_line">
                            {t('Model.singleLine')}
                          </Radio>
                          <Radio value="multi_line">
                            {t('Model.multiLine')}
                          </Radio>
                        </Radio.Group>
                      </Form.Item>
                    </div>
                  </Form.Item>
                ) : getFieldValue('attr_type') === 'tag' ? (
                  <Form.Item<AttrFieldType>
                    label=" "
                    colon={false}
                    name="option"
                    rules={[{ validator: validateTagList }]}
                  >
                    <div className="bg-[var(--color-fill-1)] p-4 rounded">
                      <div className="text-sm font-medium text-[var(--color-text-primary)] mb-3">
                        {t('Model.validationRules')}
                      </div>
                      <div className="flex items-center gap-3 mb-3">
                        <span className="text-sm text-[var(--color-text-secondary)] shrink-0">
                          {t('Model.tagMode')}：
                        </span>
                        <Form.Item
                          name="tag_mode"
                          initialValue="free"
                          className="mb-0"
                        >
                          <Radio.Group>
                            <Radio value="free">{t('Model.freeMode')}</Radio>
                            <Radio value="strict">
                              {t('Model.strictMode')}
                            </Radio>
                          </Radio.Group>
                        </Form.Item>
                      </div>
                      <div className="border-t border-[var(--color-border-1)] mb-3" />
                      <div className="flex items-center justify-between mb-2">
                        <span className="text-sm text-[var(--color-text-secondary)]">
                          {t('Model.tagOptions')}
                        </span>
                        <div className="flex items-center gap-3">
                          {isTagBatchEdit ? (
                            <>
                              <Button
                                type="link"
                                className="p-0"
                                onClick={onApplyTagBatchEdit}
                              >
                                {t('Model.applyTagBatch')}
                              </Button>
                              <Button
                                type="link"
                                className="p-0"
                                onClick={onCancelTagBatchEdit}
                              >
                                {t('common.cancel')}
                              </Button>
                            </>
                          ) : (
                            <Button
                              type="link"
                              className="p-0"
                              onClick={onOpenTagBatchEdit}
                            >
                              {t('Model.batchModifyTag')}
                            </Button>
                          )}
                        </div>
                      </div>
                      {/* 标签内容区 */}
                      {isTagBatchEdit ? (
                        <div>
                          <Input.TextArea
                            rows={6}
                            value={tagBatchText}
                            onChange={(e) => {
                              setTagBatchText(e.target.value);
                              setTagBatchError('');
                            }}
                            onBlur={() => {
                              if (!tagBatchText.trim()) return;
                              try {
                                parseTagBatchText(tagBatchText);
                                setTagBatchError('');
                              } catch (error) {
                                setTagBatchError(
                                  error instanceof Error
                                    ? error.message
                                    : t('Model.tagBatchFormatError'),
                                );
                              }
                            }}
                            placeholder={t('Model.tagBatchPlaceholder')}
                          />
                          {tagBatchError && (
                            <div className="text-red-500 text-xs mt-1">
                              {tagBatchError}
                            </div>
                          )}
                        </div>
                      ) : (
                        <ul className="ml-6">
                          {tagList.map((tag, index) => (
                            <li key={index} className="flex items-center mt-2">
                              <Input
                                placeholder="key"
                                className="mr-[10px] w-2/5"
                                value={tag.key}
                                status={tagErrors[index]?.key ? 'error' : ''}
                                onChange={(e) =>
                                  onTagChange('key', e.target.value, index)
                                }
                              />
                              <Input
                                placeholder="value"
                                className="mr-[12px] w-2/5"
                                value={tag.value}
                                status={tagErrors[index]?.value ? 'error' : ''}
                                onChange={(e) =>
                                  onTagChange('value', e.target.value, index)
                                }
                              />
                              <PlusOutlined
                                className="edit mr-[10px] cursor-pointer text-[var(--color-primary)]"
                                onClick={addTagItem}
                              />
                              {tagList.length > 1 && (
                                <MinusOutlined
                                  className="delete cursor-pointer text-[var(--color-primary)]"
                                  onClick={() => deleteTagItem(index)}
                                />
                              )}
                            </li>
                          ))}
                        </ul>
                      )}
                    </div>
                  </Form.Item>
                ) : null
              }
            </Form.Item>
            <div className="border-t border-[var(--color-border-1)] mt-2 mb-4" />
            <Form.Item
              noStyle
              shouldUpdate={(prevValues, currentValues) =>
                prevValues.attr_type !== currentValues.attr_type
              }
            >
              {({ getFieldValue }) => (
                <Form.Item label=" " colon={false} className="ml-[-80px]">
                  <div className="flex items-center gap-8">
                    <Form.Item<AttrFieldType>
                      name="is_required"
                      valuePropName="checked"
                      className="mb-0"
                    >
                      <Checkbox disabled={getFieldValue('attr_type') === 'tag'}>
                        {t('required')}
                      </Checkbox>
                    </Form.Item>
                    <Form.Item<AttrFieldType>
                      name="editable"
                      valuePropName="checked"
                      className="mb-0"
                    >
                      <Checkbox disabled={getFieldValue('attr_type') === 'tag'}>
                        {t('editable')}
                      </Checkbox>
                    </Form.Item>
                  </div>
                </Form.Item>
              )}
            </Form.Item>
            <Form.Item<AttrFieldType>
              label={t('Model.userPrompt')}
              name="user_prompt"
            >
              <Input.TextArea
                placeholder={t('Model.userPromptPlaceholder')}
                rows={3}
              />
            </Form.Item>
          </Form>
        </OperateModal>
      </div>
    );
  }
);
AttributesModal.displayName = 'attributesModal';
export default AttributesModal;
