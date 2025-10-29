import React, { ReactNode } from 'react';
import { ResultItem } from '@/app/opspilot/types/global';
import { Tag } from 'antd';
import Icon from '@/components/icon';
import globalStyles from '@/app/opspilot/styles/common.module.scss';
import { useTranslation } from '@/utils/i18n';

interface BlockResultItemProps {
  result: ResultItem;
  index: number;
  onClick: (content: string) => void;
  slot?: ReactNode;
  showScore?: boolean;
}

const BlockResultItem: React.FC<BlockResultItemProps> = ({ 
  result, 
  index, 
  onClick, 
  slot,
  showScore = true 
}) => {
  const { t } = useTranslation();

  const getIconByType = (type: string) => {
    const iconMap: { [key: string]: string } = {
      manual: 'wenben',
      file: 'wendang',
      web_page: 'icon-wangzhantuiguang',
    };
    return iconMap[type] || 'wendang';
  };

  return (
    <div
      key={result.id}
      className={`p-4 border rounded-md ${globalStyles.resultsItem}`}
      onClick={() => onClick(result.content)}
    >
      <div className="flex justify-between mb-2">
        <div className="border px-2 rounded-md">
          <span className={`text-xs ${globalStyles.activeTxt}`}># {index + 1}</span>
          <span className="ml-2 text-xs">| {t('knowledge.ranking')}</span>
        </div>
        <div className="flex items-center space-x-2 text-sm text-gray-500">
          {showScore && (
            <Tag color="geekblue" className="font-mini">
              {t('knowledge.score')}: {result.score.toFixed(4)}
            </Tag>
          )}
        </div>
      </div>
      <p className={`text-sm ${globalStyles.content} mb-2`}>{result.content}</p>
      <div className="flex items-center text-sm justify-between">
        <p className={`flex text-sm ${globalStyles.activeTxt}`}>
          <Icon type={getIconByType(result.knowledge_source_type)} className="text-xl pr-1" />{result.name}
        </p>
        {slot && (
          <div className="ml-2">{slot}</div>
        )}
      </div>
    </div>
  );
};

export default BlockResultItem;
