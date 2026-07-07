'use client';

import React from 'react';
import { Tag } from 'antd';
import { useTranslation } from '@/utils/i18n';

// 贡献来源 ai / human / mixed → 中文标签 + 配色(后端原值为英文,统一在前端映射)
const META: Record<string, { key: string; color: string }> = {
  ai: { key: 'wiki.contributionAi', color: 'blue' },
  human: { key: 'wiki.contributionHuman', color: 'green' },
  mixed: { key: 'wiki.contributionMixed', color: 'gold' },
};

const ContributionTag: React.FC<{ value?: string }> = ({ value }) => {
  const { t } = useTranslation();
  const m = META[value || ''];
  return <Tag color={m?.color}>{m ? t(m.key) : value || '-'}</Tag>;
};

export default ContributionTag;
