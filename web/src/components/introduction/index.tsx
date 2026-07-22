'use client';

import React from 'react';
import { Card } from 'antd';
import introductionStyle from './index.module.scss';

interface IntroductionProp {
  message: string;
  title: string;
  minWidth?: string | number;
  spacing?: 'compact' | 'normal' | 'flush';
  className?: string;
}

const Introduction: React.FC<IntroductionProp> = ({ message, title, minWidth, spacing, className }) => (
  <Card
    className={`${introductionStyle.introduction} ${className ?? ''} ${spacing === 'compact' ? 'mb-2' : spacing === 'flush' ? 'mb-0' : 'mb-[16px]'}`}
    style={{ width: '100%', minWidth: minWidth ?? 800 }}
  >
    <p className="font-extrabold text-base">{title}</p>
    <p className={`text-sm mt-[10px] sub-name ${introductionStyle.subName}`}>
      {message}
    </p>
  </Card>
);

export default Introduction;
