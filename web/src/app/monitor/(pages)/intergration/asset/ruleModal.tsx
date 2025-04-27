'use client';

import React, {
  useState,
  useRef,
  forwardRef,
  useImperativeHandle,
  useEffect,
} from 'react';
import { Input, Button, Form, message, Radio } from 'antd';
import SelectInstance from './selectInstance';
import { PlusOutlined } from '@ant-design/icons';
import OperateModal from '@/components/operate-modal';
import type { FormInstance } from 'antd';
import useApiClient from '@/utils/request';
import { ModalRef, ListItem } from '@/app/monitor/types';
import { RuleInfo, GroupingRules } from '@/app/monitor/types/monitor';
import { useTranslation } from '@/utils/i18n';
import { deepClone } from '@/app/monitor/utils/common';
import CustomCascader from '@/components/custom-cascader';

interface ModalProps {
  onSuccess: () => void;
  groupList: ListItem[];
  monitorObject: React.Key;
}

const RuleModal = forwardRef<ModalRef, ModalProps>(
  ({ onSuccess, groupList, monitorObject }, ref) => {
    const { post, put } = useApiClient();
    const { t } = useTranslation();
    const formRef = useRef<FormInstance>(null);
    const instRef = useRef<ModalRef>(null);
    const [groupVisible, setGroupVisible] = useState<boolean>(false);
    const [confirmLoading, setConfirmLoading] = useState<boolean>(false);
    const [groupForm, setGroupForm] = useState<RuleInfo>({});
    const [title, setTitle] = useState<string>('');
    const [type, setType] = useState<string>('');
    const [instList, setInstList] = useState<string[]>([]);

    useImperativeHandle(ref, () => ({
      showModal: ({ type, form, title }) => {
        // 开启弹窗的交互
        const formData = deepClone(form);
        setGroupVisible(true);
        setType(type);
        setTitle(title);
        if (type === 'add') {
          formData.type = 'select';
          setInstList([]);
        } else {
          if (formData.grouping_rules?.query) {
            formData.grouping_rules = formData.grouping_rules.query;
          }
          if (formData.grouping_rules?.instances) {
            setInstList(formData.grouping_rules.instances);
          }
        }
        setGroupForm(formData);
      },
    }));

    useEffect(() => {
      if (groupVisible) {
        formRef.current?.resetFields();
        formRef.current?.setFieldsValue(groupForm);
      }
    }, [groupVisible, groupForm]);

    const openInstModal = () => {
      const title = `${t('common.select')} ${t('monitor.asset')}`;
      instRef.current?.showModal({
        title,
        type: 'add',
        form: {},
      });
    };

    const operateGroup = async (params: RuleInfo) => {
      try {
        setConfirmLoading(true);
        const msg: string = t(
          type === 'add'
            ? 'common.successfullyAdded'
            : 'common.successfullyModified'
        );
        const url: string =
          type === 'add'
            ? '/monitor/api/monitor_instance_group_rule/'
            : `/monitor/api/monitor_instance_group_rule/${groupForm.id}/`;
        const requestType = type === 'add' ? post : put;
        await requestType(url, params);
        message.success(msg);
        handleCancel();
        onSuccess();
      } catch (error) {
        console.log(error);
      } finally {
        setConfirmLoading(false);
      }
    };

    const handleSubmit = () => {
      formRef.current?.validateFields().then((values) => {
        const groupingRules: GroupingRules = {};
        if (values.type === 'select') {
          groupingRules.instances = instList;
        } else {
          groupingRules.query = values.grouping_rules;
        }
        operateGroup({
          ...values,
          monitor_object: monitorObject,
          grouping_rules: groupingRules,
          organizations: values.organizations || [],
        });
      });
    };

    const operateSelect = (list: string[]) => {
      setInstList(list);
    };

    const handleCancel = () => {
      setGroupVisible(false);
    };

    // 自定义验证枚举列表
    const validateDimensions = async () => {
      if (!instList.length) {
        return Promise.reject(new Error(t('monitor.assetValidate')));
      }
      return Promise.resolve();
    };

    return (
      <div>
        <OperateModal
          width={600}
          title={title}
          visible={groupVisible}
          onCancel={handleCancel}
          footer={
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
          }
        >
          <Form
            ref={formRef}
            name="basic"
            labelCol={{ span: 4 }}
            wrapperCol={{ span: 18 }}
          >
            <Form.Item<RuleInfo>
              label={t('common.name')}
              name="name"
              rules={[{ required: true, message: t('common.required') }]}
            >
              <Input />
            </Form.Item>
            <Form.Item<RuleInfo>
              label={t('common.type')}
              name="type"
              rules={[{ required: true, message: t('common.required') }]}
            >
              <Radio.Group>
                <Radio value="select">{t('common.select')}</Radio>
                <Radio value="condition">
                  {t('monitor.intergrations.condition')}
                </Radio>
              </Radio.Group>
            </Form.Item>
            <Form.Item
              noStyle
              shouldUpdate={(prevValues, currentValues) =>
                prevValues.type !== currentValues.type
              }
            >
              {({ getFieldValue }) =>
                getFieldValue('type') === 'select' ? (
                  <Form.Item<RuleInfo>
                    label={t('monitor.asset')}
                    name="grouping_rules"
                    rules={[{ required: true, validator: validateDimensions }]}
                  >
                    <div className="flex">
                      {t('common.select')}
                      <span className="text-[var(--color-primary)] px-[4px]">
                        {instList.length}
                      </span>
                      {t('monitor.assets')}
                      <Button
                        className="ml-[10px]"
                        icon={<PlusOutlined />}
                        size="small"
                        onClick={openInstModal}
                      ></Button>
                    </div>
                  </Form.Item>
                ) : (
                  <Form.Item<RuleInfo>
                    label={t('monitor.intergrations.condition')}
                    name="grouping_rules"
                    rules={[{ required: true, message: t('common.required') }]}
                  >
                    <Input />
                  </Form.Item>
                )
              }
            </Form.Item>
            <Form.Item<RuleInfo>
              label={t('monitor.group')}
              name="organizations"
              rules={[{ required: true, message: t('common.required') }]}
            >
              <CustomCascader
                multiple
                showSearch
                maxTagCount="responsive"
                options={groupList}
              />
            </Form.Item>
          </Form>
          <SelectInstance
            ref={instRef}
            monitorObject={monitorObject}
            organizationList={groupList}
            list={instList}
            onSuccess={operateSelect}
          />
        </OperateModal>
      </div>
    );
  }
);
RuleModal.displayName = 'RuleModal';
export default RuleModal;
