'use client';

import React from 'react';
import { Card } from 'antd';
import introductionStyle from './index.module.scss';

interface IntroductionProp {
  message: string;
  title: string;
}

const Introduction: React.FC<IntroductionProp> = ({ message, title }) => (
  <Card
    className={`${introductionStyle.introduction} mb-[16px]`}
    style={{ width: '100%', minWidth: '800px' }}
  >
    <p className="font-extrabold text-base">{title}</p>
    <p className={`text-sm mt-[10px] sub-name ${introductionStyle.subName}`}>
      {message}
    </p>
  </Card>
);

export default Introduction;
