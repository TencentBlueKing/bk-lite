import React from 'react';

export interface StagedDistributeFile {
  id: number;
  name: string;
  size?: number;
}

const StagedDistributeFiles: React.FC<{
  files: StagedDistributeFile[];
  label: string;
}> = ({ files, label }) => {
  if (!files.length) {
    return null;
  }
  return (
    <div className="flex flex-wrap items-center gap-1.5 px-2.5 pt-2.5" data-testid="staged-distribute-files">
      <span className="text-xs text-[var(--color-text-3)]">{label}</span>
      {files.map((file) => (
        <span
          key={file.id}
          className="max-w-[220px] truncate rounded-md border border-[var(--color-border-1)] bg-[var(--color-fill-2)] px-2 py-1 text-xs text-[var(--color-text-1)]"
          title={file.name}
        >
          {file.name}
        </span>
      ))}
    </div>
  );
};

export default StagedDistributeFiles;
