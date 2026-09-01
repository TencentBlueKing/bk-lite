'use client';

import React from 'react';
import EntityCard from '@/app/opspilot/components/entity-card';
import { Studio } from '@/app/opspilot/types/studio';

interface StudioCardProps extends Studio {
  index: number;
  onMenuClick: (action: string, studio: Studio) => void;
}

const StudioCard: React.FC<StudioCardProps> = (props) => {
  const {
    id,
    name,
    introduction,
    created_by,
    team_name,
    team,
    online,
    bot_type,
    created_at,
    updated_at,
    is_pinned,
    permissions,
    onMenuClick,
  } = props;
  const iconTypeMapping = ['Chatflow', 'gongzuotai', 'Copilot'];

  return (
    <EntityCard
      id={id}
      name={name}
      introduction={introduction}
      created_by={created_by}
      team_name={team_name}
      team={team}
      online={online}
      bot_type={bot_type}
      created_at={typeof created_at === 'string' ? created_at : undefined}
      updated_at={typeof updated_at === 'string' ? updated_at : undefined}
      is_pinned={is_pinned}
      showPinButton={true}
      permissions={permissions}
      onMenuClick={onMenuClick}
      redirectUrl="/opspilot/studio/detail"
      iconTypeMapping={iconTypeMapping}
    />
  );
};

export default StudioCard;
