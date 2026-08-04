/**
 * Enterprise stub - 社区版的空模块占位
 * 当 enterprise 目录不存在时，TypeScript 会 fallback 到这个文件
 */
import type { ComponentType } from 'react';
import type { IncidentTableDataItem } from '@/app/alarm/types/incidents';

interface IncidentCollaborationExtensionProps {
  incidentPk: string;
  incidentDetail?: IncidentTableDataItem;
  refreshVersion: number;
}

export const useEnterpriseConfig = (): Record<string, unknown> => ({});
export const IncidentCollaborationExtension:
  | ComponentType<IncidentCollaborationExtensionProps>
  | null = null;
export const INCIDENT_COLLABORATION_SIDEBAR_WIDTH_CLASS = 'w-full lg:w-[300px]';

const enterpriseStub = {};
export default enterpriseStub;
