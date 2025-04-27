import React, { useState, useEffect } from 'react';
import { Button, Slider, Input, Tooltip } from 'antd';
import { EditOutlined, DeleteOutlined } from '@ant-design/icons';
import { useTranslation } from '@/utils/i18n';
import { getIconTypeByIndex } from '@/app/opspilot/utils/knowledgeBaseUtils';
import { KnowledgeBase, KnowledgeBaseRagSource } from '@/app/opspilot/types/skill';
import Icon from '@/components/icon';
import SkillOperateModal from './operateModal';
import styles from './index.module.scss';

interface KnowledgeBaseSelectorProps {
  knowledgeBases: KnowledgeBase[];
  selectedKnowledgeBases: number[];
  setSelectedKnowledgeBases: React.Dispatch<React.SetStateAction<number[]>>;
  ragSources?: KnowledgeBaseRagSource[];
  setRagSources?: React.Dispatch<React.SetStateAction<KnowledgeBaseRagSource[]>>;
  showScore?: boolean;
}

const KnowledgeBaseSelector: React.FC<KnowledgeBaseSelectorProps> = ({
  knowledgeBases,
  selectedKnowledgeBases,
  setSelectedKnowledgeBases,
  ragSources = [],
  setRagSources,
  showScore = true,
}) => {
  const { t } = useTranslation();
  const [modalVisible, setModalVisible] = useState(false);

  useEffect(() => {
    setRagSources?.(ragSources);
  }, [ragSources, setRagSources]);

  const handleScoreChange = (sourceName: string, newScore: number) => {
    setRagSources?.(prevRagSources =>
      prevRagSources.map(source =>
        source.name === sourceName ? { ...source, score: newScore } : source
      )
    );
  };

  const handleDeleteRagSource = (sourceName: string) => {
    const updateRagSources = (prevRagSources: KnowledgeBaseRagSource[]): KnowledgeBaseRagSource[] =>
      prevRagSources.filter(item => item.name !== sourceName);

    setRagSources?.(prev => updateRagSources(prev || []));
    const source = knowledgeBases.find(base => base.name === sourceName);
    if (source) {
      setSelectedKnowledgeBases(prev => prev.filter(id => id !== source.id));
    }
  };

  const handleModalOk = (newSelectedKnowledgeBases: number[]) => {
    setSelectedKnowledgeBases(newSelectedKnowledgeBases);
    setRagSources?.(prevRagSources => {
      const existingRagSources = prevRagSources.filter(
        ragSource => newSelectedKnowledgeBases.includes(ragSource.id)
      );
      const newRagSources = newSelectedKnowledgeBases
        .filter(id => !prevRagSources.some(ragSource => ragSource.id === id))
        .map(id => {
          const base = knowledgeBases.find(base => base.id === id);
          return base
            ? { id: base.id, name: base.name, introduction: base.introduction || '', score: 0.7 }
            : null;
        })
        .filter(Boolean) as KnowledgeBaseRagSource[];

      return [...existingRagSources, ...newRagSources];
    });
    setModalVisible(false);
  };

  const handleModalCancel = () => {
    setModalVisible(false);
  };

  return (
    <div>
      <Button className='mb-2' type="dashed" onClick={() => setModalVisible(true)}>
        + {t('common.add')}
      </Button>
      <div className={`${!showScore ? 'space-between grid grid-cols-2 gap-2' : ''}`}>
        {ragSources.length > 0 && (
          ragSources.map((source, index) => (
            <div key={index} className='w-full mt-2 flex space-between'>
              <div className={`w-full rounded-md px-4 py-2 flex items-center justify-between ${styles.borderContainer}`}>
                <Tooltip title={source.name}>
                  <div className='flex items-center'>
                    {!showScore && (<Icon className='text-sm mr-1' type={getIconTypeByIndex(index)} />)}
                    <span className={`inline-block text-ellipsis overflow-hidden whitespace-nowrap ${showScore ? 'w-24' : 'w-48'}`}>{source.name}</span>
                  </div>
                </Tooltip>
                {showScore && (
                  <div className="flex-1 flex items-center ml-2 gap-4 mr-2">
                    <Slider
                      className="flex-1 mx-2"
                      min={0}
                      max={1}
                      step={0.01}
                      value={source.score}
                      onChange={(value) => handleScoreChange(source.name, value)}
                    />
                    <Input className="w-16" value={source.score} readOnly />
                  </div>
                )}
                <div className="flex items-center space-x-2">
                  <EditOutlined onClick={() => window.open(`/opspilot/knowledge/detail?id=${source.id}&name=${source.name}&desc=${source.introduction}`, '_blank')} />
                  <DeleteOutlined onClick={() => handleDeleteRagSource(source.name)} />
                </div>
              </div>
            </div>
          ))
        )}
      </div>
      <SkillOperateModal
        visible={modalVisible}
        okText={t('common.confirm')}
        cancelText={t('common.cancel')}
        onOk={handleModalOk}
        onCancel={handleModalCancel}
        options={knowledgeBases}
        selectedOptions={selectedKnowledgeBases}
      />
    </div >
  );
};

export default KnowledgeBaseSelector;
