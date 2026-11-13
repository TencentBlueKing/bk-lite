'use client';

import {
  ApartmentOutlined, AuditOutlined, BellOutlined, BookOutlined, BranchesOutlined,
  DeploymentUnitOutlined, FileAddOutlined, FlagOutlined, ForkOutlined, FunctionOutlined,
  PlayCircleOutlined, RobotOutlined, SendOutlined, SettingOutlined, ThunderboltOutlined,
  UserOutlined,
} from '@ant-design/icons';
import type { ComponentType } from 'react';

interface NodeVisual { icon: ComponentType; tone: string }
const BLUE = 'text-[var(--color-primary)] bg-[color-mix(in_srgb,var(--color-primary)_10%,var(--color-bg))]';
const GREEN = 'text-[var(--color-success)] bg-[color-mix(in_srgb,var(--color-success)_10%,var(--color-bg))]';
const AMBER = 'text-[var(--color-warning)] bg-[color-mix(in_srgb,var(--color-warning)_10%,var(--color-bg))]';
const NEUTRAL = 'text-[var(--color-text-2)] bg-[var(--color-fill-1)]';
const VISUALS: Record<string, NodeVisual> = {
  start: { icon: PlayCircleOutlined, tone: GREEN }, end: { icon: FlagOutlined, tone: NEUTRAL },
  submit: { icon: FileAddOutlined, tone: BLUE }, approval: { icon: AuditOutlined, tone: AMBER },
  manual: { icon: UserOutlined, tone: BLUE }, handle: { icon: UserOutlined, tone: BLUE }, auto: { icon: RobotOutlined, tone: GREEN },
  decision: { icon: FunctionOutlined, tone: AMBER }, notice: { icon: BellOutlined, tone: AMBER },
  parallel: { icon: ForkOutlined, tone: BLUE }, parallel_condition: { icon: ForkOutlined, tone: AMBER },
  branch: { icon: BranchesOutlined, tone: BLUE }, branch_condition: { icon: BranchesOutlined, tone: AMBER },
  exclusive: { icon: BranchesOutlined, tone: AMBER }, converge: { icon: DeploymentUnitOutlined, tone: BLUE },
  manual_trigger: { icon: ThunderboltOutlined, tone: BLUE }, rule_trigger: { icon: SettingOutlined, tone: AMBER },
  auto_dispatch: { icon: SendOutlined, tone: GREEN }, subprocess: { icon: ApartmentOutlined, tone: BLUE },
  subprocess_submit: { icon: FileAddOutlined, tone: GREEN }, subprocess_handle: { icon: ApartmentOutlined, tone: AMBER },
  knowledge: { icon: BookOutlined, tone: GREEN },
};

/** 设计器、节点库与工单流程图共用类型标识；状态仍由节点边框表达。 */
export function NodeGlyph({ type, compact = false }: { type: string; compact?: boolean }) {
  const { icon: Icon, tone } = VISUALS[type] || { icon: ApartmentOutlined, tone: NEUTRAL };
  return <span aria-hidden="true" className={`inline-flex shrink-0 items-center justify-center rounded-lg ${compact ? 'h-6 w-6 text-sm' : 'h-8 w-8 text-lg'} ${tone}`}><Icon /></span>;
}
