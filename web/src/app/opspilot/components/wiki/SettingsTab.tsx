'use client';

import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Button, Divider, Form, Input, Popconfirm, Select, Space, Spin, Tag, message } from 'antd';
import { AimOutlined, InfoCircleOutlined, WarningOutlined } from '@ant-design/icons';
import { useRouter } from 'next/navigation';
import { useIntl } from 'react-intl';
import { useTranslation } from '@/utils/i18n';
import GroupTreeSelect from '@/components/group-tree-select';
import { useWikiApi } from '@/app/opspilot/api/wiki';
import { LlmModel } from '@/app/opspilot/types/skill';
import { WikiKnowledgeBase } from '@/app/opspilot/types/wiki';

type SectionKey = 'basic' | 'purpose' | 'danger';

const HELP_KEY: Record<SectionKey, string> = {
  basic: 'wiki.helpBasicDesc',
  purpose: 'wiki.helpPurposeDesc',
  danger: 'wiki.helpDangerDesc',
};

// 设置工作区(spec 4.6):左侧导航 | 中部表单 | 右侧预览/说明
// 生成语言默认跟随登录用户语言;网页同步已迁到「新增资料(网页)」按站点单独配置
const SettingsTab: React.FC<{ kbId: number }> = ({ kbId }) => {
  const { t } = useTranslation();
  const intl = useIntl();
  const router = useRouter();
  const [form] = Form.useForm();
  const { fetchKnowledgeBase, updateKnowledgeBase, fetchLlmModels, rebuildKnowledgeBase, deleteKnowledgeBase } =
    useWikiApi();
  const [llmModels, setLlmModels] = useState<LlmModel[]>([]);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [busy, setBusy] = useState(false);
  const [active, setActive] = useState<SectionKey>('basic');
  const [kbStatus, setKbStatus] = useState<string>('active');
  // 保存原始 KB:PUT 为全量更新,被移除的设置字段需回填原值,避免被重置
  const kbRef = useRef<WikiKnowledgeBase | null>(null);

  const nameW = Form.useWatch('name', form);
  const modelW = Form.useWatch('llm_model', form);
  const introW = Form.useWatch('introduction', form);
  const modelName = llmModels.find((m) => m.id === modelW)?.name;

  const sections: { key: SectionKey; label: string; icon: React.ReactNode; danger?: boolean }[] = [
    { key: 'basic', label: t('wiki.settingsBasic'), icon: <InfoCircleOutlined /> },
    { key: 'purpose', label: t('wiki.settingsPurposeSchema'), icon: <AimOutlined /> },
    { key: 'danger', label: t('wiki.dangerZone'), icon: <WarningOutlined />, danger: true },
  ];
  const activeSection = sections.find((s) => s.key === active)!;

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [kb, models] = await Promise.all([fetchKnowledgeBase(kbId), fetchLlmModels().catch(() => [])]);
      kbRef.current = kb;
      setLlmModels(models || []);
      setKbStatus(kb.status || 'active');
      form.setFieldsValue({
        name: kb.name,
        introduction: kb.introduction,
        llm_model: kb.llm_model,
        team: kb.team,
        purpose_md: kb.purpose_md,
        schema_md: kb.schema_md,
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
      // 生成语言默认跟随登录用户的界面语言(不再手选)
      const userLang = (intl.locale || '').toLowerCase().includes('en') ? 'en' : 'zh';
      const prev = kbRef.current;
      await updateKnowledgeBase(kbId, {
        name: v.name,
        introduction: v.introduction,
        llm_model: v.llm_model,
        team: v.team,
        purpose_md: v.purpose_md,
        schema_md: v.schema_md,
        generation_language: userLang,
        // 以下字段已从设置页移除,PUT 全量更新时回填原值避免被清空
        generation_rules: prev?.generation_rules ?? {},
        web_sync_policy: prev?.web_sync_policy ?? {},
        risk_rules: prev?.risk_rules ?? {},
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
  // 分区标题:图标 + 标题 + 下边框分隔(扁平分层,符合 DESIGN「Flat By Default」)
  const head = (icon: React.ReactNode, text: string) => (
    <div className="flex items-center gap-2 pb-3 mb-5 border-b border-[var(--color-border)]">
      <span className="flex items-center text-[var(--color-text-2)]">{icon}</span>
      <span className="text-[15px] font-semibold text-[var(--color-text-1)]">{text}</span>
    </div>
  );

  return (
    <Spin spinning={loading}>
      <div className="grid grid-cols-[160px_minmax(0,1fr)] xl:grid-cols-[188px_minmax(0,1fr)_400px] gap-6 min-h-[calc(100vh-280px)]">
        {/* 左侧导航(竖线撑满面板高度) */}
        <nav className="border-r border-[var(--color-border)] pr-3">
          {sections.map((s) => {
            const on = active === s.key;
            return (
              <button
                key={s.key}
                type="button"
                onClick={() => setActive(s.key)}
                className={`w-full flex items-center gap-2.5 px-3 py-2 mb-1 rounded-md text-sm text-left transition-colors ${
                  on
                    ? 'bg-[var(--color-primary-bg-active)] text-[var(--color-primary)] font-medium'
                    : s.danger
                      ? 'text-[var(--color-fail)] hover:bg-[var(--color-fill-2)]'
                      : 'text-[var(--color-text-2)] hover:bg-[var(--color-fill-2)]'
                }`}
              >
                <span className="flex items-center">{s.icon}</span>
                {s.label}
              </button>
            );
          })}
        </nav>

        {/* 中部表单 */}
        <div className="min-w-0">
          <Form form={form} layout="vertical">
            {/* 基本信息 */}
            <div style={show('basic')}>
              {head(<InfoCircleOutlined />, t('wiki.settingsBasic'))}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-x-8">
                <Form.Item label={t('wiki.name')} name="name" rules={[{ required: true }]}>
                  <Input />
                </Form.Item>
                <Form.Item
                  label={t('wiki.llmModel')}
                  name="llm_model"
                  rules={[{ required: true, message: `${t('common.selectMsg')}${t('wiki.llmModel')}` }]}
                  tooltip={t('wiki.llmModelTip')}
                >
                  <Select
                    placeholder={t('wiki.llmModelPlaceholder')}
                    options={llmModels.map((m) => ({ value: m.id, label: m.name, disabled: !m.enabled }))}
                  />
                </Form.Item>
                <Form.Item className="md:col-span-2" label={t('wiki.introduction')} name="introduction">
                  <Input.TextArea rows={3} />
                </Form.Item>
                <Form.Item
                  className="md:col-span-2"
                  label={t('common.organization')}
                  name="team"
                  rules={[{ required: true, message: `${t('common.selectMsg')}${t('common.organization')}` }]}
                >
                  <GroupTreeSelect placeholder={`${t('common.selectMsg')}${t('common.organization')}`} />
                </Form.Item>
              </div>
            </div>

            {/* 用途与结构 */}
            <div style={show('purpose')}>
              {head(<AimOutlined />, t('wiki.settingsPurposeSchema'))}
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-x-6">
                <Form.Item label={t('wiki.purpose')} name="purpose_md">
                  <Input.TextArea rows={12} />
                </Form.Item>
                <Form.Item label={t('wiki.schema')} name="schema_md">
                  <Input.TextArea rows={12} />
                </Form.Item>
              </div>
            </div>
          </Form>

          {active !== 'danger' && (
            <div className="pt-5 mt-6 border-t border-[var(--color-border)]">
              <Button type="primary" loading={saving} onClick={handleSave}>
                {t('common.save')}
              </Button>
            </div>
          )}

          {/* 危险操作 */}
          <div style={show('danger')} className="max-w-2xl">
            {head(<WarningOutlined />, t('wiki.dangerZone'))}
            <Space direction="vertical" className="w-full" size="middle">
              <div className="flex items-center justify-between">
                <span className="text-[var(--color-text-3)] text-sm">{t('wiki.rebuildAllTip')}</span>
                <Popconfirm title={t('wiki.rebuildAllConfirm')} onConfirm={() => runDanger(() => rebuildKnowledgeBase(kbId))}>
                  <Button loading={busy}>{t('wiki.rebuildAll')}</Button>
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

        {/* 右侧:预览 + 说明(xl 起显示,填满右侧) */}
        <aside className="hidden xl:block">
          <div className="sticky top-2 space-y-4">
            {active === 'basic' && (
              <div className="rounded-lg border border-[var(--color-border)] p-4">
                <div className="text-xs text-[var(--color-text-3)] mb-3">{t('wiki.settingsPreviewTitle')}</div>
                <div className="text-base font-medium text-[var(--color-text-1)] truncate">{nameW || '—'}</div>
                <div className="mt-1.5">
                  <Tag color={kbStatus === 'archived' ? 'default' : 'green'} className="!mr-0">
                    {kbStatus === 'archived' ? t('wiki.statusArchived') : t('wiki.statusActive')}
                  </Tag>
                </div>
                {introW ? (
                  <div className="mt-3 text-[13px] leading-6 text-[var(--color-text-3)] line-clamp-3">{introW}</div>
                ) : null}
                <Divider className="my-3" />
                <div className="flex justify-between text-sm">
                  <span className="text-[var(--color-text-3)]">{t('wiki.llmModel')}</span>
                  <span className="text-[var(--color-text-1)] truncate ml-3 text-right">{modelName || '—'}</span>
                </div>
              </div>
            )}
            <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-fill-1)] p-4">
              <div className="flex items-center gap-2 text-sm font-medium mb-2 text-[var(--color-text-1)]">
                <span className="flex items-center text-[var(--color-text-2)]">{activeSection.icon}</span>
                {t('wiki.settingsHelpTitle')}
              </div>
              <p className="text-[13px] leading-6 text-[var(--color-text-3)] m-0">{t(HELP_KEY[active])}</p>
              {active === 'purpose' && (
                <p className="text-[13px] leading-6 text-[var(--color-text-3)] mt-2 mb-0">{t('wiki.helpPurposeTip')}</p>
              )}
            </div>
          </div>
        </aside>
      </div>
    </Spin>
  );
};

export default SettingsTab;
