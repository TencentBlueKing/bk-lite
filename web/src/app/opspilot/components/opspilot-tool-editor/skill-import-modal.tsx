'use client';

import React from 'react';
import type { UploadFile } from 'antd/es/upload/interface';
import ImportFileModalShell from '@/components/import-file-modal-shell';
import { useTranslation } from '@/utils/i18n';

export interface SkillImportModalProps {
  open: boolean;
  fileList: UploadFile[];
  onFileListChange: (fileList: UploadFile[]) => void;
  onConfirm: () => void;
  onCancel: () => void;
}

const SkillImportModal: React.FC<SkillImportModalProps> = ({
  open,
  fileList,
  onFileListChange,
  onConfirm,
  onCancel,
}) => {
  const { t } = useTranslation();

  return (
    <ImportFileModalShell
      title={t('skill.import.title', '导入技能包')}
      open={open}
      width={760}
      confirmText={t('skill.import.confirm', '确认导入')}
      cancelText={t('common.cancel', '取消')}
      confirmDisabled={fileList.length === 0}
      onConfirm={onConfirm}
      onCancel={onCancel}
      beforeUploadPanel={(
        <div className="mb-4 rounded-lg border border-[var(--color-border)] bg-[var(--color-fill-1)] px-4 py-3 text-sm leading-6 text-[var(--color-text-2)]">
          {t('skill.import.introLead', '上传 ZIP 技能包。包内必须包含 ')}
          <code>SKILL.md</code>
          {t('skill.import.introOptional', '，可选 ')}
          <code>skill.yaml</code>
          {t('skill.import.introSep', '、')}
          <code>references/</code>
          {t('skill.import.introSep', '、')}
          <code>templates/</code>
          {t('skill.import.introDirs', ' 等目录。没有 ')}
          <code>skill.yaml</code>
          {t('skill.import.introRead', ' 时会读取 ')}
          <code>SKILL.md</code>
          {t('skill.import.introEnd', ' 顶部 YAML frontmatter，或从标题和目录名推导基础信息。')}
        </div>
      )}
      uploadProps={{
        accept: '.zip',
        maxCount: 1,
        fileList,
        beforeUpload: (file) => {
          onFileListChange([file as UploadFile]);
          return false;
        },
        onRemove: () => {
          onFileListChange([]);
        },
        uploadText: t('skill.import.uploadText', '点击或拖拽 ZIP 技能包到这里'),
        uploadHint: t('skill.import.uploadHint', '第一版支持本地 ZIP 上传；公开 Git 仓库导入后续接入同一导入器。'),
      }}
    />
  );
};

export default SkillImportModal;
