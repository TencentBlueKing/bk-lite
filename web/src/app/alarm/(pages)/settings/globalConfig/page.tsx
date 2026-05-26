'use client';

import React, { useState, useEffect } from 'react';
import PermissionWrapper from '@/components/permission';
import { useSettingApi } from '@/app/alarm/api/settings';
import { useCommon } from '@/app/alarm/context/common';
import { useTranslation } from '@/utils/i18n';
import {
  Config,
  GlobalConfig,
  ChannelItem,
  NotifyOption,
  LevelFormItem,
} from '@/app/alarm/types/settings';
import {
  DEFAULT_LEVEL_COLORS,
  DEFAULT_LEVEL_ICONS,
  renderLevelIconOption,
} from '@/app/alarm/constants/level';
import LevelIcon from '@/app/alarm/components/levelIcon';
import {
  Card,
  Typography,
  Grid,
  Form,
  InputNumber,
  Select,
  ColorPicker,
  Checkbox,
  Button,
  Space,
  Segmented,
  Switch,
  Spin,
  Row,
  Col,
  Table,
  Modal,
  Input,
  Upload,
  Tag,
  message,
} from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { CheckOutlined, PlusOutlined, UploadOutlined } from '@ant-design/icons';
import { LevelItem } from '@/app/alarm/types/index';

const LEVEL_TYPE_ACCENT: Record<'event' | 'alert' | 'incident', string> = {
  event: '#2F6BFF',
  alert: '#FFAD42',
  incident: '#7A45FF',
};

const isCustomIconValue = (icon?: string) => !!icon?.startsWith('data:image/');

const getLevelTagStyle = (color?: string, compact?: boolean) => ({
  backgroundColor: color || '#FFAD42',
  color: '#fff',
  border: 'none',
  borderRadius: compact ? 7 : 8,
  display: 'inline-flex',
  alignItems: 'center',
  gap: compact ? 2 : 4,
  paddingInline: compact ? 5 : 7,
  paddingBlock: compact ? 2 : 3,
  marginInlineEnd: 0,
  fontSize: compact ? 11 : 12,
  lineHeight: 1.4,
  maxWidth: '100%',
});

