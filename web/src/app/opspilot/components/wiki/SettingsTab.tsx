'use client';

import React from 'react';
import { Spin } from 'antd';

// 设置工作区(spec 4.6)。占位:下一步补齐 用途/结构/模型/生成规则/网页同步/风险审核/权限/危险操作。
const SettingsTab: React.FC<{ kbId: number }> = () => {
  return (
    <div className="py-10 text-center">
      <Spin />
    </div>
  );
};

export default SettingsTab;
