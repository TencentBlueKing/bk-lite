'use client';

import React, { useRef } from 'react';
import { UploadOutlined } from '@ant-design/icons';
import { Button, message } from 'antd';
import { useScreenAwareRouter } from '@/console-layout';
import EntityList from '@/app/opspilot/components/entity-list';
import GenericModifyModal from '@/app/opspilot/components/generic-modify-modal';
import SkillCard from '@/app/opspilot/components/skill/skillCard';
import SkillViewSwitcher from '@/app/opspilot/components/skill/SkillViewSwitcher';
import PermissionWrapper from '@/components/permission';
import type { Skill } from '@/app/opspilot/types/skill';
import { useTranslation } from '@/utils/i18n';
import { useSkillApi } from '@/app/opspilot/api/skill';
import { downloadBlob, readBlobError, rememberAgentImportNotes } from '@/app/opspilot/utils/agentTransfer';

type SkillModifyModalProps = Omit<React.ComponentProps<typeof GenericModifyModal>, 'formType'>;

const SkillModifyModal = (props: SkillModifyModalProps) => <GenericModifyModal {...props} formType="skill" />;

export default function SkillPage() {
  const { t } = useTranslation();
  const router = useScreenAwareRouter();
  const { togglePin, exportAgent, importAgent } = useSkillApi();
  const fileRef = useRef<HTMLInputElement>(null);

  const handleTogglePin = async (item: Skill) => {
    await togglePin(item.id);
    message.success(item.is_pinned ? t('common.unpinSuccess') : t('common.pinSuccess'));
  };

  const handleExport = async (item: Skill) => {
    try {
      const blob = await exportAgent(item.id);
      downloadBlob(blob, `${item.name}.zip`);
    } catch (error) {
      message.error(await readBlobError(error, t('common.exportFailed')));
    }
  };

  const handleImport = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    event.target.value = '';
    if (!file) {
      return;
    }
    try {
      const result = await importAgent(file);
      rememberAgentImportNotes(result?.notes || []);
      router.push(`/opspilot/skill/detail/settings?id=${result.id}&name=${encodeURIComponent(result.name || '')}`);
    } catch {
      // 失败响应已经由请求层提示，留在列表页。
    }
  };

  return (
    <EntityList<Skill>
      endpoint="/opspilot/model_provider_mgmt/llm/"
      queryParams={{ is_template: 0 }}
      CardComponent={SkillCard}
      ModifyModalComponent={SkillModifyModal}
      itemTypeSingle="skill"
      pageTitle={t('skill.pageTitle')}
      pageDescription={t('skill.pageDescription')}
      afterHeader={<SkillViewSwitcher value="agents" />}
      onTogglePin={handleTogglePin}
      onExport={handleExport}
      headerExtra={(
        <PermissionWrapper requiredPermissions={['Add']}>
          <Button icon={<UploadOutlined />} onClick={() => fileRef.current?.click()}>{t('common.import')}</Button>
          <input
            ref={fileRef}
            type="file"
            accept=".zip,application/zip"
            className="hidden"
            aria-label={t('common.import')}
            onChange={handleImport}
          />
        </PermissionWrapper>
      )}
    />
  );
}
