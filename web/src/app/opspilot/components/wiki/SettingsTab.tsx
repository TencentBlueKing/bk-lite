'use client';

import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Button, Form, Input, Popconfirm, Select, Spin, Tabs, message } from 'antd';
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

// 设置工作区(spec 4.6):顶部 Tab 切换分区(与其它详情页统一),内容下方铺开
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
  // 保存原始 KB:PUT 为全量更新,被移除的设置字段需回填原值,避免被重置
  const kbRef = useRef<WikiKnowledgeBase | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [kb, models] = await Promise.all([fetchKnowledgeBase(kbId), fetchLlmModels().catch(() => [])]);
      kbRef.current = kb;
      setLlmModels(models || []);
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

  // 各分区帮助说明(扁平内联提示,替代原右侧说明卡)
  const hint = (key: string) => (
    <p className="text-[13px] leading-6 text-[var(--color-text-3)] mb-4 mt-0">{t(key)}</p>
  );

  const basicPane = (
    <div className="max-w-3xl">
      {hint(HELP_KEY.basic)}
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
  );

  const purposePane = (
    <div>
      {hint(HELP_KEY.purpose)}
      {/* 两个文本域拉高(autoSize 起步 18 行),保存按钮自然贴近底部,常规内容无需内部滚动 */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-x-6">
        <Form.Item label={t('wiki.purpose')} name="purpose_md">
          <Input.TextArea autoSize={{ minRows: 18, maxRows: 28 }} />
        </Form.Item>
        <Form.Item label={t('wiki.schema')} name="schema_md">
          <Input.TextArea autoSize={{ minRows: 18, maxRows: 28 }} />
        </Form.Item>
      </div>
    </div>
  );

  const dangerPane = (
    <div className="max-w-2xl">
      {hint(HELP_KEY.danger)}
      {/* 危险区域(参考 GitHub Danger Zone:红框容器 + 每项 标题/后果说明/危险按钮) */}
      <div className="rounded-lg border border-[var(--color-fail)]">
        <div className="flex items-center justify-between gap-4 p-4">
          <div className="min-w-0">
            <div className="text-sm font-medium text-[var(--color-text-1)]">{t('wiki.rebuildAll')}</div>
            <div className="text-[13px] leading-6 text-[var(--color-text-3)] mt-0.5">{t('wiki.rebuildAllTip')}</div>
          </div>
          <Popconfirm title={t('wiki.rebuildAllConfirm')} onConfirm={() => runDanger(() => rebuildKnowledgeBase(kbId))}>
            <Button loading={busy} className="flex-shrink-0">
              {t('wiki.rebuildAll')}
            </Button>
          </Popconfirm>
        </div>
        <div className="flex items-center justify-between gap-4 p-4 border-t border-[var(--color-fail)]">
          <div className="min-w-0">
            <div className="text-sm font-medium text-[var(--color-fail)]">{t('wiki.deleteKb')}</div>
            <div className="text-[13px] leading-6 text-[var(--color-text-3)] mt-0.5">{t('wiki.deleteTip')}</div>
          </div>
          <Popconfirm
            title={t('wiki.deleteConfirm')}
            okButtonProps={{ danger: true }}
            onConfirm={() => runDanger(() => deleteKnowledgeBase(kbId), () => router.push('/opspilot/wiki'))}
          >
            <Button danger loading={busy} className="flex-shrink-0">
              {t('common.delete')}
            </Button>
          </Popconfirm>
        </div>
      </div>
    </div>
  );

  return (
    <Spin spinning={loading}>
      <Form form={form} layout="vertical">
        {/* forceRender:所有分区始终挂载,切 Tab 不丢失未提交字段值,保存时全量校验通过 */}
        <Tabs
          activeKey={active}
          onChange={(k) => setActive(k as SectionKey)}
          items={[
            {
              key: 'basic',
              label: (
                <span>
                  <InfoCircleOutlined className="mr-1.5" />
                  {t('wiki.settingsBasic')}
                </span>
              ),
              forceRender: true,
              children: basicPane,
            },
            {
              key: 'purpose',
              label: (
                <span>
                  <AimOutlined className="mr-1.5" />
                  {t('wiki.settingsPurposeSchema')}
                </span>
              ),
              forceRender: true,
              children: purposePane,
            },
            {
              key: 'danger',
              label: (
                <span className="text-[var(--color-fail)]">
                  <WarningOutlined className="mr-1.5" />
                  {t('wiki.dangerZone')}
                </span>
              ),
              forceRender: true,
              children: dangerPane,
            },
          ]}
        />
        {active !== 'danger' && (
          <div className="pt-2">
            <Button type="primary" loading={saving} onClick={handleSave}>
              {t('common.save')}
            </Button>
          </div>
        )}
      </Form>
    </Spin>
  );
};

export default SettingsTab;
