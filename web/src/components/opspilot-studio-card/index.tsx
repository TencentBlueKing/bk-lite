'use client';

import React from 'react';
import EntityCard from '@/components/opspilot-entity-card';
import type { OpsPilotStudioCardRecord } from '@/components/opspilot-cards';
import { useTranslation } from '@/utils/i18n';

interface StudioCardProps extends OpsPilotStudioCardRecord {
  index: number;
  onMenuClick: (action: string, studio: OpsPilotStudioCardRecord) => void;
}

const StudioCard: React.FC<StudioCardProps> = (props) => {
  const { id, name, introduction, created_by, team_name, team, online, bot_type, is_pinned, permissions, onMenuClick } = props;
  const { t } = useTranslation();
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
      is_pinned={is_pinned}
      showPinButton={true}
      permissions={permissions}
      onMenuClick={onMenuClick}
      redirectUrl="/opspilot/studio/detail"
      iconTypeMapping={iconTypeMapping}
      teamLabel={t('studio.form.manageGroup')}
    />
  );
};

export default StudioCard;
