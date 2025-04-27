import React, { useState } from 'react';
import { Drawer, Tooltip, Spin } from 'antd';
import { KnowledgeBase } from '@/app/opspilot/types/global';
import Icon from '@/components/icon';
import styles from './index.module.scss';
import { useTranslation } from '@/utils/i18n';
import KnowledgeResultItem from '@/app/opspilot/components/block-result';
import { useKnowledgeApi } from '@/app/opspilot/api/knowledge';

interface KnowledgeItem {
  citing_num: number;
  knowledge_id: number;
  knowledge_base_id: number;
  knowledge_source_type: string;
  knowledge_title: string;
  result: Array<{
    score: number;
    content: string;
  }>
}

interface KnowledgeBaseProps {
  knowledgeList?: KnowledgeBase[];
}

const KnowledgeBaseComp: React.FC<KnowledgeBaseProps> = ({ knowledgeList }) => {
  const { t } = useTranslation();
  const { fetchKnowledgeBaseDetails } = useKnowledgeApi(); // Use the API function
  const [isDrawerVisible, setIsDrawerVisible] = useState(false);
  const [currentResult, setCurrentResult] = useState<KnowledgeItem | null>(null);
  const [knowledgeBaseTitle, setKnowledgeBaseTitle] = useState<string>('');
  const [knowledgeBaseDesc, setKnowledgeBaseDesc] = useState<string>('');
  const [loading, setLoading] = useState<boolean>(false);

  const showDrawer = async (item: KnowledgeItem) => {
    setCurrentResult(item);
    setIsDrawerVisible(true);
    setLoading(true);
    try {
      const data = await fetchKnowledgeBaseDetails(item.knowledge_base_id);
      setKnowledgeBaseTitle(data.name);
      setKnowledgeBaseDesc(data.introduction);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const onClose = () => {
    setIsDrawerVisible(false);
  };

  const getIconByType = (type: string) => {
    const iconMap: { [key: string]: string } = {
      manual: 'wenben',
      file: 'wendang',
      web_page: 'icon-wangzhantuiguang'
    };
    return iconMap[type] || 'wendang';
  };

  const handleNavigateToDetail = () => {
    const url = `/opspilot/knowledge/detail/documents?id=${currentResult?.knowledge_base_id}&name=${knowledgeBaseTitle}&desc=${knowledgeBaseDesc}`;
    window.open(url, '_blank');
  };

  return (
    <div className="mt-4 flex flex-wrap gap-4">
      {knowledgeList && knowledgeList.length && (
        knowledgeList.map((item, index) => (
          <div
            key={index}
            className={`p-2 rounded-lg cursor-pointer flex justify-between items-center text-xs w-[120px] h-[32px] ${styles.knowledgeItem}`}
            onClick={() => showDrawer(item)}
          >
            <Tooltip title={item.knowledge_title}>
              <div className={`flex flex-1 items-center truncate ${styles.title}`}>
                <Icon className='text-sm mr-1' type={getIconByType(item.knowledge_source_type)} />
                <span className="overflow-hidden overflow-ellipsis whitespace-nowrap">
                  {item.knowledge_title}
                </span>
              </div>
            </Tooltip>
            <div className={styles.references}>
              {item.citing_num}
            </div>
          </div>
        ))
      )}

      {currentResult && (
        <Drawer
          title={t('chat.knowledgeDetails')}
          placement="right"
          onClose={onClose}
          visible={isDrawerVisible}
          width={600}
        >
          <Spin spinning={loading}>
            <div className="space-y-4">
              {currentResult.result.map((result, index) => (
                <KnowledgeResultItem
                  key={index}
                  result={{
                    id: index,
                    score: result.score,
                    content: result.content,
                    knowledge_source_type: currentResult.knowledge_source_type,
                    name: currentResult.knowledge_title,
                  }}
                  index={index}
                  slot={<p onClick={handleNavigateToDetail} className={`${styles.knowledgeTitle} flex items-center`}>
                    <Icon type="zhishiku" className='mr-1' />
                    {knowledgeBaseTitle}
                  </p>}
                  onClick={() => {}}
                />
              ))}
            </div>
          </Spin>
        </Drawer>
      )}
    </div>
  );
};

export default KnowledgeBaseComp;
