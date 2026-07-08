'use client';

import React from 'react';
import EntityCard from '@/app/opspilot/components/entity-card';
import { Skill } from '@/app/opspilot/types/skill';

interface StudioCardProps extends Skill {
  index: number;
  onMenuClick: (action: string, studio: Skill) => void;
}

const StudioCard: React.FC<StudioCardProps> = (props) => {
  const { id, name, introduction, created_by, team_name, team, llm_model_name, skill_type, is_pinned, permissions, onMenuClick } = props;
  const iconTypeMapping: [string, string] = ['jiqirenjiaohukapian', 'jiqiren'];

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
