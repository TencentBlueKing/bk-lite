'use client';

import React from 'react';
import EntityCard from '@/app/opspilot/components/entity-card';
import { Studio } from '@/app/opspilot/types/studio';

interface StudioCardProps extends Studio {
  index: number;
  onMenuClick: (action: string, studio: Studio) => void;
}

const StudioCard: React.FC<StudioCardProps> = (props) => {
  const { id, name, introduction, created_by, team_name, team, online, bot_type, permissions, onMenuClick } = props;
  const iconTypeMapping: [string, string] = ['jiqirenjiaohukapian', 'jiqiren'];
  const botTypeMapping: { [key: number]: string } = {
    1: 'Pilot',
    2: 'LobeChat',
    3: 'Chatflow'
  };

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
      botType={botTypeMapping[bot_type] || ''}
      permissions={permissions}
      onMenuClick={onMenuClick}
      redirectUrl="/opspilot/studio/detail"
      iconTypeMapping={iconTypeMapping}
    />
  );
};

export default StudioCard;
