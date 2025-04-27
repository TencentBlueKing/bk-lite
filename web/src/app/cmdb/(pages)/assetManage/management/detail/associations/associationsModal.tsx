'use client';

import React, {
  useState,
  useEffect,
  useRef,
  forwardRef,
  useImperativeHandle,
} from 'react';
import { Button, Form, message, Select } from 'antd';
import OperateModal from '@/components/operate-modal';
import Image from 'next/image';
import { getIconUrl } from '@/app/cmdb/utils/common';
import type { FormInstance } from 'antd';
import associationsModalStyle from './associationsModal.module.scss';
import { deepClone } from '@/app/cmdb/utils/common';
import useApiClient from '@/utils/request';
const { Option } = Select;
import {
  AssoTypeItem,
  ModelItem,
  AssoFieldType,
  GroupItem,
} from '@/app/cmdb/types/assetManage';
import { useTranslation } from '@/utils/i18n';

interface AssoModalProps {
  onSuccess: () => void;
  constraintList: Array<{ id: string; name: string }>;
  allModelList: ModelItem[];
  assoTypeList: AssoTypeItem[];
  groups: GroupItem[];
}

interface AssoConfig {
  type: string;
  assoInfo: any;
  subTitle: string;
  title: string;
}

export interface AssoModalRef {
  showModal: (info: AssoConfig) => void;
}

