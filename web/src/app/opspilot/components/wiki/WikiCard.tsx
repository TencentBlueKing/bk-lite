'use client';

import React from 'react';
import EntityCard from '@/app/opspilot/components/entity-card';
import { WikiKnowledgeBase } from '@/app/opspilot/types/wiki';

interface WikiCardProps extends WikiKnowledgeBase {
  index: number;
  onMenuClick: (action: string, item: WikiKnowledgeBase) => void;
}

const WikiCard: React.FC<WikiCardProps> = (props) => {
  const {
    id,
    name,
    introduction,
    created_by,
    team_name,
    team,
    created_at,
    updated_at,
    permissions,
    onMenuClick,
  } = props;
  const iconTypeMapping = ['zhishiku1', 'zhishiku3', 'zhishiku2', 'zhishiku'];

  return (
    <EntityCard
      id={id}
      name={name}
      introduction={introduction || ''}
      created_by={created_by || ''}
      team_name={team_name || []}
      team={team || []}
      created_at={created_at}
      updated_at={updated_at}
      permissions={permissions}
      onMenuClick={onMenuClick}
      redirectUrl="/opspilot/wiki/detail"
      iconTypeMapping={iconTypeMapping}
    />
  );
};

export default WikiCard;
