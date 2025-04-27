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
  const { id, name, introduction, created_by, team_name, team, index, llm_model_name, skill_type, onMenuClick } = props;
  const iconTypeMapping: [string, string] = ['jiqirenjiaohukapian', 'jiqiren'];

  const skillTypeMapping = {
    2: t('skill.form.qaType'),
    1: t('skill.form.toolsType'),
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
      index={index}
      modelName={llm_model_name}
      skillType={skillType}
      onMenuClick={onMenuClick}
      redirectUrl="/opspilot/skill/detail"
      iconTypeMapping={iconTypeMapping}
    />
  );
};

export default StudioCard;
