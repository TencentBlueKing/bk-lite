'use client';

import React, { useCallback, useEffect, useState } from 'react';
import { Button, Divider, Form, Input, InputNumber, Popconfirm, Select, Space, Spin, Switch, message } from 'antd';
import {
  AimOutlined,
  BulbOutlined,
  GlobalOutlined,
  InfoCircleOutlined,
  SafetyCertificateOutlined,
  WarningOutlined,
} from '@ant-design/icons';
import { useRouter } from 'next/navigation';
import { useTranslation } from '@/utils/i18n';
import GroupTreeSelect from '@/components/group-tree-select';
import { useWikiApi } from '@/app/opspilot/api/wiki';
import { LlmModel } from '@/app/opspilot/types/skill';

type SectionKey = 'basic' | 'purpose' | 'generation' | 'websync' | 'risk' | 'danger';

// 设置工作区(spec 4.6),左侧导航 + 右侧内容布局
const SettingsTab: React.FC<{ kbId: number }> = ({ kbId }) => {
  const { t } = useTranslation();
  const router = useRouter();
  const [form] = Form.useForm();
  const { fetchKnowledgeBase, updateKnowledgeBase, fetchLlmModels, rebuildKnowledgeBase, deleteKnowledgeBase } =
    useWikiApi();
  const [llmModels, setLlmModels] = useState<LlmModel[]>([]);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [busy, setBusy] = useState(false);
  const [active, setActive] = useState<SectionKey>('basic');

  const sections: { key: SectionKey; label: string; icon: React.ReactNode; danger?: boolean }[] = [
    { key: 'basic', label: t('wiki.settingsBasic'), icon: <InfoCircleOutlined /> },
    { key: 'purpose', label: t('wiki.settingsPurposeSchema'), icon: <AimOutlined /> },
    { key: 'generation', label: t('wiki.settingsGeneration'), icon: <BulbOutlined /> },
    { key: 'websync', label: t('wiki.settingsWebSync'), icon: <GlobalOutlined /> },
    { key: 'risk', label: t('wiki.settingsRisk'), icon: <SafetyCertificateOutlined /> },
    { key: 'danger', label: t('wiki.dangerZone'), icon: <WarningOutlined />, danger: true },
  ];

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [kb, models] = await Promise.all([fetchKnowledgeBase(kbId), fetchLlmModels().catch(() => [])]);
      setLlmModels(models || []);
      const ws = (kb.web_sync_policy || {}) as Record<string, unknown>;
      const rr = (kb.risk_rules || {}) as Record<string, unknown>;
      const gr = (kb.generation_rules || {}) as Record<string, unknown>;
      form.setFieldsValue({
        name: kb.name,
        introduction: kb.introduction,
        llm_model: kb.llm_model,
        team: kb.team,
        purpose_md: kb.purpose_md,
        schema_md: kb.schema_md,
        generation_language: kb.generation_language || 'zh',
        generation_rules_notes: (gr.notes as string) || '',
        web_sync_enabled: !!ws.enabled,
        web_sync_interval_hours: (ws.interval_hours as number) ?? 24,
        risk_auto_apply: rr.auto_apply !== false,
        risk_require_review: !!rr.require_review,
      });
    } finally {
      setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [kbId]);

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [kbId]);

  const handleSave = async () => {
    const v = await form.validateFields();
    setSaving(true);
    try {
      await updateKnowledgeBase(kbId, {
        name: v.name,
        introduction: v.introduction,
        llm_model: v.llm_model,
        team: v.team,
        purpose_md: v.purpose_md,
        schema_md: v.schema_md,
        generation_language: v.generation_language,
        generation_rules: { notes: v.generation_rules_notes || '' },
        web_sync_policy: { enabled: !!v.web_sync_enabled, interval_hours: v.web_sync_interval_hours ?? 24 },
        risk_rules: { auto_apply: !!v.risk_auto_apply, require_review: !!v.risk_require_review },
      });
      message.success(t('wiki.saveSuccess'));
    } finally {
      setSaving(false);
    }
  };

  const runDanger = async (fn: () => Promise<unknown>, after?: () => void) => {
    setBusy(true);
    try {
      await fn();
      message.success(t('wiki.saveSuccess'));
      after?.();
    } finally {
      setBusy(false);
    }
  };

  const show = (key: SectionKey) => ({ display: active === key ? 'block' : 'none' });
  const title = (text: string) => <div className="text-[15px] font-medium mb-4">{text}</div>;

  return (
    <Spin spinning={loading}>
      <div className="flex gap-6">
        {/* 左侧导航 */}
        <div className="w-44 flex-shrink-0 border-r border-[var(--color-border)] pr-2">
          {sections.map((s) => {
            const on = active === s.key;
            return (
              <div
                key={s.key}
                onClick={() => setActive(s.key)}
                className={`flex items-center gap-2 px-3 py-2 mb-1 rounded-md cursor-pointer text-sm transition-colors ${
                  on
                    ? 'bg-[var(--color-primary-bg-active)] text-[var(--color-primary)] font-medium'
                    : s.danger
                      ? 'text-[var(--color-fail)] hover:bg-[var(--color-fill-2)]'
                      : 'text-[var(--color-text-2)] hover:bg-[var(--color-fill-2)]'
                }`}
              >
                {s.icon}
                {s.label}
              </div>
            );
          })}
        </div>

        {/* 右侧内容 */}
        <div className="flex-1 min-w-0">
          <Form form={form} layout="vertical" className="max-w-4xl">
            {/* 基本信息 */}
            <div style={show('basic')}>
              {title(t('wiki.settingsBasic'))}
              <div className="grid grid-cols-2 gap-x-6">
                <Form.Item label={t('wiki.name')} name="name" rules={[{ required: true }]}>
                  <Input />
                </Form.Item>
                <Form.Item
                  label={t('wiki.llmModel')}
                  name="llm_model"
                  rules={[{ required: true }]}
                  tooltip={t('wiki.llmModelTip')}
                >
                  <Select
                    placeholder={t('wiki.llmModelPlaceholder')}
                    options={llmModels.map((m) => ({ value: m.id, label: m.name, disabled: !m.enabled }))}
                  />
                </Form.Item>
                <Form.Item className="col-span-2" label={t('wiki.introduction')} name="introduction">
                  <Input.TextArea rows={2} />
                </Form.Item>
                <Form.Item className="col-span-2" label={t('common.organization')} name="team" rules={[{ required: true }]}>
                  <GroupTreeSelect placeholder={`${t('common.selectMsg')}${t('common.organization')}`} />
                </Form.Item>
              </div>
            </div>

            {/* 用途与结构 */}
            <div style={show('purpose')}>
              {title(t('wiki.settingsPurposeSchema'))}
              <Form.Item label={t('wiki.purpose')} name="purpose_md">
                <Input.TextArea rows={6} />
              </Form.Item>
              <Form.Item label={t('wiki.schema')} name="schema_md">
                <Input.TextArea rows={6} />
              </Form.Item>
            </div>

            {/* 生成设置 */}
            <div style={show('generation')}>
              {title(t('wiki.settingsGeneration'))}
              <Form.Item label={t('wiki.generationLanguage')} name="generation_language" className="max-w-xs">
                <Select
                  options={[
                    { value: 'zh', label: '中文' },
                    { value: 'en', label: 'English' },
                  ]}
                />
              </Form.Item>
              <Form.Item label={t('wiki.generationRules')} name="generation_rules_notes" tooltip={t('wiki.generationRulesTip')}>
                <Input.TextArea rows={4} placeholder={t('wiki.generationRulesPlaceholder')} />
              </Form.Item>
            </div>

            {/* 网页同步 */}
            <div style={show('websync')}>
              {title(t('wiki.settingsWebSync'))}
              <Form.Item label={t('wiki.webSyncEnabled')} name="web_sync_enabled" valuePropName="checked" tooltip={t('wiki.webSyncTip')}>
                <Switch />
              </Form.Item>
              <Form.Item label={t('wiki.webSyncInterval')} name="web_sync_interval_hours">
                <InputNumber min={1} max={720} addonAfter={t('wiki.hours')} />
              </Form.Item>
            </div>

            {/* 风险与审核 */}
            <div style={show('risk')}>
              {title(t('wiki.settingsRisk'))}
              <Form.Item label={t('wiki.riskAutoApply')} name="risk_auto_apply" valuePropName="checked" tooltip={t('wiki.riskAutoApplyTip')}>
                <Switch />
              </Form.Item>
              <Form.Item label={t('wiki.riskRequireReview')} name="risk_require_review" valuePropName="checked" tooltip={t('wiki.riskRequireReviewTip')}>
                <Switch />
              </Form.Item>
            </div>
          </Form>

          {active !== 'danger' && (
            <Button type="primary" loading={saving} onClick={handleSave}>
              {t('common.save')}
            </Button>
          )}

          {/* 危险操作 */}
          <div style={show('danger')} className="max-w-2xl">
            {title(t('wiki.dangerZone'))}
            <Space direction="vertical" className="w-full" size="middle">
              <div className="flex items-center justify-between">
                <span className="text-[var(--color-text-3)] text-sm">{t('wiki.rebuildAllTip')}</span>
                <Popconfirm title={t('wiki.rebuildAllConfirm')} onConfirm={() => runDanger(() => rebuildKnowledgeBase(kbId))}>
                  <Button loading={busy}>{t('wiki.rebuildAll')}</Button>
                </Popconfirm>
              </div>
              <Divider className="my-1" />
              <div className="flex items-center justify-between">
                <span className="text-[var(--color-text-3)] text-sm">{t('wiki.archiveTip')}</span>
                <Popconfirm title={t('wiki.archiveConfirm')} onConfirm={() => runDanger(() => updateKnowledgeBase(kbId, { status: 'archived' }))}>
                  <Button loading={busy}>{t('wiki.archive')}</Button>
                </Popconfirm>
              </div>
              <Divider className="my-1" />
              <div className="flex items-center justify-between">
                <span className="text-[var(--color-text-3)] text-sm">{t('wiki.deleteTip')}</span>
                <Popconfirm
                  title={t('wiki.deleteConfirm')}
                  okButtonProps={{ danger: true }}
                  onConfirm={() => runDanger(() => deleteKnowledgeBase(kbId), () => router.push('/opspilot/wiki'))}
                >
                  <Button danger loading={busy}>
                    {t('common.delete')}
                  </Button>
                </Popconfirm>
              </div>
            </Space>
          </div>
        </div>
      </div>
    </Spin>
  );
};

export default SettingsTab;
