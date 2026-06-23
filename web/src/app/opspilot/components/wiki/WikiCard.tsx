'use client';

import React from 'react';
import EntityCard from '@/app/opspilot/components/entity-card';
import { WikiKnowledgeBase } from '@/app/opspilot/types/wiki';

interface WikiCardProps extends WikiKnowledgeBase {
  index: number;
  onMenuClick: (action: string, item: WikiKnowledgeBase) => void;
}

const WikiCard: React.FC<WikiCardProps> = (props) => {
  const { id, name, introduction, created_by, team_name, team, permissions, onMenuClick } = props;
  const iconTypeMapping: [string, string] = ['zhishiku', 'zhishiku'];

  return (
    <EntityCard
      id={id}
      name={name}
      introduction={introduction || ''}
      created_by={created_by || ''}
      team_name={team_name || []}
      team={team || []}
      permissions={permissions}
      onMenuClick={onMenuClick}
      redirectUrl="/opspilot/wiki/detail"
      iconTypeMapping={iconTypeMapping}
    />
  );
};

export default WikiCard;
