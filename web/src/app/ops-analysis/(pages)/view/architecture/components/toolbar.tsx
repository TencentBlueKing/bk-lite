import React from 'react';
import { Button, Tooltip } from 'antd';
import { SaveOutlined, EditOutlined } from '@ant-design/icons';
import { ArchitectureProps } from '@/app/ops-analysis/types/architecture';

interface ArchitectureToolbarProps {
  selectedArchitecture: ArchitectureProps['selectedArchitecture'];
  isEditMode: boolean;
  loading: boolean;
  onEdit: () => void;
  onSave: () => void;
}

const ArchitectureToolbar: React.FC<ArchitectureToolbarProps> = ({
  selectedArchitecture,
  isEditMode,
  loading,
  onEdit,
  onSave,
}) => {
  return (
    <div className="w-full mb-2 flex items-center justify-between rounded-lg shadow-sm p-3 border border-gray-200 bg-white">
      {/* 左侧：架构图信息 */}
      <div className="flex-1 mr-8">
        {selectedArchitecture && (
          <div className="p-1 pt-0">
            <h2 className="text-lg font-semibold mb-1">
              {selectedArchitecture.name}
            </h2>
            <p className="text-sm text-gray-500">
              {selectedArchitecture.desc || '--'}
            </p>
          </div>
        )}
      </div>

      {/* 右侧：工具栏 */}
      <div className="flex items-center space-x-2">
        {isEditMode ? (
          <Button
            icon={<SaveOutlined />}
            loading={loading}
            onClick={onSave}
            type="primary"
          >
            保存
          </Button>
        ) : (
          <Tooltip title="编辑">
            <Button
              type="text"
              icon={<EditOutlined style={{ fontSize: 16 }} />}
              onClick={onEdit}
            />
          </Tooltip>
        )}
      </div>
    </div>
  );
};

export default ArchitectureToolbar;
