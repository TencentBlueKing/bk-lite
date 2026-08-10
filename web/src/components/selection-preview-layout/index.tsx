'use client';

import React from 'react';
import { CloseOutlined } from '@ant-design/icons';
import { useTranslation } from '@/utils/i18n';
import styles from './index.module.scss';

export interface SelectionPreviewItem {
  key: string;
  label: React.ReactNode;
}

export interface SelectionPreviewLayoutProps {
  primary: React.ReactNode;
  items: SelectionPreviewItem[];
  onClear: () => void;
  onRemove: (key: string) => void;
  emptyText?: React.ReactNode;
  previewTitle?: React.ReactNode;
  clearText?: React.ReactNode;
  footer?: React.ReactNode;
  className?: string;
  primaryClassName?: string;
  previewClassName?: string;
  previewHeaderClassName?: string;
  listClassName?: string;
  showClearWhenEmpty?: boolean;
  primaryWidth?: number;
  listHeight?: string;
}

const SelectionPreviewLayout = ({
  primary,
  items,
  onClear,
  onRemove,
  emptyText,
  previewTitle,
  clearText,
  footer,
  className = '',
  primaryClassName = '',
  previewClassName = '',
  previewHeaderClassName = '',
  listClassName = '',
  showClearWhenEmpty = true,
  primaryWidth = 550,
  listHeight,
}: SelectionPreviewLayoutProps) => {
  const { t } = useTranslation();
  const resolvedEmptyText = emptyText ?? t('common.noData');
  const resolvedPreviewTitle = previewTitle ?? (
    <>
      {t('common.selected')}(
      <span className="text-[var(--color-primary)] px-[4px]">
        {items.length}
      </span>
      {t('common.items')})
    </>
  );
  const resolvedClearText = clearText ?? t('common.clear');

  return (
    <div
      className={`${styles.layout} ${className}`.trim()}
      style={
        {
          ['--selection-preview-primary-width' as string]: `${primaryWidth}px`,
          ['--selection-preview-list-height' as string]: listHeight || 'auto',
        } as React.CSSProperties
      }
    >
      <div className={`${styles.primary} ${primaryClassName}`.trim()}>{primary}</div>
      <div className={`${styles.preview} ${previewClassName}`.trim()}>
        <div className={`${styles.previewHeader} ${previewHeaderClassName}`.trim()}>
          <span>{resolvedPreviewTitle}</span>
          {(items.length > 0 || showClearWhenEmpty) ? (
            <button
              className={styles.clearAction}
              type="button"
              onClick={onClear}
              disabled={!items.length}
            >
              {resolvedClearText}
            </button>
          ) : null}
        </div>
        {items.length ? (
          <ul className={`${styles.list} ${listClassName}`.trim()}>
            {items.map((item) => (
              <li className={styles.listItem} key={item.key}>
                <div className={styles.label}>{item.label}</div>
                <button
                  className={styles.remove}
                  type="button"
                  aria-label={t('common.delete')}
                  onClick={() => onRemove(item.key)}
                >
                  <CloseOutlined />
                </button>
              </li>
            ))}
          </ul>
        ) : (
          <div className={styles.emptyState}>{resolvedEmptyText}</div>
        )}
        {footer ? <div>{footer}</div> : null}
      </div>
    </div>
  );
};

export default SelectionPreviewLayout;
