'use client';

import React from 'react';
import { useTranslation } from '@/utils/i18n';
import EntityCard from '@/app/opspilot/components/entity-card';
import { Studio } from '@/app/opspilot/types/studio';

interface StudioCardProps extends Studio {
  index: number;
  onMenuClick: (action: string, studio: Studio) => void;
}

const StudioCard: React.FC<StudioCardProps> = (props) => {
  const { t } = useTranslation();
  const { id, name, introduction, created_by, team_name, team, llm_model_name, skill_type, is_pinned, permissions, onMenuClick } = props;
  const iconTypeMapping: [string, string] = ['jiqirenjiaohukapian', 'jiqiren'];

  const skillTypeMapping = {
    2: t('skill.form.qaTag'),
    1: t('skill.form.toolsTag'),
    3: t('skill.form.planTag'),
    4: t('skill.form.complexTag')
  };
  const skillType = skillTypeMapping[skill_type as keyof typeof skillTypeMapping] || 'Unknown';

  return (
    <EntityCard
      id={id}
      name={name}
      introduction={introduction}
      created_by={created_by}
      team_name={team_name}
      team={team}
      modelName={llm_model_name}
      skill_type={skill_type}
      skillType={skillType}
      is_pinned={is_pinned}
      showPinButton={true}
      permissions={permissions}
      onMenuClick={onMenuClick}
      redirectUrl="/opspilot/skill/detail"
      iconTypeMapping={iconTypeMapping}
    />
  );
};

export default StudioCard;
