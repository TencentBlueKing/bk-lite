import React, { useState, useEffect } from 'react';
import { Drawer, Button, Input, Popconfirm, message, Segmented, Spin, Tag } from 'antd';
import { EditOutlined, CheckOutlined, DeleteOutlined, CloseOutlined } from '@ant-design/icons';
import { useTranslation } from '@/utils/i18n';
import { useKnowledgeApi } from '@/app/opspilot/api/knowledge';

const { TextArea } = Input;

interface QADetailDrawerProps {
  visible: boolean;
  qaPair: {
    id: string;
    question: string;
    answer: string;
    base_chunk_id?: string;
  } | null;
  knowledgeId?: string;
  onClose: () => void;
  onUpdate: (updatedQA: {
    id: string;
    question: string;
    answer: string;
  }) => Promise<void>;
  onDelete: (id: string) => Promise<void>;
}

const QADetailDrawer: React.FC<QADetailDrawerProps> = ({
  visible,
  qaPair,
  knowledgeId,
  onClose,
  onUpdate,
  onDelete,
}) => {
  const { t } = useTranslation();
  const [editingQuestion, setEditingQuestion] = useState(false);
  const [editingAnswer, setEditingAnswer] = useState(false);
  const [question, setQuestion] = useState('');
  const [answer, setAnswer] = useState('');
  const [originalQuestion, setOriginalQuestion] = useState('');
  const [originalAnswer, setOriginalAnswer] = useState('');
  const [updateLoading, setUpdateLoading] = useState(false);
  const [deleteLoading, setDeleteLoading] = useState(false);
  const [chunkDetail, setChunkDetail] = useState<any>(null);
  const [chunkLoading, setChunkLoading] = useState(false);
  const [activeTab, setActiveTab] = useState<string | number>('qa');

  const { getChunkDetail } = useKnowledgeApi();

  useEffect(() => {
    if (visible && qaPair) {
      setQuestion(qaPair.question);
      setAnswer(qaPair.answer);
      setOriginalQuestion(qaPair.question);
      setOriginalAnswer(qaPair.answer);
      setEditingQuestion(false);
      setEditingAnswer(false);
      setActiveTab('qa');
      setChunkDetail(null);
    }
  }, [visible, qaPair]);

  const fetchChunkDetail = async () => {
    console.log('Fetching chunk detail for base_chunk_id:', qaPair?.base_chunk_id, knowledgeId);
    if (!qaPair?.base_chunk_id || !knowledgeId) return;
    
    setChunkLoading(true);
    try {
      const detail = await getChunkDetail(knowledgeId, qaPair.base_chunk_id, 'Document');
      setChunkDetail(detail);
    } catch (error) {
      console.error('Failed to fetch chunk detail:', error);
      message.error(t('common.errorFetch'));
    } finally {
      setChunkLoading(false);
    }
  };

  const handleTabChange = (value: string | number) => {
    setActiveTab(value);
    if (value === 'chunk' && qaPair?.base_chunk_id && !chunkDetail) {
      fetchChunkDetail();
    }
  };

  const handleQuestionEditToggle = () => {
    setEditingQuestion(!editingQuestion);
  };

  const handleAnswerEditToggle = () => {
    setEditingAnswer(!editingAnswer);
  };

  const handleQuestionCancel = () => {
    setQuestion(originalQuestion);
    setEditingQuestion(false);
  };

  const handleAnswerCancel = () => {
    setAnswer(originalAnswer);
    setEditingAnswer(false);
  };

  const handleQuestionUpdate = async () => {
    if (!qaPair) return;
    
    setUpdateLoading(true);
    try {
      await onUpdate({
        ...qaPair,
        question
      });
      message.success(t('common.updateSuccess'));
      setOriginalQuestion(question);
      setEditingQuestion(false);
    } catch (error) {
      console.error('Failed to update question:', error);
      message.error(t('common.updateFailed'));
    } finally {
      setUpdateLoading(false);
    }
  };

  const handleAnswerUpdate = async () => {
    if (!qaPair) return;
    
    setUpdateLoading(true);
    try {
      await onUpdate({
        ...qaPair,
        answer
      });
      message.success(t('common.updateSuccess'));
      setOriginalAnswer(answer);
      setEditingAnswer(false);
    } catch (error) {
      console.error('Failed to update answer:', error);
      message.error(t('common.updateFailed'));
    } finally {
      setUpdateLoading(false);
    }
  };

  const handleDeleteConfirm = async () => {
    if (!qaPair) return;
    
    setDeleteLoading(true);
    try {
      await onDelete(qaPair.id);
      message.success(t('common.delSuccess'));
      onClose();
    } catch (error) {
      console.error('Failed to delete QA pair:', error);
      message.error(t('common.delFailed'));
    } finally {
      setDeleteLoading(false);
    }
  };

  if (!qaPair) return null;

  const qaContent = (
    <div className="space-y-6">
      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <h3 className="font-medium flex items-center">
            Q:
          </h3>
          <div className="flex items-center gap-1">
            {editingQuestion ? (
              <>
                <Button
                  type="text"
                  icon={<CheckOutlined />}
                  onClick={handleQuestionUpdate}
                  loading={updateLoading}
                  size="small"
                  className="text-green-600"
                />
                <Button
                  type="text"
                  icon={<CloseOutlined />}
                  onClick={handleQuestionCancel}
                  size="small"
                  className="text-red-500"
                />
              </>
            ) : (
              <Button
                type="text"
                icon={<EditOutlined />}
                onClick={handleQuestionEditToggle}
                size="small"
              />
            )}
          </div>
        </div>
        
        {editingQuestion ? (
          <TextArea
            rows={4}
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            autoFocus
            placeholder={t('common.inputMsg') + t('knowledge.qaPairs.question')}
          />
        ) : (
          <div className="p-3 bg-gray-50 rounded-md min-h-[80px]">
            {question || '--'}
          </div>
        )}
      </div>

      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <h3 className="font-medium flex items-center">
            A:
          </h3>
          <div className="flex items-center gap-1">
            {editingAnswer ? (
              <>
                <Button
                  type="text"
                  icon={<CheckOutlined />}
                  onClick={handleAnswerUpdate}
                  loading={updateLoading}
                  size="small"
                  className="text-green-600"
                />
                <Button
                  type="text"
                  icon={<CloseOutlined />}
                  onClick={handleAnswerCancel}
                  size="small"
                  className="text-red-500"
                />
              </>
            ) : (
              <Button
                type="text"
                icon={<EditOutlined />}
                onClick={handleAnswerEditToggle}
                size="small"
              />
            )}
          </div>
        </div>
        
        {editingAnswer ? (
          <TextArea
            rows={6}
            value={answer}
            onChange={(e) => setAnswer(e.target.value)}
            autoFocus
            placeholder={t('common.inputMsg') + t('knowledge.qaPairs.answer')}
          />
        ) : (
          <div className="p-3 bg-gray-50 rounded-md min-h-[120px]">
            {answer || '--'}
          </div>
        )}
      </div>
    </div>
  );

  const chunkContent = (
    <div className="space-y-4">
      {chunkLoading ? (
        <div className="flex justify-center py-8">
          <Spin size="large" />
        </div>
      ) : chunkDetail ? (
        <div className="space-y-4">
          {chunkDetail.title && (
            <div>
              <h4 className="font-medium mb-2">{t('knowledge.documents.title')}:</h4>
              <div className="p-3 bg-gray-50 rounded-md">
                {chunkDetail.title}
              </div>
            </div>
          )}
          
          <div className="bg-gray-50 rounded-md p-3">
            <div className="flex justify-between items-center mb-2">
              <span className="text-sm text-gray-600">
                {chunkDetail.index_name && (
                  <span>Index: {chunkDetail.index_name}</span>
                )}
              </span>
              <Tag color="blue">
                {chunkDetail.content ? chunkDetail.content.length : 0} chars
              </Tag>
            </div>
            <div className="min-h-[200px] max-h-[400px] overflow-y-auto whitespace-pre-wrap">
              {chunkDetail.content || '--'}
            </div>
          </div>

        </div>
      ) : (
        <div className="text-center py-8 text-gray-500">
          {t('knowledge.documents.noChunkData')}
        </div>
      )}
    </div>
  );

  const segmentedOptions = [
    {
      label: t('knowledge.qaPairs.title'),
      value: 'qa',
    },
  ];

  // 只有存在 base_chunk_id 时才添加原始分块选项
  if (qaPair?.base_chunk_id) {
    segmentedOptions.push({
      label: t('knowledge.documents.originalChunk'),
      value: 'chunk',
    });
  }

  const renderContent = () => {
    if (activeTab === 'chunk') {
      return chunkContent;
    }
    return qaContent;
  };

  return (
    <Drawer
      title={t('common.viewDetails')}
      placement="right"
      width={600}
      open={visible}
      onClose={onClose}
      footer={
        <div className="flex justify-end space-x-2">
          <Popconfirm
            title={t('common.delConfirm')}
            onConfirm={handleDeleteConfirm}
            okText={t('common.confirm')}
            cancelText={t('common.cancel')}
          >
            <Button
              danger
              icon={<DeleteOutlined />}
              loading={deleteLoading}
            >
              {t('common.delete')}
            </Button>
          </Popconfirm>
          <Button onClick={onClose}>
            {t('common.close')}
          </Button>
        </div>
      }
    >
      <div className="space-y-4">
        <Segmented
          value={activeTab}
          onChange={handleTabChange}
          options={segmentedOptions}
        />
        <div className="mt-4">
          {renderContent()}
        </div>
      </div>
    </Drawer>
  );
};

export default QADetailDrawer;