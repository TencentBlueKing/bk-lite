'use client';

import React, { useContext, useMemo } from 'react';
import EllipsisWithTooltip from '@/components/ellipsis-with-tooltip';
import UserAvatar from '@/components/user-avatar';
import { UserInfoContext } from '@/context/userInfo';
import {
  buildOrganizationPathMap,
  formatAlertOrganizationPath,
} from '@/app/alarm/utils/organizationPath';

interface OperatorWithOrgCellProps {
  team?: Array<string | number> | null;
  operatorUser?: string;
}

const OperatorWithOrgCell: React.FC<OperatorWithOrgCellProps> = ({
  team,
  operatorUser,
}) => {
  const userInfo = useContext(UserInfoContext);
  const organizationPath = useMemo(() => {
    const pathById = buildOrganizationPathMap(userInfo?.groupTree);
    const nameById = new Map(
      (userInfo?.flatGroups || []).map(
        (group) => [String(group.id), group.name] as const
      )
    );
    return formatAlertOrganizationPath(team, pathById, nameById);
  }, [team, userInfo?.flatGroups, userInfo?.groupTree]);

  return (
    <div className="flex min-w-0 flex-col gap-0.5">
      <EllipsisWithTooltip
        className="min-w-0 truncate text-xs leading-4 text-[var(--color-text-3)]"
        text={organizationPath || '--'}
      />
      {operatorUser ? (
        <UserAvatar userName={operatorUser} size="small" />
      ) : (
        <span className="leading-5 text-[var(--color-text-3)]">--</span>
      )}
    </div>
  );
};

export default OperatorWithOrgCell;
