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
import useIntegrationApi from '@/app/monitor/api/integration';
import { CardItem, ChannelItem } from '@/app/monitor/types/event';
import { UserItem } from '@/app/monitor/types';
import { useCommon } from '@/app/monitor/context/common';
import SelectCard from '../strategy/detail/selectCard';
import {
  buildBulkApplyPayload,
  buildPolicyPreview,
  BulkAssetItem,
  BulkConfig,
  displayAssetName,
  getAssetCollectionTemplateLabels,
  getAssetOrganizationText,
  getMetricLabel,
  getPrimaryNoticeType,
  getTemplateKey,
  normalizeBulkConfig,
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
  trigger_count: 1,
  notice: false,
  notice_type: '',
  notice_type_ids: [],
  notice_users: [],
  enable_alerts: ['threshold'],
  no_data_enabled: false,
  no_data_period: { type: 'min', value: 5 },
  no_data_level: 'warning',
  no_data_alert_name: '无数据告警'
};

const timeUnitOptions = [
  { label: '分钟', value: 'min' },
  { label: '小时', value: 'hour' }
];

const noDataLevelOptions = [
  { label: '严重', value: 'critical' },
  { label: '错误', value: 'error' },
  { label: '警告', value: 'warning' }
];

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
  const labels = getAssetCollectionTemplateLabels(asset);
  if (!labels.length) return '--';
  return (
    <Space size={[4, 4]} wrap>
      {labels.map((label, index) => (
        <Tag key={`${label}-${index}`}>
          {label}
        </Tag>
      ))}
    </Space>
  );
};

