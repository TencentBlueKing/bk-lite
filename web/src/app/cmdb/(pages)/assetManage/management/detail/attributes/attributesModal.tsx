'use client';

import React, {
  useState,
  useEffect,
  useRef,
  forwardRef,
  useImperativeHandle,
} from 'react';
import { Input, Button, Form, message, Select, Radio } from 'antd';
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
          const optionArray = Array.isArray(attrInfo.option)
            ? attrInfo.option
            : [];
          setEnumList(
            optionArray.length > 0 ? optionArray : [{ id: '', name: '' }],
          );
        }
        setAttrInfo(attrInfo);
      },
    }));

    const handleSubmit = () => {
      formRef.current?.validateFields().then((values) => {
        const selectedGroup = groups.find(
          (group) => group.id === values.group_id,
        );

        // 只有枚举类型才处理 enumList
        let option = [];
        if (values.attr_type === 'enum') {
          const enumArray = Array.isArray(enumList) ? enumList : [];
          const flag = enumArray.every((item) => !!item.id && !!item.name);
          option = flag ? enumArray : [];
        }

        operateAttr({
          ...values,
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
              rules={[{ required: true, message: t('required') }]}
            >
              <Input disabled={type === 'edit'} />
            </Form.Item>
            <Form.Item<AttrFieldType>
              label={t('Model.attrGroupName')}
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
                    label={t('value')}
                    name="option"
                    rules={[{ validator: validateEnumList }]}
                  >
                    <DndContext
                      sensors={sensors}
                      collisionDetection={closestCenter}
                      onDragEnd={onDragEnd}
                    >
                      <SortableContext
                        items={enumList.map((_, idx) => idx.toString())}
                        strategy={verticalListSortingStrategy}
                      >
                        <ul className="bg-[var(--color-bg-hover)] p-[10px]">
                          {enumList.map((enumItem, index) => (
                            <SortableItem
                              key={index}
                              id={index.toString()}
                              index={index}
                            >
                              <HolderOutlined className="mr-[4px]" />
                              <Input
                                placeholder={t('fieldKey')}
                                className="mr-[10px] w-1/5"
                                value={enumItem.id}
                                onChange={(e) => onEnumKeyChange(e, index)}
                              />
                              <Input
                                placeholder={t('fieldValue')}
                                className="mr-[10px] w-3/5"
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
                  </Form.Item>
                ) : null
              }
            </Form.Item>
            <Form.Item<AttrFieldType>
              label={t('editable')}
              name="editable"
              rules={[{ required: true, message: t('required') }]}
            >
              <Radio.Group>
                <Radio value={true}>{t('yes')}</Radio>
                <Radio value={false}>{t('no')}</Radio>
              </Radio.Group>
            </Form.Item>
            <Form.Item<AttrFieldType>
              label={t('unique')}
              name="is_only"
              rules={[{ required: true, message: t('required') }]}
            >
              <Radio.Group disabled={type === 'edit'}>
                <Radio value={true}>{t('yes')}</Radio>
                <Radio value={false}>{t('no')}</Radio>
              </Radio.Group>
            </Form.Item>
            <Form.Item<AttrFieldType>
              label={t('required')}
              name="is_required"
              rules={[{ required: true, message: t('required') }]}
            >
              <Radio.Group>
                <Radio value={true}>{t('yes')}</Radio>
                <Radio value={false}>{t('no')}</Radio>
              </Radio.Group>
            </Form.Item>
          </Form>
        </OperateModal>
      </div>
    );
  }
);
AttributesModal.displayName = 'attributesModal';
export default AttributesModal;
