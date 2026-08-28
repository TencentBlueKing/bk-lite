'use client';

import React from 'react';
import { CollectProtocolBar } from './collect-protocol-bar';
import { DashboardProtocolBarPortal } from './dashboard-protocol-bar-slot';
import dashboardStyles from '../../objects/common/simple-dashboard.module.scss';

/** layout 级挂载：跨 objectKey 保活，portal 到 DashboardShell 实例卡下方 slot。 */
export function DashboardProtocolBarHost() {
  return (
    <DashboardProtocolBarPortal>
      <CollectProtocolBar styles={dashboardStyles} />
    </DashboardProtocolBarPortal>
  );
}
