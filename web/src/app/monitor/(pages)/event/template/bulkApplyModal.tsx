'use client';

import React, { useEffect, useMemo, useState } from 'react';
import {
  Button,
  Form,
  Input,
  InputNumber,
  List,
  message,
  Modal,
  Result,
  Select,
  Space,
  Steps,
  Switch,
  Table,
  Tag
} from 'antd';
import { DeleteOutlined } from '@ant-design/icons';
import useMonitorApi from '@/app/monitor/api';
import useEventApi from '@/app/monitor/api/event';
import { CardItem, ChannelItem } from '@/app/monitor/types/event';
import { UserItem } from '@/app/monitor/types';
import SelectCard from '../strategy/detail/selectCard';
import {
  buildBulkApplyPayload,
  buildPolicyPreview,
  BulkAssetItem,
  BulkConfig,
  displayAssetName,
  getMetricLabel,
  getTemplateKey,
  PolicyTemplateItem
} from './templateBulkUtils';
import templateStyle from './index.module.scss';

interface BulkApplyModalProps {
  visible: boolean;
  monitorObjectId: string | number;
  selectedTemplates: PolicyTemplateItem[];
  onClose: () => void;
  onSuccess: () => void;
}

const defaultConfig: BulkConfig = {
  name_prefix: '批量策略',
  enable: true,
  schedule: { type: 'min', value: 5 },
  period: { type: 'min', value: 5 },
  notice: false,
  notice_type_ids: [],
  notice_users: []
};

const getChannelIcon = (channelType: string): string => {
  const iconMap: Record<string, string> = {
    email: 'youjian',
    enterprise_wechat_bot: 'qiwei2',
    feishu_bot: 'feishu',
    dingtalk_bot: 'dingding',
    custom_webhook: 'webhook',
    nats: 'dongzuo1'
  };
  return iconMap[channelType] || 'jiqiren3';
};

const getChannelTag = (channelType: string): string => {
  const labelMap: Record<string, string> = {
    email: '邮件',
    enterprise_wechat_bot: '企业微信',
    feishu_bot: '飞书',
    dingtalk_bot: '钉钉',
    custom_webhook: 'Webhook',
    nats: 'NATS'
  };
  return labelMap[channelType] || channelType;
};

const getCollectionTemplateText = (asset: BulkAssetItem) => {
  const plugins = asset.plugins || [];
  if (!plugins.length) return '--';
  return (
    <Space size={[4, 4]} wrap>
      {plugins.map((plugin, index) => (
        <Tag key={`${plugin.name || plugin.id || index}`}>
          {plugin.display_name || plugin.name || plugin.id || '--'}
        </Tag>
      ))}
    </Space>
  );
};

const getOrganizationText = (asset: BulkAssetItem): string => {
  const organization = asset.organization || asset.organizations;
  if (!organization) return '--';
  if (Array.isArray(organization)) {
    return organization
      .map((item: any) => item?.name || item?.label || item)
      .filter(Boolean)
      .join(',') || '--';
  }
  if (typeof organization === 'object') {
    return (organization as any).name || (organization as any).label || '--';
  }
  return String(organization);
};

