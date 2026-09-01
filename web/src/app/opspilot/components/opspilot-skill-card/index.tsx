'use client';

import React from 'react';
import EntityCard from '@/app/opspilot/components/opspilot-entity-card';
import type { OpsPilotSkillCardRecord } from '@/app/opspilot/components/opspilot-cards';

interface StudioCardProps extends OpsPilotSkillCardRecord {
  index: number;
  onMenuClick: (action: string, studio: OpsPilotSkillCardRecord) => void;
}

const SkillCard: React.FC<StudioCardProps> = (props) => {
  const {
    id,
    name,
    introduction,
    created_by,
    team_name,
    team,
    llm_model_name,
    skill_type,
    created_at,
    updated_at,
    is_pinned,
    permissions,
    onMenuClick,
  } = props;
  const iconTypeMapping = ['jiqirenjiaohukapian', 'jiqiren', 'jiqiren1', 'jiqiren2'];

  return (
    <EntityCard
      id={id}
      name={name}
      introduction={introduction}
      created_by={created_by}
      team_name={team_name}
      team={team}
      modelName={llm_model_name as string}
      skill_type={skill_type as number}
      created_at={typeof created_at === 'string' ? created_at : undefined}
      updated_at={typeof updated_at === 'string' ? updated_at : undefined}
      is_pinned={is_pinned}
      showPinButton={true}
      permissions={permissions}
      onMenuClick={onMenuClick}
      redirectUrl="/opspilot/skill/detail"
      iconTypeMapping={iconTypeMapping}
    />
  );
};

export default SkillCard;
