import React, { useState } from 'react';
// import { Button } from 'antd';
import { NodeType } from '@/app/mlops/types';
// import { UpOutlined, DownOutlined } from '@ant-design/icons';
import Icon from '@/components/icon';
import { useTranslation } from '@/utils/i18n';

interface NodePanelProps {
  nodeTypes: NodeType[];
  onDragStart: (event: React.DragEvent, nodeType: string) => void;
}

const NodePanel: React.FC<NodePanelProps> = ({ onDragStart, nodeTypes }) => {
  const { t } = useTranslation();
  const [showDetail, setShowDetail] = useState<boolean>(false);

  // const handleClick = (event: any, nodeType: any) => {
  //   setShowDetail(false);
  //   onDragStart(event, nodeType);
  // }

  return (
    <div
      className={`
        w-[48px] absolute
        rounded-[10px]
        left-[20px]
        top-[50%]
        translate-y-[-45%]
        bg-[var(--color-bg)]
        border
        z-10
        shadow-lg
        `}
    >
      <div className="flex flex-row">
        <div className="flex-1">
          <div className="flex flex-col items-center justify-center">
            <div
              className={`flex flex-col my-1 items-center py-2 px-[6px] justify-center h-[32px] rounded-lg ${showDetail && 'bg-sky-100'} hover:bg-sky-100`}
              // onDragStart={(event) => onDragStart(event, nodeType.type)}
              onClick={() => setShowDetail(prev => !prev)}
            >
              <Icon type={'tianjia'} className='!w-5 !h-5 text-blue-600 flex-shrink-0' />
            </div>
            {nodeTypes.map((nodeType: NodeType) => (
              <div
                key={nodeType.type}
                className="flex flex-col my-[2px] items-center py-2 px-[6px] justify-center h-[32px] rounded-lg  hover:bg-sky-100"
                draggable
                onDragStart={(event) => onDragStart(event, nodeType.type)}
              >
                <Icon type={nodeType.icon} className='!w-5 !h-5 text-blue-600 flex-shrink-0' />
              </div>
            ))}
          </div>
        </div>
      </div>
      {/* 详细节点面板 */}
      {showDetail && (
        <div className='
        absolute top-[50%] translate-y-[-50%] 
        p-2 w-[156px] right-[-160px] 
        rounded-[10px] z-20 border 
        bg-[var(--color-bg)] shadow-lg'
        >
          <span className='font-xs text-xs text-[var(--color-text-3)]'>{t(`common.node`)}</span>
          {nodeTypes.map((nodeType: NodeType) => (
            <div
              key={nodeType.type}
              className="flex flex-row items-center justify-start my-2 min-w-[140px] w-[140px] h-[40px] px-3 py-2 rounded-lg border-gray-200 bg-[var(--color-bg)] hover:bg-gray-100 hover:border-blue-300 transition-all cursor-grab active:cursor-grabbing select-none"
              draggable
              // onClick={(event) => handleClick(event, nodeType.type)}
              onDragStart={(event) => onDragStart(event, nodeType.type)}>
              <Icon type={nodeType.icon} className='!w-6 !h-6 mr-3 text-blue-600 flex-shrink-0' />
              <span className="text-xs text-gray-700 font-medium leading-tight flex-1">
                {nodeType.label}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

export default NodePanel;