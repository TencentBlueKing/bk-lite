import { useMemo } from 'react';
import { useTheme } from '@/context/theme';

export interface ChartColors {
  axisLine: string;
  splitLine: string;
  axisLabel: string;
  background: string;
  tooltipBg: string;
  tooltipBorder: string;
  textPrimary: string;
  textSecondary: string;
  textTertiary: string;
  primary: string;
  success: string;
  warning: string;
  danger: string;
  series: string[];
  gradientAlpha: [number, number];
}

const lightColors: ChartColors = {
  axisLine: '#e8e8e8',
  splitLine: '#f0f0f0',
  axisLabel: '#7f92a7',
  background: '#ffffff',
  tooltipBg: '#ffffff',
  tooltipBorder: '#e8e8e8',
  textPrimary: '#1d2b3a',
  textSecondary: '#5a6d7f',
  textTertiary: '#7f92a7',
  primary: '#155AEF',
  success: '#52c41a',
  warning: '#faad14',
  danger: '#f5222d',
  series: ['#155AEF', '#36BFFA', '#15B77E', '#F97316', '#EF4444', '#8B5CF6', '#EC4899', '#F59E0B'],
  gradientAlpha: [0.25, 0.02],
};

const darkColors: ChartColors = {
  axisLine: '#3a3a3a',
  splitLine: '#2a2a2a',
  axisLabel: '#8a9bb0',
  background: '#141414',
  tooltipBg: '#1f1f1f',
  tooltipBorder: '#3a3a3a',
  textPrimary: '#e8ecf0',
  textSecondary: '#a0aebe',
  textTertiary: '#8a9bb0',
  primary: '#3B82F6',
  success: '#4ade80',
  warning: '#fbbf24',
  danger: '#ef4444',
  series: ['#3B82F6', '#36BFFA', '#34D399', '#FB923C', '#F87171', '#A78BFA', '#F472B6', '#FBBF24'],
  gradientAlpha: [0.3, 0.02],
};

const useChartColors = (): ChartColors => {
  const { themeName } = useTheme();

  return useMemo(
    () => (themeName === 'dark' ? darkColors : lightColors),
    [themeName]
  );
};

export default useChartColors;
