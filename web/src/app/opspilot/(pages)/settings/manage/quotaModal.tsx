import React, { useEffect, useState, useCallback } from 'react';
import { Form, Input, Select, Button, InputNumber, Radio, Tooltip } from 'antd';
import { InfoCircleOutlined } from '@ant-design/icons';
import OperateModal from '@/components/operate-modal';
import GroupTreeSelect from '@/components/group-tree-select';
import { useTranslation } from '@/utils/i18n';
import styles from './index.module.scss';
import { QuotaModalProps, TargetOption } from '@/app/opspilot/types/settings'
import { useQuotaApi } from '@/app/opspilot/api/settings';

const { Option } = Select;

const QuotaModal: React.FC<QuotaModalProps> = ({ visible, onConfirm, onCancel, mode, initialValues }) => {
  const { t } = useTranslation();
  const [form] = Form.useForm();
  const [targetType, setTargetType] = useState<string>('user');
  const [userList, setUserList] = useState<TargetOption[]>([]);
  const [loading, setLoading] = useState<boolean>(false);
  const [targetLoading, setTargetLoading] = useState<boolean>(false);
  const { fetchGroupUsers } = useQuotaApi();

  const fetchData = useCallback(async () => {
    setTargetLoading(true);
    try {
      const userData = await fetchGroupUsers();
      setUserList(userData.map((user: any) => ({ id: user.username, name: user.username })));
    } finally {
      setTargetLoading(false);
    }
  }, [form]);

  useEffect(() => {
    if (visible && targetType === 'user' && userList.length === 0) {
      fetchData()
    }
  }, [visible])

  useEffect(() => {
    if (visible) {
      if (mode === 'edit' && initialValues) {
        form.setFieldsValue({
          ...initialValues
        });
        setTargetType(initialValues.targetType);
      } else if (mode === 'add') {
        form.resetFields();
        setTargetType('user');
        form.setFieldsValue({
          targetType: 'user',
          rule: 'uniform'
        });
      }
    }
  }, [visible]);

  const handleTargetTypeChange = (value: string) => {
    setTargetType(value);

    form.setFieldsValue({
      targetList: [],
      rule: 'uniform',
      targetType: value
    });

    if (value === 'user' && userList.length === 0) {
      fetchData();
    }
  };

  const handleSubmit = () => {
    form.validateFields().then((values) => {
      setLoading(true);
      onConfirm(values).finally(() => {
        setLoading(false);
      });
    }).catch((info) => {
      console.log('Validate Failed: ', info);
    });
  };

  return (
    <OperateModal
      width={850}
      title={mode === 'add' ? t('settings.manageQuota.form.add') : t('settings.manageQuota.form.edit')}
      visible={visible}
      onCancel={onCancel}
      footer={[
        <Button key="back" onClick={onCancel}>
          {t('common.cancel')}
        </Button>,
        <Button key="submit" type="primary" loading={loading} onClick={handleSubmit}>
          {t('common.confirm')}
        </Button>,
      ]}
    >
      <Form form={form} layout="vertical" name="quota_form">
        <Form.Item
          label={t('settings.manageQuota.form.name')}
          name="name"
          rules={[{ required: true, message: `${t('common.inputMsg')}${t('settings.manageQuota.form.name')}!` }]}
        >
          <Input placeholder={`${t('common.inputMsg')}${t('settings.manageQuota.form.name')}`} />
        </Form.Item>
        <Form.Item label={t('settings.manageQuota.form.target')} required>
          <Input.Group compact>
            <Form.Item
              name="targetType"
              noStyle
              rules={[{ required: true, message: `${t('common.selectMsg')}${t('settings.manageQuota.form.target')}` }]}
            >
              <Select style={{ width: '30%' }} onChange={handleTargetTypeChange}>
                <Option value="user">User</Option>
                <Option value="group">Group</Option>
              </Select>
            </Form.Item>
            <Form.Item
              name="targetList"
              noStyle
              rules={[{ required: true, message: `${t('common.selectMsg')}${t('settings.manageQuota.form.target')}` }]}
            >
              {targetType === 'user' ? (
                <Select
                  allowClear
                  mode="multiple"
                  maxTagCount="responsive"
                  className={styles.multipleSelect}
                  style={{ width: '70%' }}
                  loading={targetLoading}
                  disabled={targetLoading}
                  placeholder={`${t('common.selectMsg')}${t('settings.manageQuota.form.target')}`}
                >
                  {userList.map(item => (
                    <Option key={item.id} value={item.id}>{item.name}</Option>
                  ))}
                </Select>
              ) : (
                <GroupTreeSelect
                  multiple={false}
                  style={{ width: '70%' }}
                  placeholder={`${t('common.selectMsg')}${t('settings.manageQuota.form.target')}`}
                />
              )}
            </Form.Item>
          </Input.Group>
        </Form.Item>
        <Form.Item
          label={t('settings.manageQuota.form.rule')}
          name="rule"
          rules={[{ required: true, message: `${t('common.selectMsg')}` }]}>
          <Radio.Group
            disabled={targetType === 'user'}
            onChange={(e) => {
              const newRule = e.target.value;
              form.setFieldsValue({ rule: newRule });
            }}>
            <Radio value="uniform">
              {t('settings.manageQuota.form.uniform')}
              <Tooltip title={t('settings.manageQuota.form.uniformTooltip')}>
                <InfoCircleOutlined style={{ marginLeft: 8 }} />
              </Tooltip>
            </Radio>
            <Radio value="shared" style={{ marginLeft: 16 }}>
              {t('settings.manageQuota.form.shared')}
              <Tooltip title={t('settings.manageQuota.form.sharedTooltip')}>
                <InfoCircleOutlined style={{ marginLeft: 8 }} />
              </Tooltip>
            </Radio>
          </Radio.Group>
        </Form.Item>
        <Form.Item
          label={t('settings.manageQuota.form.bot')}
          name="bots"
          rules={[{ required: true, message: `${t('common.inputMsg')}${t('settings.manageQuota.form.bot')}` }]}
        >
          <InputNumber
            min={0}
            style={{ width: '100%' }}
            placeholder={`${t('common.inputMsg')}${t('settings.manageQuota.form.bot')}`} />
        </Form.Item>
        <Form.Item
          label={t('settings.manageQuota.form.skill')}
          name="skills"
          rules={[{ required: true, message: `${t('common.inputMsg')}${t('settings.manageQuota.form.skill')}` }]}
        >
          <InputNumber
            min={0}
            style={{ width: '100%' }}
            placeholder={`${t('common.inputMsg')}${t('settings.manageQuota.form.skill')}`} />
        </Form.Item>
        <Form.Item
          label={t('settings.manageQuota.form.knowledgeBase')}
          name="file_size"
          rules={[{ required: true, message: `${t('common.inputMsg')}${t('settings.manageQuota.form.knowledgeBase')}` }]}
        >
          <InputNumber
            min={0}
            addonAfter={
              <Form.Item name="unit" noStyle initialValue="MB">
                <Select>
                  <Option value="MB">MB</Option>
                  <Option value="GB">GB</Option>
                </Select>
              </Form.Item>
            }
            style={{ width: '100%' }}
            placeholder={`${t('common.inputMsg')}${t('settings.manageQuota.form.knowledgeBase')}`}
          />
        </Form.Item>
      </Form>
    </OperateModal>
  );
};

export default QuotaModal;
