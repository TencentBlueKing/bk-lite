'use client';

import React, { type ReactNode } from 'react';
import styles from './index.module.scss';

interface SystemManagerFillTableProps {
  children: ReactNode;
  className?: string;
}

export default function SystemManagerFillTable({
  children,
  className = '',
}: SystemManagerFillTableProps) {
  return (
    <div className={`min-h-0 h-full min-w-0 flex-1 overflow-hidden ${styles.fill} ${className}`}>
      {children}
    </div>
  );
}