export default function UnallocatedNotificationConfig() {
  const { t } = useTranslation();
  const screens = Grid.useBreakpoint();
  const { userList, levelMeta, refreshLevels } = useCommon();
  const [editMode, setEditMode] = useState(false);
  const [expanded, setExpanded] = useState(true);
  const [form] = Form.useForm<Config>();
  const [levelForm] = Form.useForm<LevelFormItem>();
  const [loading, setLoading] = useState(false);
  const [activationLoading, setActivationLoading] = useState(false);
  const [globalConfigId, setGlobalConfigId] = useState<string | number>('');
  const [updateLoading, setUpdateLoading] = useState(false);
  const [levelModalOpen, setLevelModalOpen] = useState(false);
  const [levelSubmitLoading, setLevelSubmitLoading] = useState(false);
  const [editingLevel, setEditingLevel] = useState<LevelItem | null>(null);
  const [iconMode, setIconMode] = useState<'preset' | 'upload'>('preset');
  const [currentLevelType, setCurrentLevelType] = useState<
    'event' | 'alert' | 'incident'
  >('event');
  const [notifyOptions, setNotifyOptions] = useState<NotifyOption[]>([]);
  const [channelList, setChannelList] = useState<ChannelItem[]>([]);
  const [channelLoading, setChannelLoading] = useState(false);
  const {
    getGlobalConfig,
    updateGlobalConfig,
    toggleGlobalConfig,
    getChannelList,
    createLevel,
    updateLevel,
    deleteLevel,
  } = useSettingApi();
  const [config, setConfig] = useState<Config>({
    notify_every: 60,
    notify_people: [],
    notify_channel: [],
  });

  const assigneeOptions = userList.map((u) => ({
    label: `${u.display_name} (${u.username})`,
    value: u.username,
  }));

  // 获取通知渠道列表
  const fetchChannelList = async () => {
    setChannelLoading(true);
    try {
      const data: any = await getChannelList({});
      setChannelList(data);
      const options: NotifyOption[] = data.map((channel: ChannelItem) => ({
        label: channel.name,
        value: channel.id.toString(),
      }));
      setNotifyOptions(options);
    } catch (error) {
      console.error('获取通知渠道失败:', error);
    } finally {
      setChannelLoading(false);
    }
  };

  useEffect(() => {
    form.setFieldsValue(config);
  }, [form, config]);

  useEffect(() => {
    const loadGlobalConfig = async () => {
      setLoading(true);
      try {
        const res: GlobalConfig = await getGlobalConfig(
          'no_dispatch_alert_notice',
        );
        const { notify_channel, notify_every, notify_people } = res.value;

        const notifyChannelIds = (notify_channel || []).map((ch: any) =>
          ch.id.toString(),
        );

        form.setFieldsValue({
          notify_channel: notifyChannelIds,
          notify_every,
          notify_people,
        });
        setConfig({
          notify_channel: notifyChannelIds,
          notify_every,
          notify_people,
        });
        setExpanded(res.is_activate ?? false);
        setGlobalConfigId(res.id);
      } catch (error) {
        console.error('加载全局配置失败', error);
      } finally {
        setLoading(false);
      }
    };

    // 获取通知渠道列表
    fetchChannelList();
    loadGlobalConfig();
  }, []);

  const enterEdit = () => {
    setEditMode(true);
  };

  const cancelEdit = () => {
    form.setFieldsValue(config);
    setEditMode(false);
  };

  const confirmEdit = async () => {
    setUpdateLoading(true);
    try {
      const values = await form.validateFields();

      const notifyChannels = (values.notify_channel || [])
        .map((id: string) => channelList.find((ch) => ch.id.toString() === id))
        .filter(Boolean);

      await updateGlobalConfig(globalConfigId, {
        key: 'no_dispatch_alert_notice',
        is_activate: true,
        value: {
          notify_channel: notifyChannels,
          notify_every: values.notify_every,
          notify_people: values.notify_people,
        },
      });
      setConfig(values);
      setEditMode(false);
    } catch (error) {
      console.error('更新配置失败', error);
    } finally {
      setUpdateLoading(false);
    }
  };

  const handleToggleActivation = async (checked: boolean) => {
    setActivationLoading(true);
    try {
      await toggleGlobalConfig(globalConfigId, { is_activate: checked });
      setExpanded(checked);
    } catch (error) {
      console.error('切换激活状态失败', error);
    } finally {
      setActivationLoading(false);
    }
  };

  const levelTypeTitles: Record<'event' | 'alert' | 'incident', string> = {
    event: t('settings.globalConfig.eventLevel'),
    alert: t('settings.globalConfig.alertLevel'),
    incident: t('settings.globalConfig.incidentLevel'),
  };
  const addLevelButtonText = t('settings.globalConfig.addLevel')
    .replace(/\s*等级$/u, '')
    .replace(/\s+levels?$/iu, '')
    .trim();
  const isCompactLevelView = !screens.md || !!screens.xl;
  const levelNameTextMaxWidth = isCompactLevelView ? 78 : 126;
  const isCompactModalForm = !screens.sm;

  const openLevelModal = (
    levelType: 'event' | 'alert' | 'incident',
    row?: LevelItem,
  ) => {
    setCurrentLevelType(levelType);
    setEditingLevel(row || null);
    const list = levelMeta[levelType]?.list || [];
    const nextId = list.length
      ? Math.max(...list.map((item) => item.level_id)) + 1
      : 0;
    levelForm.setFieldsValue({
      level_id: row?.level_id ?? nextId,
      level_display_name: row?.level_display_name ?? '',
      color: row?.color || DEFAULT_LEVEL_COLORS[0],
      icon: row?.icon || DEFAULT_LEVEL_ICONS[0],
      level_type: levelType,
      built_in: row?.built_in,
    });
    setIconMode(isCustomIconValue(row?.icon) ? 'upload' : 'preset');
    setLevelModalOpen(true);
  };

  const closeLevelModal = () => {
    setEditingLevel(null);
    setIconMode('preset');
    setLevelModalOpen(false);
    levelForm.resetFields();
  };

  const beforeIconUpload = async (file: File) => {
    const isAllowed = [
      'image/png',
      'image/jpeg',
      'image/jpg',
      'image/svg+xml',
    ].includes(file.type);
    if (!isAllowed) {
      message.error(t('settings.globalConfig.uploadTip'));
      return Upload.LIST_IGNORE;
    }

    const isLt200Kb = file.size / 1024 <= 200;
    if (!isLt200Kb) {
      message.error(t('settings.globalConfig.uploadTip'));
      return Upload.LIST_IGNORE;
    }

    const dataUrl = await new Promise<string>((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(String(reader.result || ''));
      reader.onerror = () => reject(new Error('read-failed'));
      reader.readAsDataURL(file);
    });
    levelForm.setFieldValue('icon', dataUrl);
    setIconMode('upload');
    return Upload.LIST_IGNORE;
  };

  const handleIconModeChange = (nextMode: 'preset' | 'upload') => {
    setIconMode(nextMode);
    const currentIcon = levelForm.getFieldValue('icon');

    if (nextMode === 'preset') {
      if (!currentIcon || isCustomIconValue(currentIcon)) {
        levelForm.setFieldValue('icon', DEFAULT_LEVEL_ICONS[0]);
      }
      return;
    }

    if (!isCustomIconValue(currentIcon)) {
      levelForm.setFieldValue('icon', '');
    }
  };

  const submitLevel = async () => {
    setLevelSubmitLoading(true);
    try {
      const values = await levelForm.validateFields();
      const payload = {
        level_id: values.level_id,
        level_display_name: values.level_display_name,
        color: values.color,
        icon: values.icon,
        level_name: editingLevel?.level_name || values.level_display_name,
        level_type: currentLevelType,
        built_in: editingLevel?.built_in ?? false,
      };
      if (editingLevel?.id) {
        await updateLevel(editingLevel.id, payload);
      } else {
        await createLevel(payload);
      }
      await refreshLevels();
      message.success(t('settings.globalConfig.saveSuccess'));
      closeLevelModal();
    } catch (error) {
      console.error('save level failed', error);
    } finally {
      setLevelSubmitLoading(false);
    }
  };

  const handleDeleteLevel = (row: LevelItem) => {
    Modal.confirm({
      title: t('common.delConfirm'),
      content: t('common.delConfirmCxt'),
      okText: t('common.confirm'),
      cancelText: t('common.cancel'),
      centered: true,
      onOk: async () => {
        await deleteLevel(row.id);
        await refreshLevels();
        message.success(t('settings.globalConfig.deleteSuccess'));
      },
    });
  };

  const levelColumns: ColumnsType<LevelItem> = [
    {
      title: t('settings.globalConfig.levelId'),
      dataIndex: 'level_id',
      key: 'level_id',
      width: isCompactLevelView ? 64 : 84,
      align: 'center',
    },
    {
      title: t('settings.globalConfig.levelDisplayEffect'),
      dataIndex: 'level_display_name',
      key: 'level_display_name',
      width: isCompactLevelView ? 140 : 228,
      render: (_value, record) => (
        <Tag style={getLevelTagStyle(record.color, isCompactLevelView)}>
          <span
            className={
              isCompactLevelView
                ? 'flex h-3 w-3 shrink-0 items-center justify-center leading-none'
                : 'flex h-3.5 w-3.5 shrink-0 items-center justify-center leading-none'
            }
          >
            <LevelIcon
              icon={record.icon}
              className={isCompactLevelView ? 'h-3 w-3' : 'h-3.5 w-3.5'}
              style={{ color: '#fff', lineHeight: 1 }}
            />
          </span>
          <span
            className="truncate"
            style={{ maxWidth: levelNameTextMaxWidth }}
            title={record.level_display_name}
          >
            {record.level_display_name}
          </span>
        </Tag>
      ),
    },
    {
      title: t('settings.globalConfig.levelActions'),
      key: 'actions',
      width: isCompactLevelView ? 98 : 124,
      render: (_value, record) => (
        <Space size={isCompactLevelView ? 8 : 10}>
          <PermissionWrapper requiredPermissions={['Edit']}>
            <Button
              type="link"
              size="small"
              className="px-0 text-[#2F6BFF]"
              onClick={() =>
                openLevelModal(
                  record.level_type as 'event' | 'alert' | 'incident',
                  record,
                )
              }
            >
              {t('common.edit')}
            </Button>
          </PermissionWrapper>
          <PermissionWrapper requiredPermissions={['Edit']}>
            <Button
              type="link"
              size="small"
              className="px-0 text-[#2F6BFF]"
              onClick={() => handleDeleteLevel(record)}
            >
              {t('common.delete')}
            </Button>
          </PermissionWrapper>
        </Space>
      ),
    },
  ];

  const levelCards = (['event', 'alert', 'incident'] as const).map(
    (levelType) => {
      const group = levelMeta[levelType];
      return (
        <Col xs={24} lg={12} xl={8} key={levelType} className="flex">
          <div className="flex h-full flex-col overflow-hidden rounded-2xl border border-(--color-border-1) bg-(--color-bg-1)">
            <div
              className="flex items-center justify-between border-b border-(--color-border-1) px-2.5 py-1.5 sm:px-3 sm:py-2"
              style={{
                background:
                  'color-mix(in srgb, var(--color-fill-1) 58%, white)',
              }}
            >
              <div className="flex items-center gap-2">
                <span
                  className="inline-block h-2 w-2 rounded-full"
                  style={{ backgroundColor: LEVEL_TYPE_ACCENT[levelType] }}
                />
                <span className="text-[14px] font-medium text-(--color-text-1) sm:text-[15px]">
                  {levelTypeTitles[levelType]}
                </span>
              </div>
              <PermissionWrapper requiredPermissions={['Edit']}>
                <Button
                  type="link"
                  size="small"
                  className="px-0"
                  onClick={() => openLevelModal(levelType)}
                >
                  <span className="inline-flex items-center gap-0.5">
                    <PlusOutlined className="text-[10px]" />
                    <span>{addLevelButtonText}</span>
                  </span>
                </Button>
              </PermissionWrapper>
            </div>
            <div className="px-2.5 py-1.5 sm:px-3 sm:py-2">
              <Table
                className="level-table-clean"
                rowKey="id"
                size="small"
                pagination={false}
                tableLayout="fixed"
                sticky
                scroll={{ y: 280 }}
                columns={levelColumns}
                dataSource={group?.list || []}
              />
            </div>
          </div>
        </Col>
      );
    },
  );

  return (
    <Card style={{ height: '100%' }}>
      <style jsx global>{`
        .level-table-clean .ant-table,
        .level-table-clean .ant-table-container {
          background: transparent;
        }

        .compact-config-form .ant-form-item {
          margin-bottom: 18px;
        }

        .compact-config-form .ant-checkbox-group {
          display: flex;
          flex-direction: column;
          gap: 4px;
        }

        .level-table-clean .ant-table-thead > tr > th {
          background: color-mix(in srgb, var(--color-fill-1) 34%, white);
          color: var(--color-text-2);
          font-weight: 500;
          border-bottom: 1px solid var(--color-border-1);
          padding-top: 6px;
          padding-bottom: 6px;
          font-size: 12px;
        }

        .level-table-clean .ant-table-tbody > tr > td {
          border-bottom: 1px solid
            color-mix(in srgb, var(--color-border-1) 70%, transparent);
          padding-top: 6px;
          padding-bottom: 6px;
          font-size: 12px;
        }

        .level-table-clean .ant-table-tbody > tr:last-child > td {
          border-bottom: none;
        }

        .level-table-clean .ant-table-cell::before {
          display: none !important;
        }
      `}</style>
      {loading ? (
        <div className="flex justify-center pt-[20px] mt-[20vh]">
          <Spin spinning={loading} />
        </div>
      ) : (
        <div className="h-full">
          <div className="rounded-2xl border border-(--color-border-1) bg-(--color-bg-1) p-3 pb-1 sm:p-3.5 sm:pb-1.5">
            <div className="mb-2.5 flex items-center gap-3">
              <div className="flex items-center gap-2">
                <span className="inline-block h-4 w-1 rounded-full bg-[#2F6BFF]" />
                <Typography.Title
                  level={4}
                  style={{ margin: 0, fontSize: '15px' }}
                >
                  {t('settings.globalConfig.title')}
                </Typography.Title>
              </div>
              <Switch
                size="small"
                checked={expanded}
                loading={activationLoading}
                onChange={(checked) => handleToggleActivation(checked)}
              />
            </div>
            {expanded && (
              <div className="max-w-[640px]">
                <div className="mb-2.5 pl-3 text-[12px] leading-5 text-(--color-text-3)">
                  {t('settings.globalConfig.description')}
                </div>
                <Form
                  form={form}
                  className="compact-config-form"
                  layout="horizontal"
                  initialValues={config}
                  labelCol={{ flex: '108px' }}
                  wrapperCol={{ flex: '1' }}
                  style={{ maxWidth: 500 }}
                >
                  <Form.Item
                    name="notify_every"
                    label={t('settings.globalConfig.intervalLabel')}
                    rules={[
                      {
                        required: true,
                        message:
                          t('common.inputTip') +
                          t('settings.globalConfig.intervalLabel'),
                      },
                    ]}
                  >
                    <InputNumber
                      min={1}
                      addonAfter={t('settings.globalConfig.intervalMinutes')}
                      disabled={!editMode}
                      style={{ width: '160px' }}
                    />
                  </Form.Item>

                  <Form.Item
                    name="notify_people"
                    label={t('settings.globalConfig.personnelLabel')}
                    rules={[
                      {
                        required: true,
                        message:
                          t('common.selectTip') +
                          t('settings.globalConfig.personnelLabel'),
                      },
                    ]}
                  >
                    <Select
                      mode="multiple"
                      showSearch
                      allowClear
                      options={assigneeOptions}
                      disabled={!editMode}
                      placeholder={t(
                        'settings.globalConfig.personnelPlaceholder',
                      )}
                      filterOption={(input: string, option?: any) =>
                        !!option?.label
                          ?.toLowerCase()
                          .includes(input.toLowerCase())
                      }
                    />
                  </Form.Item>

                  <Form.Item
                    name="notify_channel"
                    className="mb-2"
                    label={t('settings.globalConfig.notificationMethodLabel')}
                    rules={[
                      {
                        required: true,
                        message:
                          t('common.selectTip') +
                          t('settings.globalConfig.notificationMethodLabel'),
                      },
                    ]}
                  >
                    <Checkbox.Group
                      options={notifyOptions}
                      disabled={!editMode || channelLoading}
                    />
                    {channelLoading && (
                      <div className="mt-2 flex h-8 justify-center">
                        <Spin spinning={channelLoading} />
                      </div>
                    )}
                  </Form.Item>

                  <Form.Item className="mb-0 ml-3">
                    <Space>
                      {editMode ? (
                        <>
                          <Button
                            type="primary"
                            size="small"
                            onClick={confirmEdit}
                            loading={updateLoading}
                          >
                            {t('common.confirm')}
                          </Button>
                          <Button size="small" onClick={cancelEdit}>
                            {t('common.cancel')}
                          </Button>
                        </>
                      ) : (
                        <PermissionWrapper requiredPermissions={['Edit']}>
                          <Button
                            type="primary"
                            size="small"
                            className="px-2"
                            onClick={enterEdit}
                          >
                            {t('common.edit')}
                          </Button>
                        </PermissionWrapper>
                      )}
                    </Space>
                  </Form.Item>
                </Form>
              </div>
            )}
          </div>

          <div className="mt-4 rounded-2xl border border-(--color-border-1) bg-(--color-bg-1) p-3 sm:p-3.5">
            <div className="mb-3">
              <div className="flex items-center gap-2">
                <span className="inline-block h-4 w-1 rounded-full bg-[#2F6BFF]" />
                <Typography.Title
                  level={4}
                  style={{ margin: 0, fontSize: '15px' }}
                >
                  {t('settings.globalConfig.levelPanelTitle')}
                </Typography.Title>
              </div>
              <div className="mt-1 pl-3 text-[12px] leading-5 text-(--color-text-3)">
                {t('settings.globalConfig.levelPanelDescription')}
              </div>
            </div>
            <div className="overflow-hidden">
              <Row gutter={[24, 24]} align="stretch">
                {levelCards}
              </Row>
            </div>
          </div>
        </div>
      )}

      <Modal
        title={
          editingLevel
            ? t('settings.globalConfig.editLevelTitle')
            : t('settings.globalConfig.addLevelTitle')
        }
        width={580}
        centered
        open={levelModalOpen}
        onCancel={closeLevelModal}
        onOk={submitLevel}
        confirmLoading={levelSubmitLoading}
        styles={{ body: { paddingTop: 20, paddingBottom: 20 } }}
        destroyOnHidden
      >
        <Form
          form={levelForm}
          layout={isCompactModalForm ? 'vertical' : 'horizontal'}
          labelCol={isCompactModalForm ? undefined : { flex: '90px' }}
          wrapperCol={isCompactModalForm ? undefined : { flex: 'auto' }}
          labelAlign="right"
          style={{ marginTop: 4 }}
        >
          <Form.Item
            name="level_id"
            label={t('settings.globalConfig.levelId')}
            style={{ marginBottom: 24 }}
            rules={[
              {
                required: true,
                message: t('settings.globalConfig.nonNegativeInteger'),
              },
              {
                validator: async (_, value) => {
                  if (value === undefined || value === null || value === '') {
                    return;
                  }
                  if (
                    Number.isNaN(Number(value)) ||
                    Number(value) < 0 ||
                    !Number.isInteger(Number(value))
                  ) {
                    throw new Error(
                      t('settings.globalConfig.nonNegativeInteger'),
                    );
                  }
                },
              },
            ]}
          >
            <InputNumber
              min={0}
              precision={0}
              style={{ width: '100%' }}
              disabled={!!editingLevel}
            />
          </Form.Item>
          <Form.Item
            name="level_display_name"
            label={t('settings.globalConfig.levelName')}
            style={{ marginBottom: 24 }}
            rules={[
              {
                required: true,
                message:
                  t('common.inputTip') + t('settings.globalConfig.levelName'),
              },
            ]}
          >
            <Input maxLength={32} />
          </Form.Item>
          <Form.Item
            name="color"
            rules={[
              {
                required: true,
                message:
                  t('common.selectTip') + t('settings.globalConfig.levelColor'),
              },
            ]}
            hidden
          >
            <Input />
          </Form.Item>
          <Form.Item
            required
            label={t('settings.globalConfig.levelColor')}
            style={{ marginBottom: 24 }}
          >
            <Form.Item shouldUpdate noStyle>
              {() => {
                const selectedColor =
                  levelForm.getFieldValue('color') || DEFAULT_LEVEL_COLORS[0];
                return (
                  <div className="flex items-center gap-2">
                    <Select
                      value={selectedColor}
                      className="flex-1"
                      onChange={(value) =>
                        levelForm.setFieldValue('color', value)
                      }
                      options={DEFAULT_LEVEL_COLORS.map((color) => ({
                        value: color,
                        label: (
                          <div className="flex items-center gap-2">
                            <span
                              className="inline-block h-4 w-4 rounded-full border border-[#E5E7EB]"
                              style={{ backgroundColor: color }}
                            />
                            <span>{color}</span>
                          </div>
                        ),
                      }))}
                    />
                    <ColorPicker
                      value={selectedColor}
                      presets={[
                        {
                          label: t('settings.globalConfig.levelColor'),
                          colors: DEFAULT_LEVEL_COLORS,
                        },
                      ]}
                      onChange={(color) =>
                        levelForm.setFieldValue(
                          'color',
                          color.toHexString().toUpperCase(),
                        )
                      }
                    />
                  </div>
                );
              }}
            </Form.Item>
          </Form.Item>
          <Form.Item
            label={t('settings.globalConfig.levelIcon')}
            required
            style={{ marginBottom: 0 }}
            className="align-top"
          >
            <Form.Item
              name="icon"
              rules={[
                {
                  required: true,
                  message: t('settings.globalConfig.iconRequired'),
                },
              ]}
              noStyle
            >
              <input type="hidden" />
            </Form.Item>
            <div className="w-full">
              <div className="mb-6 flex items-start">
                <Segmented
                  size="middle"
                  className="h-9 items-center"
                  style={{ alignSelf: 'flex-start' }}
                  value={iconMode}
                  onChange={(value) =>
                    handleIconModeChange(value as 'preset' | 'upload')
                  }
                  options={[
                    {
                      label: t('settings.globalConfig.defaultIcons'),
                      value: 'preset',
                    },
                    {
                      label: t('settings.globalConfig.customUpload'),
                      value: 'upload',
                    },
                  ]}
                />
              </div>
              {iconMode === 'preset' ? (
                <Form.Item shouldUpdate noStyle>
                  {() => {
                    const selectedIcon = levelForm.getFieldValue('icon');
                    const selectedColor = levelForm.getFieldValue('color');
                    return (
                      <div className="grid grid-cols-5 gap-3">
                        {DEFAULT_LEVEL_ICONS.map((icon) => {
                          const isActive = selectedIcon === icon;
                          return (
                            <button
                              key={icon}
                              type="button"
                              className={`relative flex h-12 cursor-pointer items-center justify-center rounded-xl border transition-all ${
                                isActive
                                  ? 'border-[#BFD3FF] bg-[#F7FAFF]'
                                  : 'border-(--color-border-1) bg-white hover:border-[#9DBBFF] hover:bg-[#FAFBFF]'
                              }`}
                              onClick={() =>
                                levelForm.setFieldValue('icon', icon)
                              }
                            >
                              {isActive && (
                                <span className="absolute -top-1 -right-1 flex h-4 w-4 items-center justify-center rounded-full bg-[#2F6BFF] text-white shadow-sm ring-2 ring-white">
                                  <CheckOutlined className="text-[9px]" />
                                </span>
                              )}
                              {renderLevelIconOption(icon, selectedColor)}
                            </button>
                          );
                        })}
                      </div>
                    );
                  }}
                </Form.Item>
              ) : (
                <div>
                  <Upload
                    showUploadList={false}
                    beforeUpload={(file) => beforeIconUpload(file as File)}
                  >
                    <Button icon={<UploadOutlined />}>
                      {t('settings.globalConfig.uploadIcon')}
                    </Button>
                  </Upload>
                  <div className="mt-4 text-[12px] text-[var(--color-text-3)]">
                    {t('settings.globalConfig.uploadTip')}
                  </div>
                  <Form.Item shouldUpdate noStyle>
                    {() => {
                      const icon = levelForm.getFieldValue('icon');
                      const selectedColor =
                        levelForm.getFieldValue('color') ||
                        DEFAULT_LEVEL_COLORS[0];
                      return isCustomIconValue(icon) ? (
                        <div className="mt-4">
                          <div
                            className="inline-flex h-12 min-w-12 items-center justify-center rounded-xl border border-[#BFD3FF] bg-[#F7FAFF] px-4"
                            style={{
                              borderColor:
                                'color-mix(in srgb, var(--color-primary) 22%, white)',
                            }}
                          >
                            <span
                              className="flex h-7 w-7 items-center justify-center rounded-md"
                              style={{ backgroundColor: selectedColor }}
                            >
                              <LevelIcon
                                icon={icon}
                                className="h-4 w-4"
                                style={{ color: '#fff' }}
                              />
                            </span>
                          </div>
                        </div>
                      ) : null;
                    }}
                  </Form.Item>
                </div>
              )}
            </div>
          </Form.Item>
        </Form>
      </Modal>
    </Card>
  );
}
