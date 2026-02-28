'use client';

import React, {
  useState,
  useEffect,
  useRef,
  forwardRef,
  useImperativeHandle,
} from 'react';
import { Input, Button, Form, message, Select, Radio, Checkbox } from 'antd';
import { DndContext, closestCenter, PointerSensor, useSensor, useSensors } from '@dnd-kit/core';
import { SortableContext, verticalListSortingStrategy, useSortable, arrayMove } from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import OperateModal from '@/components/operate-modal';
import type { FormInstance } from 'antd';
import { PlusOutlined, DeleteTwoTone, HolderOutlined } from '@ant-design/icons';
import { deepClone } from '@/app/cmdb/utils/common';
import { useSearchParams } from 'next/navigation';
import {
  AttrFieldType,
  EnumList,
  AttrGroup,
  StrAttrOption,
  TimeAttrOption,
  IntAttrOption,
} from '@/app/cmdb/types/assetManage';
import { useTranslation } from '@/utils/i18n';
import { useModelApi } from '@/app/cmdb/api';
const { Option } = Select;

interface AttrModalProps {
  onSuccess: (type?: unknown) => void;
  attrTypeList: Array<{ id: string; name: string }>;
  groups: AttrGroup[];
}

interface AttrConfig {
  type: string;
  attrInfo: any;
  subTitle: string;
  title: string;
}

export interface AttrModalRef {
  showModal: (info: AttrConfig) => void;
}

const SortableItem = ({
  id,
  index,
  children,
}: {
  id: string;
  index: number;
  children: React.ReactNode;
}) => {
  const { attributes, listeners, setNodeRef, transform, transition } =
    useSortable({ id });
  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    marginTop: index ? 10 : 0,
    display: 'flex',
  };
  return (
    <li ref={setNodeRef} style={style}>
      {React.Children.map(children, (child, idx) =>
        idx === 0 && React.isValidElement(child)
          ? React.cloneElement(child, { ...attributes, ...listeners })
          : child
      )}
    </li>
  );
};

const AttributesModal = forwardRef<AttrModalRef, AttrModalProps>(
  (props, ref) => {
    const { onSuccess, attrTypeList, groups } = props;
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
    const [confirmLoading, setConfirmLoading] = useState<boolean>(false);
    const formRef = useRef<FormInstance>(null);
    const searchParams = useSearchParams();

    const { createModelAttr, updateModelAttr } = useModelApi();

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
        } else {
          const option = attrInfo.option;
          if (attrInfo.attr_type === 'enum' && Array.isArray(option)) {
            setEnumList(option.length > 0 ? option : [{ id: '', name: '' }]);
          } else {
            setEnumList([{ id: '', name: '' }]);
          }
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
    }));

    const handleSubmit = () => {
      formRef.current?.validateFields().then((values) => {
        const selectedGroup = groups.find(
          (group) => group.id === values.group_id,
        );

        let option: EnumList[] | StrAttrOption | TimeAttrOption | IntAttrOption | Record<string, unknown> = {};

        if (values.attr_type === 'enum') {
          const enumArray = Array.isArray(enumList) ? enumList : [];
          const flag = enumArray.every((item) => !!item.id && !!item.name);
          option = flag ? enumArray : [];
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
        }

        const restValues = { ...values };
        delete restValues.validation_type;
        delete restValues.custom_regex;
        delete restValues.widget_type;
        delete restValues.display_format;
        delete restValues.min_value;
        delete restValues.max_value;

        operateAttr({
          ...restValues,
          option,
          attr_group: selectedGroup?.group_name || '',
          model_id: modelId,
        });
      });
    };

    // 自定义验证枚举列表
    const validateEnumList = async () => {
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
          >
            <Form.Item<AttrFieldType>
              label={t('name')}
              name="attr_name"
              rules={[{ required: true, message: t('required') }]}
            >
              <Input />
            </Form.Item>
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
              <Input disabled={type === 'edit'} />
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
                    <Option value={item.id} key={item.id}>
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
                      <DndContext
                        sensors={sensors}
                        collisionDetection={closestCenter}
                        onDragEnd={onDragEnd}
                      >
                        <SortableContext
                          items={enumList.map((_, idx) => idx.toString())}
                          strategy={verticalListSortingStrategy}
                        >
                          <ul className="ml-6">
                            <li className="flex items-center mb-2 text-sm text-[var(--color-text-secondary)]">
                              <span className="mr-[4px] w-[14px]"></span>
                              <span className="mr-[10px] w-2/5">
                                {t('fieldValue')}
                              </span>
                              <span className="mr-[10px] w-2/5">
                                {t('Model.display')}
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
                                    t('common.inputTip') + t('fieldValue')
                                  }
                                  className="mr-[10px] w-2/5"
                                  value={enumItem.id}
                                  onChange={(e) => onEnumKeyChange(e, index)}
                                />
                                <Input
                                  placeholder={
                                    t('common.inputTip') + t('Model.display')
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
                                  <DeleteTwoTone
                                    className="delete cursor-pointer"
                                    onClick={() => deleteEnumItem(index)}
                                  />
                                )}
                              </SortableItem>
                            ))}
                          </ul>
                        </SortableContext>
                      </DndContext>
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
                          <Radio value="multi_line">{t('Model.multiLine')}</Radio>
                        </Radio.Group>
                      </Form.Item>
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
                    {getFieldValue('attr_type') !== 'enum' && (
                      <Form.Item<AttrFieldType>
                        name="is_only"
                        valuePropName="checked"
                        className="mb-0"
                      >
                        <Checkbox disabled={type === 'edit'}>{t('unique')}</Checkbox>
                      </Form.Item>
                    )}
                    <Form.Item<AttrFieldType>
                      name="is_required"
                      valuePropName="checked"
                      className="mb-0"
                    >
                      <Checkbox>{t('required')}</Checkbox>
            </Form.Item>
            <Form.Item<AttrFieldType>
                      name="editable"
                      valuePropName="checked"
                      className="mb-0"
                    >
                      <Checkbox>{t('editable')}</Checkbox>
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
