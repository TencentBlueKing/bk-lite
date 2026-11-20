'use client';

import React from 'react';
import { message } from 'antd';
import EntityList from '@/app/opspilot/components/entity-list';
import GenericModifyModal from '@/app/opspilot/components/generic-modify-modal';
import SkillCard from '@/app/opspilot/components/skill/skillCard';
import SkillViewSwitcher from '@/app/opspilot/components/skill/SkillViewSwitcher';
import type { Skill } from '@/app/opspilot/types/skill';
import { useTranslation } from '@/utils/i18n';
import { useSkillApi } from '@/app/opspilot/api/skill';

type SkillModifyModalProps = Omit<React.ComponentProps<typeof GenericModifyModal>, 'formType'>;

const SkillModifyModal = (props: SkillModifyModalProps) => <GenericModifyModal {...props} formType="skill" />;

export default function SkillPage() {
  const { t } = useTranslation();
  const { togglePin } = useSkillApi();

  const handleTogglePin = async (item: Skill) => {
    await togglePin(item.id);
    message.success(item.is_pinned ? t('common.unpinSuccess') : t('common.pinSuccess'));
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
    />
  );
}
