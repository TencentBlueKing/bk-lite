import React, { useEffect, useState, useCallback } from 'react';
import { Form, Input, Select, Button, InputNumber, Radio, Tooltip } from 'antd';
import { InfoCircleOutlined, PlusCircleOutlined, MinusCircleOutlined } from '@ant-design/icons';
import OperateModal from '@/components/operate-modal';
import { useTranslation } from '@/utils/i18n';
import styles from './index.module.scss';
import { useUserInfoContext } from '@/context/userInfo';
import { QuotaModalProps, TargetOption } from '@/app/opspilot/types/settings'
import { useQuotaApi } from '@/app/opspilot/api/settings';

const { Option } = Select;

const QuotaModal: React.FC<QuotaModalProps> = ({ visible, onConfirm, onCancel, mode, initialValues }) => {
  const { t } = useTranslation();
  const [form] = Form.useForm();
  const { groups: groupList, selectedGroup } = useUserInfoContext();
  const [targetType, setTargetType] = useState<string>('user');
  const [rule, setRule] = useState<string>('uniform');
  const [userList, setUserList] = useState<TargetOption[]>([]);
  const [loading, setLoading] = useState<boolean>(false);
  const [targetLoading, setTargetLoading] = useState<boolean>(false);
  const [modelList, setModelList] = useState<TargetOption[]>([]);
  const [modelLoading, setModelLoading] = useState<boolean>(false);
  const { fetchGroupUsers, fetchModelsByGroup } = useQuotaApi();

  const fetchData = useCallback(async () => {
    setTargetLoading(true);
    try {
      const userData = await fetchGroupUsers();
      setUserList(userData.map((user: any) => ({ id: user.username, name: user.username })));
    } finally {
      setTargetLoading(false);
    }
  }, [form]);

  const fetchModelList = useCallback(async (groupId: string) => {
    setModelLoading(true);
    try {
      const data = await fetchModelsByGroup(groupId);
      setModelList(data.map((model: string) => ({
        id: model,
        name: model
      })));
    } finally {
      setModelLoading(false);
    }
  }, []);

  useEffect(() => {
    if (visible && targetType === 'user' && userList.length === 0) {
      fetchData()
    }
  }, [visible])

  useEffect(() => {
    if (visible) {
      if (mode === 'edit' && initialValues) {
        const tokenSet = initialValues.token_set
          ? Object.entries(initialValues.token_set as Record<string, { value: any, unit: string }>)
            .map(([model, { value, unit }]: [string, { value: any, unit: string }]) => ({
              model,
              value,
              unit
            }))
          : [];
        form.setFieldsValue({
          ...initialValues,
          token_set: tokenSet
        });
        setRule(initialValues.rule_type);
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
    if (value === 'user' && userList.length === 0) {
      fetchData();
    }
    if (value === 'group') {
      form.setFieldValue('token_set', [{ model: '', value: '', unit: '' }]);
      const defaultGroup = selectedGroup?.id;
      form.setFieldsValue({
        targetList: defaultGroup
      });
      if (defaultGroup) {
        fetchModelList(defaultGroup);
      }
    }
    form.setFieldsValue({
      rule: 'uniform',
      targetType: value
    });
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

  const handleTokenChange = (index: number, field: string, value: any) => {
    const tokenSet = form.getFieldValue('token_set') || [];
    tokenSet[index] = {
      ...tokenSet[index],
      [field]: value
    };
    form.setFieldValue('token_set', tokenSet);
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
              <Select
                allowClear
                mode={targetType === 'user' ? "multiple" : undefined}
                maxTagCount="responsive"
                className={styles.multipleSelect}
                style={{ width: '70%' }}
                loading={targetLoading}
                disabled={targetLoading}
                onChange={(value) => {
                  if (targetType === 'group' && value) {
                    fetchModelList(value);
                  }
                }}
                placeholder={`${t('common.selectMsg')}${t('settings.manageQuota.form.target')}`}>
                {(targetType === 'user' ? userList : groupList).map(item => (
                  <Option key={item.id} value={item.id}>{item.name}</Option>
                ))}
              </Select>
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
              setRule(e.target.value);
              form.setFieldsValue({ rule: e.target.value });
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
        {(targetType === 'group' && rule === 'shared') && (
          <>
            <Form.List name="token_set">
              {(fields, { add, remove }) => (
                <div className={styles.tokenSetWrapper}>
                  {fields.map((field, index) => (
                    <Form.Item
                      label={index === 0 ? t('settings.manageQuota.form.token') : ''}
                      key={field.key}
                    >
                      <div className="flex items-center justify-center">
                        <Input
                          style={{ width: '100%' }}
                          addonBefore={
                            <Select
                              showSearch
                              style={{ width: 200 }}
                              loading={modelLoading}
                              disabled={modelLoading}
                              value={form.getFieldValue(['token_set', index, 'model'])}
                              onChange={(value) => handleTokenChange(index, 'model', value)}
                            >
                              {modelList.map(model => (
                                <Option key={model.id} value={model.name}>{model.name}</Option>
                              ))}
                            </Select>
                          }
                          addonAfter={
                            <Select
                              style={{ width: 100 }}
                              value={form.getFieldValue(['token_set', index, 'unit'])}
                              onChange={(value) => handleTokenChange(index, 'unit', value)}
                            >
                              <Option value="thousand">{t('settings.manageQuota.form.thousand')}</Option>
                              <Option value="million">{t('settings.manageQuota.form.million')}</Option>
                            </Select>
                          }
                          value={form.getFieldValue(['token_set', index, 'value'])}
                          onChange={(e) => handleTokenChange(index, 'value', e.target.value)}
                        />
                        <div className="w-[65px]">
                          <PlusCircleOutlined
                            className="ml-1"
                            onClick={() => add(index)}
                          />
                          {fields.length > 1 && (
                            <MinusCircleOutlined
                              className="ml-1"
                              onClick={() => remove(index)}
                            />
                          )}
                        </div>
                      </div>
                    </Form.Item>
                  ))}
                </div>
              )}
            </Form.List>
          </>
        )}
      </Form>
    </OperateModal>
  );
};

export default QuotaModal;