const BulkApplyModal: React.FC<BulkApplyModalProps> = ({
  visible,
  monitorObjectId,
  selectedTemplates,
  onClose,
  onSuccess
}) => {
  const [form] = Form.useForm<BulkConfig>();
  const { getInstanceList, getAllUsers } = useMonitorApi();
  const { bulkCreatePoliciesFromTemplates, getSystemChannelList } = useEventApi();
  const [currentStep, setCurrentStep] = useState(0);
  const [templates, setTemplates] = useState<PolicyTemplateItem[]>([]);
  const [assets, setAssets] = useState<BulkAssetItem[]>([]);
  const [selectedAssetIds, setSelectedAssetIds] = useState<React.Key[]>([]);
  const [channelList, setChannelList] = useState<ChannelItem[]>([]);
  const [userList, setUserList] = useState<UserItem[]>([]);
  const [loadingAssets, setLoadingAssets] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [createdCount, setCreatedCount] = useState<number | null>(null);
  const [config, setConfig] = useState<BulkConfig>(defaultConfig);

  useEffect(() => {
    if (!visible) return;
    setCurrentStep(0);
    setTemplates(selectedTemplates);
    setSelectedAssetIds([]);
    setCreatedCount(null);
    setConfig(defaultConfig);
    form.setFieldsValue(defaultConfig);
    loadAssets();
    loadNotificationOptions();
  }, [visible, selectedTemplates, monitorObjectId]);

  const selectedAssets = useMemo(
    () => assets.filter((asset) => selectedAssetIds.includes(asset.instance_id)),
    [assets, selectedAssetIds]
  );

  const previewItems = useMemo(
    () => buildPolicyPreview(templates, selectedAssets, config),
    [templates, selectedAssets, config]
  );

  const channelCardData: CardItem[] = useMemo(
    () =>
      channelList.map((item) => ({
        icon: getChannelIcon(item.channel_type),
        title: item.name,
        tag: getChannelTag(item.channel_type),
        description: item.description,
        value: item.id
      })),
    [channelList]
  );

  const loadAssets = async () => {
    if (!monitorObjectId) return;
    setLoadingAssets(true);
    try {
      const data = await getInstanceList(monitorObjectId, {
        page: 1,
        page_size: -1
      });
      const list = Array.isArray(data) ? data : data?.items || data?.results || [];
      setAssets(list);
    } finally {
      setLoadingAssets(false);
    }
  };

  const loadNotificationOptions = async () => {
    const [channels, users] = await Promise.all([
      getSystemChannelList(),
      getAllUsers()
    ]);
    setChannelList(channels || []);
    setUserList(users || []);
  };

  const handleRemoveTemplate = (template: PolicyTemplateItem) => {
    const key = getTemplateKey(template);
    setTemplates((prev) => prev.filter((item) => getTemplateKey(item) !== key));
  };

  const handleValuesChange = (_: Partial<BulkConfig>, values: BulkConfig) => {
    setConfig({
      ...defaultConfig,
      ...values,
      schedule: values.schedule || defaultConfig.schedule,
      period: values.period || defaultConfig.period
    });
  };

  const handleChannelChange = (ids: (string | number)[]) => {
    form.setFieldValue('notice_type_ids', ids);
    const selectedTypes = channelList
      .filter((item) => ids.includes(item.id))
      .map((item) => item.channel_type);
    if (selectedTypes.length && selectedTypes.every((type) => type === 'nats')) {
      form.setFieldValue('notice_users', []);
    }
    handleValuesChange({}, form.getFieldsValue(true));
  };

  const handleNext = async () => {
    if (currentStep === 0 && !templates.length) {
      message.warning('请至少保留一个策略模版');
      return;
    }
    if (currentStep === 1 && !selectedAssetIds.length) {
      message.warning('请至少选择一个监控资产');
      return;
    }
    if (currentStep === 2) {
      await handleCreate();
      return;
    }
    setCurrentStep((step) => step + 1);
  };

  const handleCreate = async () => {
    const values = await form.validateFields();
    const payload = buildBulkApplyPayload({
      monitorObjectId,
      templates,
      assets: selectedAssets,
      config: {
        ...defaultConfig,
        ...values
      }
    });
    setSubmitting(true);
    try {
      const result = await bulkCreatePoliciesFromTemplates(payload);
      setCreatedCount(result?.created_count ?? previewItems.length);
      message.success('批量创建成功');
      onSuccess();
    } finally {
      setSubmitting(false);
    }
  };

  const handleClose = () => {
    form.resetFields();
    onClose();
  };

  const footer = createdCount === null ? (
    <Space>
      <Button onClick={handleClose}>取消</Button>
      {currentStep > 0 && <Button onClick={() => setCurrentStep((step) => step - 1)}>上一步</Button>}
      <Button type="primary" loading={submitting} onClick={handleNext}>
        {currentStep === 2 ? '创建策略' : '下一步'}
      </Button>
    </Space>
  ) : (
    <Button type="primary" onClick={handleClose}>
      完成
    </Button>
  );

  return (
    <Modal
      title="批量应用策略模版"
      open={visible}
      width={1080}
      onCancel={handleClose}
      footer={footer}
      destroyOnHidden
    >
      {createdCount !== null ? (
        <Result
          status="success"
          title="策略创建完成"
          subTitle={`已创建 ${createdCount} 条监控策略`}
        />
      ) : (
        <div className={templateStyle.bulkModal}>
          <Steps
            current={currentStep}
            items={[
              { title: '确认模版' },
              { title: '选择资产' },
              { title: '公共配置' }
            ]}
          />

          {currentStep === 0 && (
            <List
              className={templateStyle.templateConfirmList}
              dataSource={templates}
              locale={{ emptyText: '暂无策略模版' }}
              renderItem={(item) => (
                <List.Item
                  actions={[
                    <Button
                      key="remove"
                      type="text"
                      danger
                      icon={<DeleteOutlined />}
                      onClick={() => handleRemoveTemplate(item)}
                    >
                      移除
                    </Button>
                  ]}
                >
                  <List.Item.Meta
                    title={item.name || '--'}
                    description={`策略指标：${getMetricLabel(item)}`}
                  />
                </List.Item>
              )}
            />
          )}

          {currentStep === 1 && (
            <Table
              rowKey="instance_id"
              loading={loadingAssets}
              dataSource={assets}
              pagination={{ pageSize: 8, showSizeChanger: false }}
              rowSelection={{
                selectedRowKeys: selectedAssetIds,
                onChange: setSelectedAssetIds
              }}
              columns={[
                {
                  title: '资产名称',
                  dataIndex: 'instance_name',
                  key: 'instance_name',
                  render: (_, record) => displayAssetName(record)
                },
                {
                  title: '所属组织',
                  dataIndex: 'organization',
                  key: 'organization',
                  render: (_, record) => getOrganizationText(record)
                },
                {
                  title: '采集模版',
                  dataIndex: 'plugins',
                  key: 'plugins',
                  render: (_, record) => getCollectionTemplateText(record)
                }
              ]}
            />
          )}

          {currentStep === 2 && (
            <div className={templateStyle.configStep}>
              <Form
                form={form}
                layout="vertical"
                initialValues={defaultConfig}
                onValuesChange={handleValuesChange}
                className={templateStyle.configForm}
              >
                <Form.Item
                  label="策略名称前缀"
                  name="name_prefix"
                  rules={[{ required: true, message: '请输入策略名称前缀' }]}
                >
                  <Input placeholder="请输入策略名称前缀" />
                </Form.Item>
                <Form.Item label="启用状态" name="enable" valuePropName="checked">
                  <Switch />
                </Form.Item>
                <Form.Item label="检测频率" required>
                  <Space.Compact block>
                    <Form.Item name={['schedule', 'value']} noStyle rules={[{ required: true, message: '请输入检测频率' }]}>
                      <InputNumber min={1} className="w-full" />
                    </Form.Item>
                    <Form.Item name={['schedule', 'type']} noStyle>
                      <Select className="w-[96px]" options={[{ label: '分钟', value: 'min' }, { label: '小时', value: 'hour' }]} />
                    </Form.Item>
                  </Space.Compact>
                </Form.Item>
                <Form.Item label="汇聚周期" required>
                  <Space.Compact block>
                    <Form.Item name={['period', 'value']} noStyle rules={[{ required: true, message: '请输入汇聚周期' }]}>
                      <InputNumber min={1} className="w-full" />
                    </Form.Item>
                    <Form.Item name={['period', 'type']} noStyle>
                      <Select className="w-[96px]" options={[{ label: '分钟', value: 'min' }, { label: '小时', value: 'hour' }]} />
                    </Form.Item>
                  </Space.Compact>
                </Form.Item>
                <Form.Item label="通知配置" name="notice" valuePropName="checked">
                  <Switch />
                </Form.Item>
                <Form.Item noStyle shouldUpdate={(prev, next) => prev.notice !== next.notice || prev.notice_type_ids !== next.notice_type_ids}>
                  {({ getFieldValue }) =>
                    getFieldValue('notice') ? (
                      <>
                        <Form.Item
                          label="通知渠道"
                          name="notice_type_ids"
                          rules={[{ required: true, message: '请选择通知渠道' }]}
                        >
                          <SelectCard
                            data={channelCardData}
                            onChange={handleChannelChange}
                            cardWidth={180}
                          />
                        </Form.Item>
                        {(() => {
                          const selectedIds: number[] = getFieldValue('notice_type_ids') || [];
                          const selectedChannels = channelList.filter((item) => selectedIds.includes(item.id));
                          if (!selectedChannels.length || selectedChannels.every((item) => item.channel_type === 'nats')) {
                            return null;
                          }
                          return (
                            <Form.Item
                              label="通知者"
                              name="notice_users"
                              rules={[{ required: true, message: '请选择通知者' }]}
                            >
                              <Select
                                mode="multiple"
                                showSearch
                                allowClear
                                maxTagCount="responsive"
                                optionFilterProp="label"
                                options={userList.map((user) => ({
                                  label: user.display_name || user.username || user.id,
                                  value: user.id
                                }))}
                              />
                            </Form.Item>
                          );
                        })()}
                      </>
                    ) : null
                  }
                </Form.Item>
              </Form>

              <div className={templateStyle.previewPanel}>
                <div className={templateStyle.previewTitle}>创建预览</div>
                <List
                  size="small"
                  dataSource={previewItems}
                  locale={{ emptyText: '请选择模版和资产' }}
                  renderItem={(item) => (
                    <List.Item>
                      <div className={templateStyle.previewItem}>
                        <div className={templateStyle.previewName}>{item.name}</div>
                        <div className={templateStyle.previewMeta}>
                          <span>策略指标：{item.metricLabel}</span>
                          <Tag color={item.statusLabel === '启用' ? 'success' : 'default'}>
                            {item.statusLabel}
                          </Tag>
                        </div>
                      </div>
                    </List.Item>
                  )}
                />
              </div>
            </div>
          )}
        </div>
      )}
    </Modal>
  );
};

export default BulkApplyModal;