const BulkApplyModal: React.FC<BulkApplyModalProps> = ({
  visible,
  monitorObjectId,
  selectedTemplates,
  onClose,
  onSuccess
}) => {
  const [form] = Form.useForm<BulkConfig>();
  const { getAllUsers } = useMonitorApi();
  const { getInstanceListByPrimaryObject } = useIntegrationApi();
  const { bulkCreatePoliciesFromTemplates, getSystemChannelList } = useEventApi();
  const commonContext = useCommon();
  const organizationList = commonContext?.authOrganizations || [];
  const [currentStep, setCurrentStep] = useState(0);
  const [templates, setTemplates] = useState<PolicyTemplateItem[]>([]);
  const [assets, setAssets] = useState<BulkAssetItem[]>([]);
  const [selectedAssetIds, setSelectedAssetIds] = useState<React.Key[]>([]);
  const [channelList, setChannelList] = useState<ChannelItem[]>([]);
  const [userList, setUserList] = useState<UserItem[]>([]);
  const [loadingAssets, setLoadingAssets] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [config, setConfig] = useState<BulkConfig>(defaultConfig);

  useEffect(() => {
    if (!visible) return;
    setCurrentStep(0);
    setTemplates(selectedTemplates);
    setSelectedAssetIds([]);
    setConfig(defaultConfig);
    form.setFieldsValue(defaultConfig);
    loadAssets();
    loadNotificationOptions();
  }, [visible, monitorObjectId]);

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
      const data = await getInstanceListByPrimaryObject({
        id: monitorObjectId,
        page: 1,
        page_size: 1000
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
    setConfig(normalizeBulkConfig({
      ...defaultConfig,
      ...values,
      schedule: values.schedule || defaultConfig.schedule,
      period: values.period || defaultConfig.period,
      no_data_period: values.no_data_period || defaultConfig.no_data_period
    }, channelList));
  };

  const handleChannelChange = (ids: (string | number)[]) => {
    form.setFieldValue('notice_type_ids', ids);
    form.setFieldValue('notice_type', getPrimaryNoticeType(ids, channelList));
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
    const normalizedConfig = normalizeBulkConfig({
      ...defaultConfig,
      ...values,
    }, channelList);
    const payload = buildBulkApplyPayload({
      monitorObjectId,
      templates,
      assets: selectedAssets,
      config: normalizedConfig
    });
    setSubmitting(true);
    try {
      const result = await bulkCreatePoliciesFromTemplates(payload);
      const createdCount = result?.created_count ?? previewItems.length;
      message.success(`批量创建成功，已创建 ${createdCount} 条监控策略`);
      handleClose();
      onSuccess();
    } finally {
      setSubmitting(false);
    }
  };

  const handleClose = () => {
    form.resetFields();
    setCurrentStep(0);
    setTemplates([]);
    setAssets([]);
    setSelectedAssetIds([]);
    setConfig(defaultConfig);
    onClose();
  };

  const footer = (
    <div className={templateStyle.modalFooter}>
      <Button onClick={handleClose}>取消</Button>
      <Space>
        {currentStep > 0 && <Button onClick={() => setCurrentStep((step) => step - 1)}>上一步</Button>}
        <Button type="primary" loading={submitting} onClick={handleNext}>
          {currentStep === 2 ? '创建策略' : '下一步'}
        </Button>
      </Space>
    </div>
  );

  return (
    <Modal
      title="批量应用策略模版"
      open={visible}
      width={1080}
      onCancel={handleClose}
      footer={footer}
      className={templateStyle.bulkApplyDialog}
      destroyOnHidden
    >
      <div className={templateStyle.bulkModal}>
        <Steps
          className={templateStyle.bulkSteps}
          current={currentStep}
          items={[
            { title: '确认模版' },
            { title: '选择资产' },
            { title: '公共配置' }
          ]}
        />

        {currentStep === 0 && (
          <div className={templateStyle.stepPanel}>
            <div className={templateStyle.stepHint}>
              确认本次要应用的模版。阈值、算法和告警级别会沿用模版默认配置。
            </div>
            <List
              className={templateStyle.templateConfirmList}
              dataSource={templates}
              locale={{ emptyText: '暂无策略模版' }}
              renderItem={(item) => (
                <List.Item
                  actions={[
                    <Button
                      key="remove"
                      type="link"
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
          </div>
        )}

        {currentStep === 1 && (
          <div className={templateStyle.stepPanel}>
            <div className={templateStyle.stepHint}>
              选择这些模版要覆盖的监控资产。最终按所选模版 x 所选资产批量创建策略。
            </div>
            <Table
              className={templateStyle.assetTable}
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
                  render: (_, record) => getAssetOrganizationText(record, organizationList)
                },
                {
                  title: '采集模版',
                  dataIndex: 'plugins',
                  key: 'plugins',
                  render: (_, record) => getCollectionTemplateText(record)
                }
              ]}
            />
          </div>
        )}

        {currentStep === 2 && (
          <div className={templateStyle.stepPanel}>
            <div className={templateStyle.stepHint}>
              只配置批量策略共享的轻量项。复杂项如阈值、算法、告警级别继续使用模版默认值。
            </div>
            <div className={templateStyle.configStep}>
              <Form
                form={form}
                layout="vertical"
                initialValues={defaultConfig}
                onValuesChange={handleValuesChange}
                className={templateStyle.configForm}
              >
                <div className={templateStyle.formGrid}>
                  <Form.Item
                    label="策略名称前缀"
                    name="name_prefix"
                    rules={[{ required: true, message: '请输入策略名称前缀' }]}
                  >
                    <Input placeholder="例如：生产环境-" />
                  </Form.Item>
                  <Form.Item label="检测频率" required>
                    <Space.Compact block>
                      <Form.Item name={['schedule', 'value']} noStyle rules={[{ required: true, message: '请输入检测频率' }]}>
                        <InputNumber min={1} className="w-full" />
                      </Form.Item>
                      <Form.Item name={['schedule', 'type']} noStyle>
                        <Select className="w-[96px]" options={timeUnitOptions} />
                      </Form.Item>
                    </Space.Compact>
                  </Form.Item>
                  <Form.Item label="汇聚周期" required>
                    <Space.Compact block>
                      <Form.Item name={['period', 'value']} noStyle rules={[{ required: true, message: '请输入汇聚周期' }]}>
                        <InputNumber min={1} className="w-full" />
                      </Form.Item>
                      <Form.Item name={['period', 'type']} noStyle>
                        <Select className="w-[96px]" options={timeUnitOptions} />
                      </Form.Item>
                    </Space.Compact>
                  </Form.Item>
                  <Form.Item
                    label="触发条件"
                    name="trigger_count"
                    rules={[{ required: true, message: '请输入触发次数' }]}
                  >
                    <InputNumber min={1} precision={0} className="w-full" addonBefore="连续" addonAfter="个周期" />
                  </Form.Item>
                  <Form.Item label="启用状态" name="enable" valuePropName="checked">
                    <Switch checkedChildren="启用" unCheckedChildren="停用" />
                  </Form.Item>
                </div>
                <div className={templateStyle.noticeRow}>
                  <Form.Item label="无数据告警" name="no_data_enabled" valuePropName="checked">
                    <Switch checkedChildren="开启" unCheckedChildren="关闭" />
                  </Form.Item>
                  <span>当指标查询结果为空时触发无数据告警。</span>
                </div>
                <Form.Item noStyle shouldUpdate={(prev, next) => prev.no_data_enabled !== next.no_data_enabled}>
                  {({ getFieldValue }) =>
                    getFieldValue('no_data_enabled') ? (
                      <div className={templateStyle.formGrid}>
                        <Form.Item label="无数据周期" required>
                          <Space.Compact block>
                            <Form.Item
                              name={['no_data_period', 'value']}
                              noStyle
                              rules={[{ required: true, message: '请输入无数据周期' }]}
                            >
                              <InputNumber min={1} className="w-full" />
                            </Form.Item>
                            <Form.Item name={['no_data_period', 'type']} noStyle>
                              <Select className="w-[96px]" options={timeUnitOptions} />
                            </Form.Item>
                          </Space.Compact>
                        </Form.Item>
                        <Form.Item
                          label="无数据级别"
                          name="no_data_level"
                          rules={[{ required: true, message: '请选择无数据告警级别' }]}
                        >
                          <Select options={noDataLevelOptions} />
                        </Form.Item>
                        <Form.Item
                          label="无数据告警名称"
                          name="no_data_alert_name"
                          rules={[{ required: true, message: '请输入无数据告警名称' }]}
                        >
                          <Input placeholder="例如：无数据告警" />
                        </Form.Item>
                      </div>
                    ) : null
                  }
                </Form.Item>
                <div className={templateStyle.noticeRow}>
                  <Form.Item label="通知配置" name="notice" valuePropName="checked">
                    <Switch checkedChildren="开启" unCheckedChildren="关闭" />
                  </Form.Item>
                  <span>选择告警触发时的通知渠道和接收人。</span>
                </div>
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
          </div>
        )}
      </div>
    </Modal>
  );
};

export default BulkApplyModal;
