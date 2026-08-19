'use client';

import React, { useEffect, useMemo, useState } from 'react';
import {
  Alert,
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
  Tag,
  Tooltip
} from 'antd';
import { DeleteOutlined, QuestionCircleOutlined } from '@ant-design/icons';
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
  buildAssetScopeLabel,
  formatTemplateListName,
  PolicyTemplateItem
} from './templateBulkUtils';
import TemplateConditionSummary from './templateConditionSummary';
import templateStyle from './index.module.scss';
import { formatUserName } from '@/utils/userDisplay';
import { useTranslation } from '@/utils/i18n';

const ASSET_PAGE_SIZE = 1000;

const renderConfigLabel = (text: string, tip: string) => (
  <span className={templateStyle.fieldLabel}>
    {text}
    <Tooltip title={tip}>
      <QuestionCircleOutlined className={templateStyle.fieldLabelIcon} />
    </Tooltip>
  </span>
);

interface BulkApplyModalProps {
  visible: boolean;
  monitorObjectId: string | number;
  selectedTemplates: PolicyTemplateItem[];
  onClose: () => void;
  onSuccess: () => void;
}

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

const getChannelTypeKey = (channelType: string): string => {
  const keyMap: Record<string, string> = {
    email: 'monitor.events.channelTypeEmail',
    enterprise_wechat_bot: 'monitor.events.channelTypeWechatBot',
    feishu_bot: 'monitor.events.channelTypeFeishuBot',
    dingtalk_bot: 'monitor.events.channelTypeDingtalkBot',
    custom_webhook: 'monitor.events.channelTypeCustomWebhook',
    nats: 'monitor.events.channelTypeNats'
  };
  return keyMap[channelType] || '';
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
  const { t } = useTranslation();
  const [form] = Form.useForm<BulkConfig>();
  const { getAllUsers } = useMonitorApi();
  const { getInstanceListByPrimaryObject } = useIntegrationApi();
  const { bulkCreatePoliciesFromTemplates, getSystemChannelList } = useEventApi();
  const commonContext = useCommon();
  const organizationList = commonContext?.authOrganizations || [];
  const defaultConfig = useMemo<BulkConfig>(() => ({
    name_prefix: t('monitor.events.bulkNamePrefixDefault', '批量策略'),
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
    no_data_alert_name: t('monitor.events.noDataAlertDefaultName', '无数据告警')
  }), [t]);
  const timeUnitOptions = [
    { label: t('monitor.events.minutes', '分钟'), value: 'min' },
    { label: t('monitor.events.hours', '小时'), value: 'hour' }
  ];
  const noDataLevelOptions = [
    { label: t('monitor.events.critical', '严重'), value: 'critical' },
    { label: t('monitor.events.error', '错误'), value: 'error' },
    { label: t('monitor.events.warning', '警告'), value: 'warning' }
  ];
  const [currentStep, setCurrentStep] = useState(0);
  const [templates, setTemplates] = useState<PolicyTemplateItem[]>([]);
  const [assets, setAssets] = useState<BulkAssetItem[]>([]);
  const [assetTotal, setAssetTotal] = useState(0);
  const [selectedAssetIds, setSelectedAssetIds] = useState<React.Key[]>([]);
  const [channelList, setChannelList] = useState<ChannelItem[]>([]);
  const [userList, setUserList] = useState<UserItem[]>([]);
  const [loadingAssets, setLoadingAssets] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [config, setConfig] = useState<BulkConfig>(defaultConfig);
  const noDataEnabled = Form.useWatch('no_data_enabled', form);
  const noticeEnabled = Form.useWatch('notice', form);

  useEffect(() => {
    if (!visible) return;
    setCurrentStep(0);
    setTemplates(selectedTemplates);
    setSelectedAssetIds([]);
    setAssetTotal(0);
    setConfig(defaultConfig);
    form.setFieldsValue(defaultConfig);
    loadAssets();
    loadNotificationOptions();
    // 仅在弹窗打开或监控对象切换时重置；不要因 defaultConfig 引用变化冲掉用户输入
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [visible, monitorObjectId]);

  const selectedAssets = useMemo(
    () => assets.filter((asset) => selectedAssetIds.includes(asset.instance_id)),
    [assets, selectedAssetIds]
  );

  const previewItems = useMemo(
    () => buildPolicyPreview(templates, selectedAssets, config, t),
    [templates, selectedAssets, config, t]
  );

  const previewScopeLabel = useMemo(
    () => buildAssetScopeLabel(selectedAssets, t),
    [selectedAssets, t]
  );

  const previewScopeFull = useMemo(
    () => selectedAssets.map((asset) => displayAssetName(asset)).filter(Boolean).join('、') || '--',
    [selectedAssets]
  );

  const channelCardData: CardItem[] = useMemo(
    () =>
      channelList.map((item) => ({
        icon: getChannelIcon(item.channel_type),
        title: item.name,
        tag: getChannelTypeKey(item.channel_type)
          ? t(getChannelTypeKey(item.channel_type))
          : item.channel_type,
        description: item.description,
        value: item.id
      })),
    [channelList, t]
  );

  const loadAssets = async () => {
    if (!monitorObjectId) return;
    setLoadingAssets(true);
    try {
      const data = await getInstanceListByPrimaryObject({
        id: monitorObjectId,
        page: 1,
        page_size: ASSET_PAGE_SIZE
      });
      const list = Array.isArray(data) ? data : data?.items || data?.results || [];
      const total = typeof data?.count === 'number' ? data.count : list.length;
      setAssets(list);
      setAssetTotal(total);
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

  const syncPreviewConfig = (values: BulkConfig = form.getFieldsValue(true)) => {
    setConfig(normalizeBulkConfig({
      ...defaultConfig,
      ...values,
      schedule: values.schedule || defaultConfig.schedule,
      period: values.period || defaultConfig.period,
      no_data_period: values.no_data_period || defaultConfig.no_data_period
    }, channelList));
  };

  const handleValuesChange = (_: Partial<BulkConfig>, values: BulkConfig) => {
    syncPreviewConfig(values);
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
    syncPreviewConfig(form.getFieldsValue(true));
  };

  const handleNext = async () => {
    if (currentStep === 0 && !templates.length) {
      message.warning(t('monitor.events.keepAtLeastOneTemplate', '请至少保留一个策略模版'));
      return;
    }
    if (currentStep === 1 && !selectedAssetIds.length) {
      message.warning(t('monitor.events.selectAtLeastOneAsset', '请至少选择一个监控资产'));
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
      message.success(t('monitor.events.bulkCreateSuccess', '批量创建成功，已创建 {count} 条监控策略', {
        count: createdCount
      }));
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
    setAssetTotal(0);
    setConfig(defaultConfig);
    onClose();
  };

  const footer = (
    <div className={templateStyle.modalFooter}>
      <Button onClick={handleClose}>{t('common.cancel')}</Button>
      <Space>
        {currentStep > 0 && (
          <Button onClick={() => setCurrentStep((step) => step - 1)}>
            {t('common.pre')}
          </Button>
        )}
        <Button type="primary" loading={submitting} onClick={handleNext}>
          {currentStep === 2 ? t('monitor.events.createPolicies', '创建策略') : t('common.next')}
        </Button>
      </Space>
    </div>
  );

  return (
    <Modal
      title={t('monitor.events.bulkApplyTitle', '批量应用策略模版')}
      open={visible}
      width="min(1360px, calc(100vw - 40px))"
      centered
      styles={{
        content: { maxHeight: 'calc(100vh - 48px)' }
      }}
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
            { title: t('monitor.events.confirmTemplate', '确认模版') },
            { title: t('monitor.events.selectAssets', '选择资产') },
            { title: t('monitor.events.sharedConfig', '公共配置') }
          ]}
        />

        {currentStep === 0 && (
          <div className={templateStyle.stepPanel}>
            <div className={templateStyle.stepHint}>
              {t('monitor.events.confirmTemplateHint', '确认本次要应用的模版。阈值、算法和告警级别会沿用模版默认配置。')}
            </div>
            <List
              className={templateStyle.templateConfirmList}
              dataSource={templates}
              locale={{ emptyText: t('monitor.events.noTemplate', '暂无策略模版') }}
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
                      {t('common.delete')}
                    </Button>
                  ]}
                >
                  <List.Item.Meta
                    title={formatTemplateListName(item, templates)}
                    description={
                      <div className={templateStyle.templateMetaLines}>
                        <div className={templateStyle.conditionRow}>
                          <span className={templateStyle.conditionLabel}>
                            {t('monitor.events.policyMetric', '策略指标')}：
                          </span>
                          <span className={templateStyle.conditionContent}>{getMetricLabel(item)}</span>
                        </div>
                        <TemplateConditionSummary template={item} />
                      </div>
                    }
                  />
                </List.Item>
              )}
            />
          </div>
        )}

        {currentStep === 1 && (
          <div className={templateStyle.stepPanel}>
            <div className={templateStyle.stepHint}>
              <span>
                {t('monitor.events.selectAssetsHint', '选择这些模版要覆盖的监控资产。每个模版将创建一条策略，实例范围包含所选全部资产。')}
              </span>
              {assets.length > 0 && (
                <span className={templateStyle.selectionBadge}>
                  {t('monitor.events.selectedAssetCount', '已选 {selected} / {total} 个资产', {
                    selected: selectedAssetIds.length,
                    total: assets.length
                  })}
                </span>
              )}
            </div>
            {assetTotal > assets.length ? (
              <Alert
                className="mb-3"
                type="warning"
                showIcon
                message={t('monitor.events.assetTruncatedHint', '当前仅展示前 {shown} 条，共 {total} 个实例。未展示的实例无法纳入本次批量应用。', {
                  shown: assets.length,
                  total: assetTotal
                })}
              />
            ) : null}
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
                  title: t('monitor.events.assetName', '资产名称'),
                  dataIndex: 'instance_name',
                  key: 'instance_name',
                  render: (_, record) => displayAssetName(record)
                },
                {
                  title: t('monitor.events.assetGroup', '组织'),
                  dataIndex: 'organization',
                  key: 'organization',
                  render: (_, record) => getAssetOrganizationText(record, organizationList)
                },
                {
                  title: t('monitor.events.collectionTemplate', '采集模板'),
                  dataIndex: 'plugins',
                  key: 'plugins',
                  render: (_, record) => getCollectionTemplateText(record)
                }
              ]}
            />
          </div>
        )}

        <div
          className={`${templateStyle.stepPanel} ${templateStyle.configStepPanel}`}
          style={{ display: currentStep === 2 ? undefined : 'none' }}
        >
            <div className={templateStyle.stepHint}>
              {t('monitor.events.sharedConfigHint', '只配置批量策略共享的轻量项。复杂项如阈值、算法、告警级别继续使用模版默认值。')}
            </div>
            <div className={templateStyle.configStep}>
              <div className={templateStyle.configFormScroll}>
              <Form
                form={form}
                layout="vertical"
                initialValues={defaultConfig}
                onValuesChange={handleValuesChange}
                className={templateStyle.configForm}
              >
                <section className={templateStyle.configModule}>
                  <div className={templateStyle.configModuleHeader}>
                    <span className={templateStyle.configModuleTitle}>
                      {t('monitor.events.basicConfig', '基础配置')}
                    </span>
                  </div>
                  <div className={templateStyle.configModuleBody}>
                    <Form.Item
                      label={t('monitor.events.namePrefix', '策略名称前缀')}
                      name="name_prefix"
                      rules={[{ required: true, message: t('monitor.events.namePrefixRequired', '请输入策略名称前缀') }]}
                    >
                      <Input placeholder={t('monitor.events.namePrefixPlaceholder', '例如：生产环境-')} />
                    </Form.Item>
                    <Form.Item
                      label={renderConfigLabel(
                        t('monitor.events.enableStatus', '启用状态'),
                        t('monitor.events.enableStatusTip', '决定创建出来的策略是否为启用状态。')
                      )}
                      name="enable"
                      valuePropName="checked"
                    >
                      <Switch
                        checkedChildren={t('common.enable')}
                        unCheckedChildren={t('monitor.events.inactive', '停用')}
                      />
                    </Form.Item>
                    <Form.Item label={t('monitor.events.testingFrequency', '检测频率')} required>
                      <Space.Compact block>
                        <Form.Item
                          name={['schedule', 'value']}
                          noStyle
                          rules={[{ required: true, message: t('monitor.events.testingFrequencyRequired', '请输入检测频率') }]}
                        >
                          <InputNumber min={1} className="w-full" />
                        </Form.Item>
                        <Form.Item name={['schedule', 'type']} noStyle>
                          <Select className="w-[96px]" options={timeUnitOptions} />
                        </Form.Item>
                      </Space.Compact>
                    </Form.Item>
                    <Form.Item label={t('monitor.events.convergenceCycle', '汇聚周期')} required>
                      <Space.Compact block>
                        <Form.Item
                          name={['period', 'value']}
                          noStyle
                          rules={[{ required: true, message: t('monitor.events.convergenceCycleRequired', '请输入汇聚周期') }]}
                        >
                          <InputNumber min={1} className="w-full" />
                        </Form.Item>
                        <Form.Item name={['period', 'type']} noStyle>
                          <Select className="w-[96px]" options={timeUnitOptions} />
                        </Form.Item>
                      </Space.Compact>
                    </Form.Item>
                    <Form.Item
                      label={t('monitor.events.triggerCondition', '触发条件')}
                      name="trigger_count"
                      rules={[{ required: true, message: t('common.required') }]}
                    >
                      <InputNumber
                        min={1}
                        precision={0}
                        className="w-full"
                        addonBefore={t('monitor.events.triggerConditionPrefix', '连续')}
                        addonAfter={t('monitor.events.period', '周期')}
                      />
                    </Form.Item>
                  </div>
                </section>

                <section className={templateStyle.configModule}>
                  <div className={templateStyle.configModuleHeader}>
                    <span className={templateStyle.configModuleTitle}>
                      {renderConfigLabel(
                        t('monitor.events.noDataAlertLevel', '无数据告警'),
                        t('monitor.events.noDataAlertTip', '当指标查询结果为空时触发无数据告警。')
                      )}
                    </span>
                    <Form.Item name="no_data_enabled" valuePropName="checked" noStyle>
                      <Switch
                        checkedChildren={t('monitor.events.turnedOn', '开启')}
                        unCheckedChildren={t('monitor.events.turnedOff', '关闭')}
                      />
                    </Form.Item>
                  </div>
                  {noDataEnabled && (
                    <div className={`${templateStyle.configModuleBody} ${templateStyle.configModuleBodyNoData}`}>
                      <Form.Item label={t('monitor.events.noDataPeriod', '无数据周期')} required>
                        <Space.Compact block>
                          <Form.Item
                            name={['no_data_period', 'value']}
                            noStyle
                            rules={[{ required: true, message: t('monitor.events.noDataPeriodRequired', '请输入无数据周期') }]}
                          >
                            <InputNumber min={1} className="w-full" />
                          </Form.Item>
                          <Form.Item name={['no_data_period', 'type']} noStyle>
                            <Select className="w-[96px]" options={timeUnitOptions} />
                          </Form.Item>
                        </Space.Compact>
                      </Form.Item>
                      <Form.Item
                        label={t('monitor.events.level', '级别')}
                        name="no_data_level"
                        rules={[{ required: true, message: t('common.required') }]}
                      >
                        <Select options={noDataLevelOptions} />
                      </Form.Item>
                      <Form.Item
                        label={t('monitor.events.noDataAlertName', '无数据告警名称')}
                        name="no_data_alert_name"
                        rules={[{ required: true, message: t('common.required') }]}
                      >
                        <Input placeholder={t('monitor.events.noDataAlertDefaultName', '无数据告警')} />
                      </Form.Item>
                    </div>
                  )}
                </section>

                <section className={templateStyle.configModule}>
                  <div className={templateStyle.configModuleHeader}>
                    <span className={templateStyle.configModuleTitle}>
                      {renderConfigLabel(
                        t('monitor.events.notificationConfig', '通知配置'),
                        t('monitor.events.notificationDesc', '选择告警触发时的通知方式和接收人。')
                      )}
                    </span>
                    <Form.Item name="notice" valuePropName="checked" noStyle>
                      <Switch
                        checkedChildren={t('monitor.events.turnedOn', '开启')}
                        unCheckedChildren={t('monitor.events.turnedOff', '关闭')}
                      />
                    </Form.Item>
                  </div>
                  {noticeEnabled && (
                    <Form.Item noStyle shouldUpdate>
                      {({ getFieldValue }) => {
                        const selectedIds: Array<string | number> = getFieldValue('notice_type_ids') || [];
                        const selectedChannels = channelList.filter((item) => selectedIds.includes(item.id));
                        const onlyNats =
                          selectedChannels.length > 0 &&
                          selectedChannels.every((item) => item.channel_type === 'nats');
                        return (
                          <div className={`${templateStyle.configModuleBody} ${templateStyle.configModuleBodyNotice}`}>
                            <Form.Item
                              label={t('monitor.events.notificationChannelMulti', '通知渠道（可多选）')}
                              name="notice_type_ids"
                              rules={[{ required: true, message: t('monitor.events.selectNotificationChannel', '请选择通知渠道') }]}
                            >
                              <SelectCard
                                data={channelCardData}
                                onChange={handleChannelChange}
                                cardWidth={180}
                                showCheckbox
                              />
                            </Form.Item>
                            {onlyNats ? (
                              <div className="text-[12px] leading-5 text-[var(--color-text-3)]">
                                {t('monitor.events.natsNoNotifierHint', '告警将进入告警中心，无需选择通知者。')}
                              </div>
                            ) : null}
                            {selectedIds.length > 0 && !onlyNats && (
                              <Form.Item
                                label={t('monitor.events.notifier', '通知者')}
                                name="notice_users"
                                rules={[{ required: true, message: t('monitor.events.selectNotifier', '请选择通知者') }]}
                              >
                                <Select
                                  mode="multiple"
                                  showSearch
                                  allowClear
                                  maxTagCount="responsive"
                                  optionFilterProp="label"
                                  options={userList.map((user) => ({
                                    label: formatUserName(user),
                                    value: user.id
                                  }))}
                                />
                              </Form.Item>
                            )}
                          </div>
                        );
                      }}
                    </Form.Item>
                  )}
                </section>
              </Form>
              </div>

              <div className={templateStyle.previewPanel}>
                <div className={templateStyle.previewStickyHeader}>
                  <div className={templateStyle.previewTitle}>
                    {t('monitor.events.createPreview', '创建预览')}
                    {previewItems.length > 0 ? (
                      <span className={templateStyle.previewCount}>
                        {t('monitor.events.previewCount', '共 {count} 条', { count: previewItems.length })}
                      </span>
                    ) : null}
                  </div>
                  <div className={templateStyle.previewScope}>
                    <span className={templateStyle.previewScopeLabel}>
                      {t('monitor.events.instanceScope', '实例范围')}
                    </span>
                    <Tooltip title={previewScopeFull}>
                      <span className={templateStyle.previewScopeValue}>{previewScopeLabel}</span>
                    </Tooltip>
                  </div>
                </div>
                <div className={templateStyle.previewList}>
                <List
                  size="small"
                  dataSource={previewItems}
                  locale={{ emptyText: t('monitor.events.selectTemplateAndAsset', '请选择模版和资产') }}
                  renderItem={(item) => {
                    const template = templates.find((entry) => getTemplateKey(entry) === item.key);
                    return (
                      <List.Item>
                        <div className={templateStyle.previewItem}>
                          <div className={templateStyle.previewHeader}>
                            <div className={templateStyle.previewName} title={item.name}>{item.name}</div>
                            <Tag color={item.statusEnabled ? 'success' : 'default'}>
                              {item.statusLabel}
                            </Tag>
                          </div>
                          <div className={templateStyle.previewMeta}>
                            <div className={templateStyle.conditionRow}>
                              <span className={templateStyle.conditionLabel}>
                                {t('monitor.events.policyMetric', '策略指标')}：
                              </span>
                              <span className={templateStyle.conditionContent} title={item.metricLabel}>
                                {item.metricLabel}
                              </span>
                            </div>
                            {template ? <TemplateConditionSummary template={template} config={config} /> : null}
                          </div>
                        </div>
                      </List.Item>
                    );
                  }}
                />
                </div>
              </div>
            </div>
          </div>
      </div>
    </Modal>
  );
};

export default BulkApplyModal;