const AssociationsModal = forwardRef<AssoModalRef, AssoModalProps>(
  ({ onSuccess, constraintList, allModelList, assoTypeList, groups }, ref) => {
    const [modelVisible, setModelVisible] = useState<boolean>(false);
    const [subTitle, setSubTitle] = useState<string>('');
    const [title, setTitle] = useState<string>('');
    const [assoType, setAssoType] = useState<string>('');
    const [confirmLoading, setConfirmLoading] = useState<boolean>(false);
    const [assoInfo, setAssoInfo] = useState<any>({});
    const formRef = useRef<FormInstance>(null);
    const { post } = useApiClient();
    const { t } = useTranslation();

    useEffect(() => {
      if (modelVisible) {
        formRef.current?.resetFields();
        formRef.current?.setFieldsValue(assoInfo);
      }
    }, [modelVisible, assoInfo]);

    useImperativeHandle(ref, () => ({
      showModal: ({ type, assoInfo, subTitle, title }) => {
        // 开启弹窗的交互
        setModelVisible(true);
        setSubTitle(subTitle);
        setTitle(title);
        setAssoInfo(assoInfo);
        setAssoType(type);
      },
    }));

    const showModelKeyName = (id: string, key: string) => {
      return allModelList.find((item) => item.model_id === id)?.[key] || '--';
    };

    const operateRelationships = async (params: AssoFieldType) => {
      try {
        setConfirmLoading(true);
        const requestParams = deepClone(params);
        await post('/cmdb/api/model/association/', requestParams);
        message.success(t('successfullyAdded'));
        onSuccess();
        handleCancel();
      } catch (error) {
        console.log(error);
      } finally {
        setConfirmLoading(false);
      }
    };

    const handleSubmit = () => {
      formRef.current?.validateFields().then((values) => {
        operateRelationships(values);
      });
    };

    const handleCancel = () => {
      setModelVisible(false);
    };

    return (
      <div>
        <OperateModal
          title={title}
          width={600}
          subTitle={subTitle}
          visible={modelVisible}
          onCancel={handleCancel}
          footer={
            <div>
              <Button
                className="mr-[10px]"
                type="primary"
                loading={confirmLoading}
                disabled={assoType === 'edit'}
                onClick={handleSubmit}
              >
                {t('confirm')}
              </Button>
              <Button onClick={handleCancel}>{t('cancel')}</Button>
            </div>
          }
        >
          <Form
            className={associationsModalStyle.associationsModal}
            ref={formRef}
            name="basic"
            labelCol={{ span: 6 }}
            wrapperCol={{ span: 18 }}
            disabled={assoType === 'edit'}
          >
            <Form.Item<AssoFieldType>
              label={t('Model.sourceModel')}
              name="src_model_id"
              rules={[{ required: true, message: t('required') }]}
            >
              <Select allowClear disabled>
                {allModelList.map((item) => {
                  return (
                    <Option value={item.model_id} key={item.model_id}>
                      {item.model_name}
                    </Option>
                  );
                })}
              </Select>
            </Form.Item>
            <Form.Item<AssoFieldType>
              label={t('Model.targetModel')}
              name="dst_model_id"
              rules={[{ required: true, message: t('required') }]}
            >
              <Select
                allowClear
                showSearch
                options={groups.map((item) => ({
                  label: item.classification_name,
                  title: item.classification_name,
                  options: item.list.map((tex) => ({
                    label: tex.model_name,
                    value: tex.model_id,
                  })),
                }))}
              ></Select>
            </Form.Item>
            <Form.Item<AssoFieldType>
              label={t('Model.associationType')}
              name="asst_id"
              rules={[
                {
                  required: true,
                  message: t('required'),
                },
              ]}
            >
              <Select allowClear>
                {assoTypeList.map((item) => {
                  return (
                    <Option value={item.asst_id} key={item.asst_id}>
                      {item.asst_name}
                    </Option>
                  );
                })}
              </Select>
            </Form.Item>
            <Form.Item<AssoFieldType>
              label={t('Model.constraint')}
              name="mapping"
              rules={[
                {
                  required: true,
                  message: t('required'),
                },
              ]}
            >
              <Select>
                {constraintList.map((item) => {
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
                prevValues.asst_id !== currentValues.asst_id ||
                prevValues.dst_model_id !== currentValues.dst_model_id ||
                prevValues.src_model_id !== currentValues.src_model_id
              }
            >
              {({ getFieldValue }) =>
                getFieldValue('asst_id') &&
                getFieldValue('dst_model_id') &&
                getFieldValue('src_model_id') ? (
                    <Form.Item<AssoFieldType> label={t('Model.effect')}>
                      <div
                        className={associationsModalStyle.effectRepresentation}
                      >
                        <div className={associationsModalStyle.modelObject}>
                          <div className="mb-[4px]">
                            <Image
                              src={getIconUrl({
                                icn: showModelKeyName(
                                  getFieldValue('src_model_id'),
                                  'icn'
                                ),
                                model_id: getFieldValue('src_model_id'),
                              })}
                              className="block bg-[var(--color-bg-1)] p-[6px] rounded-[50%]"
                              alt={t('picture')}
                              width={40}
                              height={40}
                            />
                          </div>
                          <span
                            className={associationsModalStyle.modelObjectName}
                          >
                            {showModelKeyName(
                              getFieldValue('src_model_id'),
                              'model_name'
                            )}
                          </span>
                        </div>
                        <div className={associationsModalStyle.modelEdge}>
                          <div className={associationsModalStyle.connection}>
                            <span className={associationsModalStyle.name}>
                              {assoTypeList.find(
                                (tex) => tex.asst_id === getFieldValue('asst_id')
                              )?.asst_name || '--'}
                            </span>
                          </div>
                        </div>
                        <div className={associationsModalStyle.modelObject}>
                          <div className="mb-[4px]">
                            <Image
                              src={getIconUrl({
                                icn: showModelKeyName(
                                  getFieldValue('dst_model_id'),
                                  'icn'
                                ),
                                model_id: getFieldValue('dst_model_id'),
                              })}
                              className="block bg-[var(--color-bg-1)] p-[6px] rounded-[50%]"
                              alt={t('picture')}
                              width={40}
                              height={40}
                            />
                          </div>
                          <span
                            className={associationsModalStyle.modelObjectName}
                          >
                            {showModelKeyName(
                              getFieldValue('dst_model_id'),
                              'model_name'
                            )}
                          </span>
                        </div>
                      </div>
                    </Form.Item>
                  ) : null
              }
            </Form.Item>
          </Form>
        </OperateModal>
      </div>
    );
  }
);
AssociationsModal.displayName = 'associationsModal';
export default AssociationsModal;
