'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { Alert, Button, Drawer, Form, Input } from 'antd';

import { useRumQueries } from '@/app/rum/api';
import { OriginEditor } from '@/app/rum/applications/ui/origin-editor';
import { rumErrorMessage } from '@/app/rum/lib/error-message';
import { rumSetupPath } from '@/app/rum/lib/ingest';
import { useTranslation } from '@/utils/i18n';

export default function CreateApplicationDrawer({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const { t } = useTranslation();
  const router = useRouter();
  const { createApplication } = useRumQueries();
  const [application, setApplication] = useState('');
  const [origins, setOrigins] = useState(['http://127.0.0.1:5100']);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState('');

  function reset() {
    setApplication('');
    setOrigins(['http://127.0.0.1:5100']);
    setError('');
    setPending(false);
  }

  async function submit() {
    setPending(true);
    setError('');
    try {
      const validOrigins = origins.map((value) => value.trim()).filter(Boolean);
      if (!application.trim() || validOrigins.length === 0) {
        setError(t('rum.create.required', '请填写应用名称与至少一个 Origin'));
        return;
      }
      const view = await createApplication({
        application: application.trim(),
        origins: validOrigins,
      });
      onOpenChange(false);
      reset();
      router.push(rumSetupPath(view.application));
    } catch (err) {
      setError(rumErrorMessage(err, t));
    } finally {
      setPending(false);
    }
  }

  return (
    <Drawer
      open={open}
      onClose={() => {
        onOpenChange(false);
        reset();
      }}
      destroyOnClose
      width={520}
      title={t('rum.create.title', '新建 RUM 应用')}
      footer={
        <div className="flex justify-end gap-2">
          <Button onClick={() => onOpenChange(false)}>{t('rum.common.cancel', '取消')}</Button>
          <Button type="primary" loading={pending} onClick={() => void submit()}>
            {t('rum.create.submit', '创建')}
          </Button>
        </div>
      }
    >
      <div className="space-y-4">
        <p className="text-xs leading-5 text-[var(--color-text-3)]">
          {t(
            'rum.create.description',
            '填写应用名与允许的浏览器 Origin；创建后立即签发 Browser Key。',
          )}
        </p>
        {error ? <Alert type="error" showIcon message={error} /> : null}
        <Form layout="vertical" requiredMark={false}>
          <Form.Item label={t('rum.create.application', '应用名称')} className="mb-4">
            <Input
              value={application}
              placeholder={t('rum.create.applicationPlaceholder', '例如 storefront')}
              onChange={(event) => setApplication(event.target.value)}
              autoFocus
            />
            <p className="mt-1 text-xs text-[var(--color-text-3)]">
              {t(
                'rum.create.applicationHint',
                '1–80 个字母、数字、点、下划线、冒号或短横线，以字母或数字开头；须与 SDK app.name 完全一致。',
              )}
            </p>
          </Form.Item>
          <Form.Item label={t('rum.create.origins', '允许的浏览器 Origin')} className="mb-0">
            <OriginEditor origins={origins} onChange={setOrigins} />
            <p className="mt-1 text-xs text-[var(--color-text-3)]">
              {t(
                'rum.create.originsHint',
                '精确填写协议、主机和可选端口。其他 Origin 会被拒绝；这仍是滥用控制，Browser Key 不可省略。',
              )}
            </p>
          </Form.Item>
        </Form>
      </div>
    </Drawer>
  );
}
