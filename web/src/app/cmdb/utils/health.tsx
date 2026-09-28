import React from 'react';
import { Tag } from 'antd';

export type HealthStatusType = 'OK' | 'Warning' | 'Critical' | 'Unknown';

export const normalizeHealthStatus = (value: unknown): HealthStatusType | null => {
  if (value === null || value === undefined) return null;
  const str = String(value).trim();
  if (!str) return null;
  const upper = str.toUpperCase();
  if (upper === 'OK' || upper === 'HEALTHY' || upper === 'GOOD') {
    return 'OK';
  }
  if (upper === 'WARNING' || upper === 'WARN') {
    return 'Warning';
  }
  if (upper === 'CRITICAL' || upper === 'ERROR' || upper === 'DANGER') {
    return 'Critical';
  }
  if (upper === 'UNKNOWN' || upper === 'ABSENT') {
    return 'Unknown';
  }
  return str as HealthStatusType;
};

export const getHealthTagProps = (status: HealthStatusType | string) => {
  const upper = String(status || '').toUpperCase();
  switch (upper) {
    case 'OK':
    case 'HEALTHY':
    case 'GOOD':
      return { color: 'success', text: 'OK' };
    case 'WARNING':
    case 'WARN':
      return { color: 'warning', text: 'Warning' };
    case 'CRITICAL':
    case 'ERROR':
    case 'DANGER':
      return { color: 'error', text: 'Critical' };
    case 'UNKNOWN':
    case 'ABSENT':
      return { color: 'default', text: 'Unknown' };
    default:
      return { color: 'default', text: String(status) };
  }
};

export const HealthStatusTag: React.FC<{ value: unknown }> = ({ value }) => {
  if (value === null || value === undefined || value === '') {
    return <span className="text-[var(--color-text-3)]">--</span>;
  }
  const tagProps = getHealthTagProps(String(value));
  return <Tag color={tagProps.color}>{tagProps.text}</Tag>;
};

export const formatPowerState = (value: unknown): string => {
  if (value === null || value === undefined || value === '') {
    return '--';
  }
  const str = String(value).trim();
  const lower = str.toLowerCase();
  if (lower === 'on' || lower === '1' || lower === 'poweringon') {
    return 'On';
  }
  if (lower === 'off' || lower === '0' || lower === 'poweringoff') {
    return 'Off';
  }
  return str;
};
