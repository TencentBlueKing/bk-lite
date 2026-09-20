'use client';

import { useEffect, useState } from 'react';
import { Alert, Button, Drawer, Form, Input, Select } from 'antd';

import { useRumQueries, type RumFunnelItem } from '@/app/rum/api';
import { rumErrorMessage } from '@/app/rum/lib/error-message';
import { useTranslation } from '@/utils/i18n';

export default function FunnelFormDrawer({
  open,
  onOpenChange,
  onSaved,
  initial,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSaved: () => void;
  initial?: RumFunnelItem | null;
}) {
  const { t } = useTranslation();
  const { createFunnel, updateFunnel, listApplications } = useRumQueries();
  const [name, setName] = useState('');
  const [steps, setSteps] = useState('/,/checkout,/success');
  const [application, setApplication] = useState('');
  const [apps, setApps] = useState<string[]>([]);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    if (!open) return;
    if (initial) {
      setName(initial.name);
      setSteps((initial.steps || []).join(','));
      setApplication(initial.application || '');
    } else {
      setName('');
      setSteps('/,/checkout,/success');
      setApplication('');
    }
    setError('');
    void listApplications()
      .then((items) => setApps(items.map((item) => item.application).filter(Boolean)))
      .catch(() => setApps([]));
  }, [open, initial, listApplications]);

  async function submit() {
    setPending(true);
    setError('');
    try {
      const stepList = steps
        .split(',')
        .map((s) => s.trim())
        .filter(Boolean);
      if (!name.trim() || stepList.length < 2) {
        setError(t('rum.funnels.required', '请填写名称，并至少提供 2 个路由步骤'));
        return;
      }
      const body = {
        name: name.trim(),
        steps: stepList,
        application: application.trim() || undefined,
      };
      if (initial?.id) await updateFunnel(initial.id, body);
      else await createFunnel(body);
      onOpenChange(false);
      onSaved();
    } catch (err) {
      setError(rumErrorMessage(err, t));
    } finally {
      setPending(false);
    }
  }

  return (
    <Drawer
      open={open}
      onClose={() => onOpenChange(false)}
      destroyOnClose
      width={520}
      title={initial?.id ? t('rum.funnels.edit', '编辑') : t('rum.funnels.create', '新建漏斗')}
      footer={
        <div className="flex justify-end gap-2">
          <Button onClick={() => onOpenChange(false)}>{t('rum.common.cancel', '取消')}</Button>
          <Button type="primary" loading={pending} onClick={() => void submit()}>
            {initial?.id ? t('rum.common.save', '保存') : t('rum.funnels.create', '新建漏斗')}
          </Button>
        </div>
      }
    >
      <div className="space-y-4">
        <p className="text-xs leading-5 text-[var(--color-text-3)]">
          {t(
            'rum.funnels.createDescription',
            '定义路由步骤后，可按当前筛选范围测算到达人数与转化率。',
          )}
        </p>
        {error ? <Alert type="error" showIcon message={error} /> : null}
        <Form layout="vertical" requiredMark={false}>
          <Form.Item label={t('rum.funnels.name', '名称')} className="mb-4">
            <Input value={name} onChange={(e) => setName(e.target.value)} autoFocus />
          </Form.Item>
          <Form.Item label={t('rum.applications.application', '应用')} className="mb-4">
            <Select
              value={application || undefined}
              onChange={setApplication}
              allowClear
              placeholder={t('rum.filter.allApps', '全部应用')}
              options={apps.map((app) => ({ value: app, label: app }))}
              className="w-full"
            />
          </Form.Item>
          <Form.Item label={t('rum.funnels.steps', '步骤')} className="mb-0">
            <Input
              value={steps}
              onChange={(e) => setSteps(e.target.value)}
              placeholder="/,/checkout,/success"
            />
            <p className="mt-1 text-xs text-[var(--color-text-3)]">
              {t('rum.funnels.stepsHint', '用逗号分隔 2–8 个路由，例如 /,/checkout,/success')}
            </p>
          </Form.Item>
        </Form>
      </div>
    </Drawer>
  );
}
