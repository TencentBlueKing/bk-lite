'use client';

import { useEffect, useRef, useState } from 'react';
import { message } from 'antd';
import { useTranslation } from '@/utils/i18n';
import PermissionWrapper from '@/components/permission';
import { useRetentionApi } from '@/app/cmdb/api';
import RetentionPolicyForm, {
  type RetentionJob,
  type RetentionPolicy,
} from './RetentionPolicyForm';

export default function SystemSettingsPage() {
  const { t } = useTranslation();
  const { getRetention, saveRetention } = useRetentionApi();
  const [policy, setPolicy] = useState<RetentionPolicy | null>(null);
  const [job, setJob] = useState<RetentionJob | null>(null);
  const [saving, setSaving] = useState(false);
  const requestSeq = useRef(0);

  const load = async () => {
    const seq = ++requestSeq.current;
    try {
      const data = await getRetention();
      if (seq !== requestSeq.current) {
        return;
      }
      setPolicy(data.policy);
      setJob(data.job);
    } catch {
      if (seq !== requestSeq.current) {
        return;
      }
      setPolicy(null);
      setJob(null);
    }
  };

  useEffect(() => {
    load();
  }, []);

  return (
    <div className="p-6">
      <h2 className="mb-4 text-lg font-medium">{t('SystemSettings.title')}</h2>
      {policy && job ? (
        <PermissionWrapper requiredPermissions={['Edit Model']}>
          <RetentionPolicyForm
            policy={policy}
            job={job}
            saving={saving}
            onSave={async (next) => {
              setSaving(true);
              requestSeq.current += 1;
              try {
                const data = await saveRetention(next);
                setPolicy(data.policy);
                setJob(data.job);
                message.success(t('SystemSettings.saveSuccess'));
              } catch {
                await load();
              } finally {
                setSaving(false);
              }
            }}
          />
        </PermissionWrapper>
      ) : null}
    </div>
  );
}
