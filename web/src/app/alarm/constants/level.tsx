import React from 'react';
import LevelIcon from '@/app/alarm/components/levelIcon';
import { NEUTRAL } from '@/app/alarm/constants/colors';

export const DEFAULT_LEVEL_ICONS = [
  'huoyanhuodongtuijian',
  'weiwangguanicon-defuben-',
  'gantanhao1',
  'tixing',
];

export const DEFAULT_LEVEL_COLORS = [
  '#F43B2C',
  '#D97007',
  '#FFAD42',
  '#FBBF24',
  '#2F6BFF',
  '#13C2C2',
  '#7A45FF',
  '#9E9E9E',
];

export const renderLevelIconOption = (icon: string, color?: string) => (
  <div
    className="flex h-7 w-7 items-center justify-center rounded-md"
    style={{ backgroundColor: color || DEFAULT_LEVEL_COLORS[0] }}
  >
    <LevelIcon icon={icon} className="h-4 w-4" style={{ color: NEUTRAL.ON_DARK_FG }} />
  </div>
);
