'use client';

import React from 'react';
import { Menu } from 'antd';
import { useRouter } from 'next/navigation';
import { useTranslation } from '@/utils/i18n';
import PermissionWrapper from '@/components/permission';
import UnifiedOpsCard from '@/app/opspilot/components/unified-ops-card';
import { formatRelativeTime, pickEntityTimestamp } from '@/app/opspilot/utils/relativeTime';
import { pickStableIcon } from '@/app/opspilot/utils/pickStableIcon';

interface EntityCardProps {
  id: string | number;
  name: string;
  introduction: string;
  created_by: string;
  team_name: string | string[];
  team: any[];
  online?: boolean;
  modelName?: string;
  skillType?: string;
  skill_type?: number;
  bot_type?: number;
  botType?: string;
  created_at?: string | null;
  updated_at?: string | null;
  is_pinned?: boolean;
  showPinButton?: boolean;
  permissions?: string[];
  onMenuClick: (action: string, entity: any) => void;
  redirectUrl: string;
  iconTypeMapping: string[];
  /** @deprecated Look B 使用 Owner/Team，保留以免调用方报错 */
  teamLabel?: string;
}

const EntityCard: React.FC<EntityCardProps> = ({
  id,
  name,
  introduction,
  created_by,
  team_name,
  team,
  online,
  modelName,
  skillType,
  skill_type,
  bot_type,
  botType,
  created_at,
  updated_at,
  is_pinned,
  showPinButton = false,
  permissions,
  onMenuClick,
  redirectUrl,
  iconTypeMapping,
}) => {
  const router = useRouter();
  const { t } = useTranslation();

  const entityPayload = {
    id,
    name,
    introduction,
    created_by,
    team_name,
    team,
    online,
    skill_type,
    bot_type,
    is_pinned,
  };

  const menu = (
    <Menu>
      <Menu.Item key={`edit-${id}`}>
        <PermissionWrapper requiredPermissions={['Edit']} instPermissions={permissions}>
          <span className="block" onClick={() => onMenuClick('edit', entityPayload)}>
            {t('common.edit')}
          </span>
        </PermissionWrapper>
      </Menu.Item>
      <Menu.Item key={`delete-${id}`}>
        <PermissionWrapper requiredPermissions={['Delete']} instPermissions={permissions}>
          <span className="block" onClick={() => onMenuClick('delete', entityPayload)}>
            {t('common.delete')}
          </span>
        </PermissionWrapper>
      </Menu.Item>
    </Menu>
  );

  const getIconType = () => pickStableIcon(id, iconTypeMapping, name);

  // 工作台 botType（Chatflow 等）与标题下上线/下线重复，改用上线/下线作 meta tag
  const studioStatusMeta =
    bot_type !== undefined && online !== undefined
      ? online
        ? t('studio.on')
        : t('studio.off')
      : undefined;

  const meta = [
    studioStatusMeta ?? botType,
    skillType,
    modelName,
  ].filter((item): item is string => Boolean(item && String(item).trim()));

  const teams = Array.isArray(team_name)
    ? team_name
    : team_name
      ? [team_name]
      : [];

  const relativeUpdatedAt = formatRelativeTime(pickEntityTimestamp({ updated_at, created_at }), t);

  return (
    <UnifiedOpsCard
      name={name}
      description={introduction}
      icon={getIconType()}
      status={
        studioStatusMeta || online === undefined
          ? undefined
          : online
            ? 'online'
            : 'offline'
      }
      statusLabel={
        studioStatusMeta || online === undefined
          ? undefined
          : online
            ? t('studio.on')
            : t('studio.off')
      }
      updatedAt={relativeUpdatedAt || undefined}
      meta={meta}
      pinned={is_pinned}
      showPin={showPinButton}
      footer="entity"
      owner={created_by || '--'}
      team={teams}
      menuOverlay={menu}
      onClick={() => router.push(`${redirectUrl}?id=${id}&name=${name}&desc=${introduction}`)}
      onPinClick={() => onMenuClick('pin', entityPayload)}
    />
  );
};

export default EntityCard;
