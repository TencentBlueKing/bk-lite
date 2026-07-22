'use client';

import React, { useEffect, useState } from 'react';
import { Button, Descriptions, Drawer, Space, Spin } from 'antd';

export interface KnowledgeQAPair {
  id: string;
  question: string;
  answer: string;
  base_chunk_id?: string;
}

export interface KnowledgeChunkDetail {
  title?: string;
  index_name?: string;
  content?: string;
}

export interface KnowledgeQADetailDrawerProps {
  visible: boolean;
  onClose: () => void;
  knowledgeId: string;
  qaPair: KnowledgeQAPair;
  onUpdate?: (next: KnowledgeQAPair) => Promise<void> | void;
  onDelete?: (qaId: string) => Promise<void> | void;
  getChunkDetailAction?: (chunkId: string) => Promise<KnowledgeChunkDetail>;
}

const KnowledgeQADetailDrawer: React.FC<KnowledgeQADetailDrawerProps> = ({
  visible,
  onClose,
  knowledgeId,
  qaPair,
  onUpdate,
  onDelete,
  getChunkDetailAction,
}) => {
  const [chunkDetail, setChunkDetail] = useState<KnowledgeChunkDetail | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!visible || !qaPair.base_chunk_id || !getChunkDetailAction) {
      setChunkDetail(null);
      return;
    }
    let cancelled = false;
    setLoading(true);
    getChunkDetailAction(qaPair.base_chunk_id)
      .then((detail) => {
        if (!cancelled) setChunkDetail(detail);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [visible, qaPair.base_chunk_id, getChunkDetailAction]);

  return (
    <Drawer
      open={visible}
      onClose={onClose}
      title={`QA pair · ${knowledgeId}`}
      width={560}
      destroyOnClose
      extra={
        <Space>
          {onUpdate ? (
            <Button onClick={() => onUpdate(qaPair)}>Update</Button>
          ) : null}
          {onDelete ? (
            <Button danger onClick={() => onDelete(qaPair.id)}>
              Delete
            </Button>
          ) : null}
        </Space>
      }
    >
      <Descriptions column={1} size="small" bordered>
        <Descriptions.Item label="Question">{qaPair.question}</Descriptions.Item>
        <Descriptions.Item label="Answer">{qaPair.answer}</Descriptions.Item>
        <Descriptions.Item label="Base chunk">
          {loading ? <Spin size="small" /> : chunkDetail?.title ?? qaPair.base_chunk_id ?? '—'}
        </Descriptions.Item>
        {chunkDetail ? (
          <Descriptions.Item label="Chunk content">
            <div className="whitespace-pre-wrap text-sm">{chunkDetail.content}</div>
          </Descriptions.Item>
        ) : null}
      </Descriptions>
    </Drawer>
  );
};

export default KnowledgeQADetailDrawer;
