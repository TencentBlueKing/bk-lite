'use client';

import React, { useState, useEffect } from 'react';
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
import { Card, Form, Spin, Modal, message } from 'antd';
import { LevelItem } from '@/app/alarm/types/index';
import { BRAND } from '@/app/alarm/constants/colors';
import NoDispatchConfigCard from './components/noDispatchConfigCard';
import LevelManagementPanel from './components/levelManagementPanel';
import LevelFormModal from './components/levelFormModal';

export default function UnallocatedNotificationConfig() {
  const { t } = useTranslation();
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
        color: row?.color || BRAND.FAIL,
        icon: row?.icon || 'huoyanhuodongtuijian',
        level_type: levelType,
        built_in: row?.built_in,
      });
    setLevelModalOpen(true);
  };

  const closeLevelModal = () => {
    setEditingLevel(null);
    setLevelModalOpen(false);
    levelForm.resetFields();
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
      okButtonProps: { danger: true },
      centered: true,
      onOk: async () => {
        await deleteLevel(row.id);
        await refreshLevels();
        message.success(t('settings.globalConfig.deleteSuccess'));
      },
    });
  };

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
          <NoDispatchConfigCard
            expanded={expanded}
            activationLoading={activationLoading}
            editMode={editMode}
            form={form}
            config={config}
            assigneeOptions={assigneeOptions}
            notifyOptions={notifyOptions}
            channelLoading={channelLoading}
            updateLoading={updateLoading}
            onToggleActivation={handleToggleActivation}
            onEnterEdit={enterEdit}
            onCancelEdit={cancelEdit}
            onConfirmEdit={confirmEdit}
          />

          <LevelManagementPanel
            levelMeta={levelMeta}
            onOpenLevelModal={openLevelModal}
            onDeleteLevel={handleDeleteLevel}
          />
        </div>
      )}

      <LevelFormModal
        open={levelModalOpen}
        form={levelForm}
        editingLevel={editingLevel}
        currentLevelType={currentLevelType}
        submitting={levelSubmitLoading}
        onCancel={closeLevelModal}
        onSubmit={submitLevel}
      />
    </Card>
  );
}
