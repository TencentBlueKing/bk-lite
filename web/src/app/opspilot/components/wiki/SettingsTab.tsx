'use client';

import React, { useCallback, useEffect, useState } from 'react';
import { Button, Card, Divider, Form, Input, InputNumber, Popconfirm, Select, Space, Spin, Switch, message } from 'antd';
import { useRouter } from 'next/navigation';
import { useTranslation } from '@/utils/i18n';
import GroupTreeSelect from '@/components/group-tree-select';
import { useWikiApi } from '@/app/opspilot/api/wiki';
import { LlmModel } from '@/app/opspilot/types/skill';

// 设置工作区(spec 4.6):用途/结构、AI 模型、生成语言+规则、网页同步策略、风险审核规则、团队、危险操作
const SettingsTab: React.FC<{ kbId: number }> = ({ kbId }) => {
  const { t } = useTranslation();
  const router = useRouter();
  const [form] = Form.useForm();
  const { fetchKnowledgeBase, updateKnowledgeBase, fetchLlmModels, rebuildKnowledgeBase, deleteKnowledgeBase } =
    useWikiApi();
  const [llmModels, setLlmModels] = useState<LlmModel[]>([]);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [busy, setBusy] = useState(false); // 危险操作进行中

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
        risk_auto_apply: rr.auto_apply !== false, // 默认自动生效
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

  const handleRebuild = async () => {
    setBusy(true);
    try {
      await rebuildKnowledgeBase(kbId);
      message.success(t('wiki.saveSuccess'));
    } finally {
      setBusy(false);
    }
  };

  const handleArchive = async () => {
    setBusy(true);
    try {
      await updateKnowledgeBase(kbId, { status: 'archived' });
      message.success(t('wiki.saveSuccess'));
    } finally {
      setBusy(false);
    }
  };

  const handleDelete = async () => {
    setBusy(true);
    try {
      await deleteKnowledgeBase(kbId);
      message.success(t('wiki.deleteSuccess'));
      router.push('/opspilot/wiki');
    } finally {
      setBusy(false);
    }
  };

  return (
    <Spin spinning={loading}>
      <Form form={form} layout="vertical" className="max-w-3xl">
        {/* 基本 + 模型 */}
        <Card size="small" title={t('wiki.settingsBasic')} className="mb-4">
          <Form.Item label={t('wiki.name')} name="name" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item label={t('wiki.introduction')} name="introduction">
            <Input.TextArea rows={2} />
          </Form.Item>
          <Form.Item label={t('wiki.llmModel')} name="llm_model" rules={[{ required: true }]} tooltip={t('wiki.llmModelTip')}>
            <Select
              placeholder={t('wiki.llmModelPlaceholder')}
              options={llmModels.map((m) => ({ value: m.id, label: m.name, disabled: !m.enabled }))}
            />
          </Form.Item>
          <Form.Item label={t('common.organization')} name="team" rules={[{ required: true }]}>
            <GroupTreeSelect placeholder={`${t('common.selectMsg')}${t('common.organization')}`} />
          </Form.Item>
        </Card>

        {/* 用途 / 结构 */}
        <Card size="small" title={t('wiki.settingsPurposeSchema')} className="mb-4">
          <Form.Item label={t('wiki.purpose')} name="purpose_md">
            <Input.TextArea rows={4} />
          </Form.Item>
          <Form.Item label={t('wiki.schema')} name="schema_md">
            <Input.TextArea rows={4} />
          </Form.Item>
        </Card>

        {/* 生成语言 + 规则 */}
        <Card size="small" title={t('wiki.settingsGeneration')} className="mb-4">
          <Form.Item label={t('wiki.generationLanguage')} name="generation_language">
            <Select
              options={[
                { value: 'zh', label: '中文' },
                { value: 'en', label: 'English' },
              ]}
            />
          </Form.Item>
          <Form.Item label={t('wiki.generationRules')} name="generation_rules_notes" tooltip={t('wiki.generationRulesTip')}>
            <Input.TextArea rows={3} placeholder={t('wiki.generationRulesPlaceholder')} />
          </Form.Item>
        </Card>

        {/* 网页同步策略 */}
        <Card size="small" title={t('wiki.settingsWebSync')} className="mb-4">
          <Form.Item label={t('wiki.webSyncEnabled')} name="web_sync_enabled" valuePropName="checked" tooltip={t('wiki.webSyncTip')}>
            <Switch />
          </Form.Item>
          <Form.Item label={t('wiki.webSyncInterval')} name="web_sync_interval_hours">
            <InputNumber min={1} max={720} addonAfter={t('wiki.hours')} />
          </Form.Item>
        </Card>

        {/* 自动生效 + 风险审核规则 */}
        <Card size="small" title={t('wiki.settingsRisk')} className="mb-4">
          <Form.Item label={t('wiki.riskAutoApply')} name="risk_auto_apply" valuePropName="checked" tooltip={t('wiki.riskAutoApplyTip')}>
            <Switch />
          </Form.Item>
          <Form.Item label={t('wiki.riskRequireReview')} name="risk_require_review" valuePropName="checked" tooltip={t('wiki.riskRequireReviewTip')}>
            <Switch />
          </Form.Item>
        </Card>

        <div className="mb-6">
          <Button type="primary" loading={saving} onClick={handleSave}>
            {t('common.save')}
          </Button>
        </div>

        {/* 危险操作 */}
        <Card size="small" title={<span className="text-[var(--color-fail)]">{t('wiki.dangerZone')}</span>}>
          <Space direction="vertical" className="w-full" size="middle">
            <div className="flex items-center justify-between">
              <span>{t('wiki.rebuildAllTip')}</span>
              <Popconfirm title={t('wiki.rebuildAllConfirm')} onConfirm={handleRebuild}>
                <Button loading={busy}>{t('wiki.rebuildAll')}</Button>
              </Popconfirm>
            </div>
            <Divider className="my-1" />
            <div className="flex items-center justify-between">
              <span>{t('wiki.archiveTip')}</span>
              <Popconfirm title={t('wiki.archiveConfirm')} onConfirm={handleArchive}>
                <Button loading={busy}>{t('wiki.archive')}</Button>
              </Popconfirm>
            </div>
            <Divider className="my-1" />
            <div className="flex items-center justify-between">
              <span>{t('wiki.deleteTip')}</span>
              <Popconfirm title={t('wiki.deleteConfirm')} okButtonProps={{ danger: true }} onConfirm={handleDelete}>
                <Button danger loading={busy}>
                  {t('common.delete')}
                </Button>
              </Popconfirm>
            </div>
          </Space>
        </Card>
      </Form>
    </Spin>
  );
};

export default SettingsTab;
