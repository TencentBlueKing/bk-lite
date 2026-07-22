'use client';

import React, { useEffect, useState } from 'react';
import { Button, Slider, Input, Tooltip } from 'antd';
import { EditOutlined, DeleteOutlined } from '@ant-design/icons';
import { useTranslation } from '@/utils/i18n';
import type {
  KnowledgeBase,
  KnowledgeBaseRagSource,
} from '@/app/opspilot/components/opspilot-selector-shared';
import { getIconTypeByIndex } from '@/app/opspilot/components/opspilot-selector-shared';
import Icon from '@/components/icon';
import OpspilotSelectorOperateModal from '@/app/opspilot/components/opspilot-selector-operate-modal';
import styles from './index.module.scss';

interface OpspilotKnowledgeBaseSelectorProps {
  knowledgeBases: KnowledgeBase[];
  selectedKnowledgeBases: number[];
  setSelectedKnowledgeBases: React.Dispatch<React.SetStateAction<number[]>>;
  ragSources?: KnowledgeBaseRagSource[];
  setRagSources?: React.Dispatch<React.SetStateAction<KnowledgeBaseRagSource[]>>;
  showScore?: boolean;
}

const OpspilotKnowledgeBaseSelector: React.FC<
  OpspilotKnowledgeBaseSelectorProps
> = ({
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
    setRagSources?.((prevRagSources) =>
      prevRagSources.map((source) =>
        source.name === sourceName ? { ...source, score: newScore } : source,
      ),
    );
  };

  const handleDeleteRagSource = (sourceName: string) => {
    const updateRagSources = (
      prevRagSources: KnowledgeBaseRagSource[],
    ): KnowledgeBaseRagSource[] =>
      prevRagSources.filter((item) => item.name !== sourceName);

    setRagSources?.((prev) => updateRagSources(prev || []));
    const source = knowledgeBases.find((base) => base.name === sourceName);
    if (source) {
      setSelectedKnowledgeBases((prev) => prev.filter((id) => id !== source.id));
    }
  };

  const handleModalOk = (newSelectedKnowledgeBases: number[]) => {
    setSelectedKnowledgeBases(newSelectedKnowledgeBases);
    setRagSources?.((prevRagSources) => {
      const existingRagSources = prevRagSources.filter((ragSource) =>
        newSelectedKnowledgeBases.includes(ragSource.id),
      );
      const newRagSources = newSelectedKnowledgeBases
        .filter((id) => !prevRagSources.some((ragSource) => ragSource.id === id))
        .map((id) => {
          const base = knowledgeBases.find((item) => item.id === id);
          return base
            ? {
              id: base.id,
              name: base.name,
              introduction: base.introduction || '',
              score: 0.7,
            }
            : null;
        })
        .filter(Boolean) as KnowledgeBaseRagSource[];

      return [...existingRagSources, ...newRagSources];
    });
    setModalVisible(false);
  };

  return (
    <div>
      <Button className="mb-2" type="dashed" onClick={() => setModalVisible(true)}>
        + {t('common.add')}
      </Button>
      <div className={`${!showScore ? 'grid grid-cols-2 gap-2 space-between' : ''}`}>
        {ragSources.length > 0 &&
          ragSources.map((source, index) => (
            <div key={index} className="mt-2 flex w-full space-between">
              <div
                className={`flex w-full items-center justify-between rounded-md px-4 py-2 ${styles.borderContainer}`}
              >
                <Tooltip title={source.name}>
                  <div className="flex items-center">
                    {!showScore && (
                      <Icon
                        className="mr-1 text-sm"
                        type={getIconTypeByIndex(index)}
                      />
                    )}
                    <span
                      className={`inline-block overflow-hidden text-ellipsis whitespace-nowrap ${
                        showScore ? 'w-24' : 'w-48'
                      }`}
                    >
                      {source.name}
                    </span>
                  </div>
                </Tooltip>
                {showScore && (
                  <div className="ml-2 mr-2 flex flex-1 items-center gap-4">
                    <Slider
                      className="mx-2 flex-1"
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
                  <EditOutlined
                    onClick={() =>
                      window.open(
                        `/opspilot/knowledge/detail?id=${source.id}&name=${source.name}&desc=${source.introduction}`,
                        '_blank',
                      )
                    }
                  />
                  <DeleteOutlined onClick={() => handleDeleteRagSource(source.name)} />
                </div>
              </div>
            </div>
          ))}
      </div>
      <OpspilotSelectorOperateModal
        visible={modalVisible}
        okText={t('common.confirm')}
        cancelText={t('common.cancel')}
        onOk={handleModalOk}
        onCancel={() => setModalVisible(false)}
        options={knowledgeBases}
        selectedOptions={selectedKnowledgeBases}
      />
    </div>
  );
};

export type { OpspilotKnowledgeBaseSelectorProps };
export default OpspilotKnowledgeBaseSelector;
