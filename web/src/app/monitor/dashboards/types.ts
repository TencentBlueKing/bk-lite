import { ComponentType } from 'react';

export type ProfessionalDashboardComponent = ComponentType;

export interface ProfessionalDashboardRegistryItem {
  key: string;
  objectName: string;
  objectDisplayName?: string;
  inheritedPermissionPath?: string;
  component: ProfessionalDashboardComponent;
}
