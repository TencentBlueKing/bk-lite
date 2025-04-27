'use client';

import React, {
  useState,
  useEffect,
  useRef,
  forwardRef,
  useImperativeHandle,
} from 'react';
import { Input, Button, Form, message, Select, Radio } from 'antd';
import { DragDropContext, Droppable, Draggable } from 'react-beautiful-dnd';
import OperateModal from '@/components/operate-modal';
import type { FormInstance } from 'antd';
import { PlusOutlined, DeleteTwoTone, HolderOutlined } from '@ant-design/icons';
import { deepClone } from '@/app/cmdb/utils/common';
import useApiClient from '@/utils/request';
import { useSearchParams } from 'next/navigation';
import { AttrFieldType, EnumList } from '@/app/cmdb/types/assetManage';
import { useTranslation } from '@/utils/i18n';
const { Option } = Select;

interface AttrModalProps {
  onSuccess: (type?: unknown) => void;
  attrTypeList: Array<{ id: string; name: string }>;
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

const AttributesModal = forwardRef<AttrModalRef, AttrModalProps>(
  ({ onSuccess, attrTypeList }, ref) => {
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
    const { post, put } = useApiClient();
    const searchParams = useSearchParams();
    const classificationId: string =
      searchParams.get('classification_id') || '';
    const modelId: string = searchParams.get('model_id') || '';
    const { t } = useTranslation();

    useEffect(() => {
      if (modelVisible) {
        formRef.current?.resetFields();
        formRef.current?.setFieldsValue(attrInfo);
      }
    }, [modelVisible, attrInfo]);

    useImperativeHandle(ref, () => ({
      showModal: ({ type, attrInfo, subTitle, title }) => {
        // 开启弹窗的交互
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
          setEnumList(attrInfo.option || []);
        }
        setAttrInfo(attrInfo);
      },
    }));

    const handleSubmit = () => {
      formRef.current?.validateFields().then((values) => {
        const flag = enumList.every((item) => !!item.id && !!item.name);
        operateAttr({
          ...values,
          option: flag ? enumList : [],
          attr_group: classificationId,
          model_id: modelId,
        });
      });
    };

    // 自定义验证枚举列表
    const validateEnumList = async () => {
      if (enumList.some((item) => !item.id || !item.name)) {
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

    const onEnumValChange = (
      e: React.ChangeEvent<HTMLInputElement>,
      index: number
    ) => {
      const enumTypeList = deepClone(enumList);
      enumTypeList[index].id = e.target.value;
      setEnumList(enumTypeList);
    };
    const onEnumKeyChange = (
      e: React.ChangeEvent<HTMLInputElement>,
      index: number
    ) => {
      const enumTypeList = deepClone(enumList);
      enumTypeList[index].name = e.target.value;
      setEnumList(enumTypeList);
    };

    const onDragEnd = (result: any) => {
      if (!result.destination) return;
      const items = Array.from(enumList);
      const [reorderedItem] = items.splice(result.source.index, 1);
      items.splice(result.destination.index, 0, reorderedItem);
      setEnumList(items);
    };

    const operateAttr = async (params: AttrFieldType) => {
      try {
        setConfirmLoading(true);
        const msg: string = t(
          type === 'add' ? 'successfullyAdded' : 'successfullyModified'
        );
        const url: string =
          type === 'add'
            ? `/cmdb/api/model/${params.model_id}/attr/`
            : `/cmdb/api/model/${params.model_id}/attr_update/`;
        const requestParams = deepClone(params);
        const requestType = type === 'add' ? post : put;
        await requestType(url, requestParams);
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
                {t('confirm')}
              </Button>
              <Button onClick={handleCancel}> {t('cancel')}</Button>
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
                    <DragDropContext onDragEnd={onDragEnd}>
                      <Droppable droppableId="enumList">
                        {(provided: any) => (
                          <ul
                            className="bg-[var(--color-bg-hover)] p-[10px]"
                            {...provided.droppableProps}
                            ref={provided.innerRef}
                          >
                            {enumList.map((enumItem, index) => (
                              <Draggable
                                key={index}
                                draggableId={`item-${index}`}
                                index={index}
                              >
                                {(provided: any) => (
                                  <li
                                    className={`flex ${
                                      index ? 'mt-[10px]' : ''
                                    }`}
                                    ref={provided.innerRef}
                                    {...provided.draggableProps}
                                    {...provided.dragHandleProps}
                                  >
                                    <HolderOutlined className="mr-[4px]" />
                                    <Input
                                      placeholder={t('fieldKey')}
                                      className="mr-[10px] w-1/5"
                                      value={enumItem.name}
                                      onChange={(e) =>
                                        onEnumKeyChange(e, index)
                                      }
                                    />
                                    <Input
                                      placeholder={t('fieldValue')}
                                      className="mr-[10px] w-3/5"
                                      value={enumItem.id}
                                      onChange={(e) =>
                                        onEnumValChange(e, index)
                                      }
                                    />
                                    <PlusOutlined
                                      className="edit mr-[10px] cursor-pointer text-[var(--color-primary)]"
                                      onClick={addEnumItem}
                                    />
                                    {index ? (
                                      <DeleteTwoTone
                                        className="delete cursor-pointer"
                                        onClick={() => deleteEnumItem(index)}
                                      />
                                    ) : null}
                                  </li>
                                )}
                              </Draggable>
                            ))}
                            {provided.placeholder}
                          </ul>
                        )}
                      </Droppable>
                    </DragDropContext>
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
