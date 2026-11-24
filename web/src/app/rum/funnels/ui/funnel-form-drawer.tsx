'use client';

import { useEffect, useState } from 'react';
import { MinusOutlined, PlusOutlined } from '@ant-design/icons';
import { Alert, Button, Drawer, Form, Input, Select } from 'antd';

import { useRumQueries, type RumFunnelItem } from '@/app/rum/api';
import {
  FUNNEL_STEP_MAX,
  FUNNEL_STEP_MIN,
  addFunnelStepRow,
  blankFunnelStepRows,
  funnelStepPlaceholder,
  funnelStepRowsFromSteps,
  removeFunnelStepRow,
  validateFunnelStepRows,
} from '@/app/rum/funnels/ui/funnel-step-rows';
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
  const [rows, setRows] = useState<string[]>(() => blankFunnelStepRows());
  const [invalidIndexes, setInvalidIndexes] = useState<number[]>([]);
  const [application, setApplication] = useState('');
  const [apps, setApps] = useState<string[]>([]);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    if (!open) return;
    if (initial) {
      setName(initial.name);
      setRows(funnelStepRowsFromSteps(initial.steps));
      setApplication(initial.application || '');
    } else {
      setName('');
      setRows(blankFunnelStepRows());
      setApplication('');
    }
    setInvalidIndexes([]);
    setError('');
    void listApplications(true)
      .then((items) => setApps(items.map((item) => item.application).filter(Boolean)))
      .catch(() => setApps([]));
  }, [open, initial, listApplications]);

  async function submit() {
    const stepResult = validateFunnelStepRows(rows);
    setInvalidIndexes(stepResult.invalidIndexes);
    if (!name.trim() || stepResult.countError) {
      setError(t('rum.funnels.required', '请填写名称，并至少提供 2 个路由步骤'));
      return;
    }
    if (!stepResult.ok) {
      setError('');
      return;
    }
    setPending(true);
    setError('');
    try {
      const body = {
        name: name.trim(),
        steps: stepResult.steps,
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
            <div className="space-y-2">
              {rows.map((row, index) => {
                const invalid = invalidIndexes.includes(index);
                return (
                  <div key={index} className="flex items-start gap-2">
                    <div className="min-w-0 flex-1">
                      <Input
                        value={row}
                        placeholder={funnelStepPlaceholder(index)}
                        status={invalid ? 'error' : undefined}
                        aria-invalid={invalid || undefined}
                        aria-label={`${t('rum.funnels.step', '步骤')} ${index + 1}`}
                        onChange={(event) => {
                          const value = event.target.value;
                          setRows((current) =>
                            current.map((item, rowIndex) => (rowIndex === index ? value : item)),
                          );
                          setInvalidIndexes((current) => current.filter((rowIndex) => rowIndex !== index));
                        }}
                      />
                      {invalid ? (
                        <p className="mt-1 text-xs text-[var(--color-fail)]">
                          {t('rum.funnels.stepInvalid', '路由需以 / 开头')}
                        </p>
                      ) : null}
                    </div>
                    <Button
                      type="default"
                      size="small"
                      className="size-8 shrink-0 px-0"
                      icon={<MinusOutlined aria-hidden="true" />}
                      disabled={rows.length <= FUNNEL_STEP_MIN}
                      aria-label={t('rum.funnels.removeStep', '删除路由')}
                      onClick={() => {
                        setRows((current) => removeFunnelStepRow(current, index));
                        setInvalidIndexes([]);
                      }}
                    />
                  </div>
                );
              })}
              <Button
                type="link"
                size="small"
                className="h-auto px-0"
                icon={<PlusOutlined aria-hidden="true" />}
                disabled={rows.length >= FUNNEL_STEP_MAX}
                onClick={() => {
                  setRows((current) => addFunnelStepRow(current));
                  setInvalidIndexes([]);
                }}
              >
                {t('rum.funnels.addStep', '添加路由')}
              </Button>
            </div>
            <p className="mt-1 text-xs text-[var(--color-text-3)]">
              {t('rum.funnels.stepsHint', '每行一个路由，共 2–8 个，每个以 / 开头')}
            </p>
          </Form.Item>
        </Form>
      </div>
    </Drawer>
  );
}
