'use client';

import React from 'react';
import type { UploadFile } from 'antd/es/upload/interface';
import ImportFileModalShell from '@/components/import-file-modal-shell';

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
  return (
    <ImportFileModalShell
      title="导入技能包"
      open={open}
      width={760}
      confirmText="确认导入"
      cancelText="取消"
      confirmDisabled={fileList.length === 0}
      onConfirm={onConfirm}
      onCancel={onCancel}
      beforeUploadPanel={(
        <div className="mb-4 rounded-lg border border-[var(--color-border)] bg-[var(--color-fill-1)] px-4 py-3 text-sm leading-6 text-[var(--color-text-2)]">
          上传 ZIP 技能包。包内必须包含 <code>SKILL.md</code>，可选 <code>skill.yaml</code>、<code>references/</code>、<code>templates/</code> 等目录。没有 <code>skill.yaml</code> 时会读取 <code>SKILL.md</code> 顶部 YAML frontmatter，或从标题和目录名推导基础信息。
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
        uploadText: '点击或拖拽 ZIP 技能包到这里',
        uploadHint: '第一版支持本地 ZIP 上传；公开 Git 仓库导入后续接入同一导入器。',
      }}
    />
  );
};

export default SkillImportModal;
