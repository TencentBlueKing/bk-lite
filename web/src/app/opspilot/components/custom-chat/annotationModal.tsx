import React, { useState, useEffect } from 'react';
import { Input, Select, message, Tooltip, Button, Popconfirm } from 'antd';
import { EditOutlined, CheckOutlined } from '@ant-design/icons';
import Icon from '@/components/icon';
import { Annotation } from '@/app/opspilot/types/global';
import { useTranslation } from '@/utils/i18n';
import OperateModal from '@/components/operate-modal';
import { useKnowledgeApi } from '@/app/opspilot/api/knowledge';

const { TextArea } = Input;
const { Option } = Select;

interface AnnotationModalProps {
  visible: boolean;
  showMarkOnly?: boolean;
  annotation: Annotation;
  onSave: (annotation?: Annotation) => void;
  onCancel: () => void;
  onRemove: (id: string | undefined) => void;
}

const AnnotationModal: React.FC<AnnotationModalProps> = ({ visible, showMarkOnly, annotation, onSave, onCancel, onRemove }) => {
  const { t } = useTranslation();
  const { fetchKnowledgeBase, saveAnnotation, removeAnnotation } = useKnowledgeApi();
  const [isEditingQuestion, setIsEditingQuestion] = useState(false);
  const [isEditingAnswer, setIsEditingAnswer] = useState(false);
  const [knowledgeBase, setKnowledgeBase] = useState(annotation?.selectedKnowledgeBase || '');
  const [knowledgeBases, setKnowledgeBases] = useState<{ id: string, name: string }[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  const [questionContent, setQuestionContent] = useState(annotation.question?.content);
  const [answerContent, setAnswerContent] = useState(annotation.answer.content);

  useEffect(() => {
    const fetchData = async () => {
      try {
        const data = await fetchKnowledgeBase(); // Use fetchKnowledgeBase
        setKnowledgeBases(data);
      } catch {
        message.error(t('common.fetchFailed'));
      } finally {
        setLoading(false);
      }
    };

    fetchData();
  }, [fetchKnowledgeBase]);

  const handleSave = async () => {
    setSaving(true);
    const payload = {
      question: questionContent,
      knowledge_base_id: parseInt(knowledgeBase.toString()),
      answer_id: showMarkOnly ? annotation.answer.id : null,
      content: answerContent,
      tag_id: annotation?.tagId || 0,
    };

    try {
      const data = await saveAnnotation(payload); // Use saveAnnotation
      message.success(t('chat.annotationSaved'));
      onSave({
        answer: { ...annotation.answer, content: answerContent },
        question: { ...annotation.question, content: questionContent || '' },
        selectedKnowledgeBase: knowledgeBase,
        tagId: data.tag_id,
      });
    } catch {
      message.error(t('chat.annotationFailed'));
    } finally {
      setSaving(false);
    }
  };

  const handleRemoveAnnotation = async () => {
    setSaving(true);
    try {
      await removeAnnotation(annotation.tagId);
      message.success(t('chat.annotationRemoved'));
      onRemove(annotation?.answer?.id);
    } catch {
      message.error(t('chat.annotationRemoveFailed'));
    } finally {
      setSaving(false);
    }
  };

  return (
    <OperateModal
      title={annotation.tagId ? t('chat.editAnnotation') : t('chat.addAnnotation')}
      visible={visible}
      onOk={handleSave}
      onCancel={onCancel}
      okText={annotation.tagId ? t('common.confirm') : t('common.add')}
      styles={{ body: { overflowY: 'auto', maxHeight: 'calc(80vh - 108px)' } }}
      confirmLoading={saving || loading}
    >
      <div className='pt-4 pb-4'>
        <div className="flex items-start">
          <Icon type='yonghu' className='text-2xl mr-2' />
          <div className="flex-1">
            <div className="flex">
              <h4 className="flex-1 font-semibold">{t('chat.question')}</h4>
              {isEditingQuestion ? (
                <Tooltip title="Finish">
                  <CheckOutlined className="ml-2 cursor-pointer text-blue-500" onClick={() => setIsEditingQuestion(false)} />
                </Tooltip>
              ) : (
                <Tooltip title="Edit">
                  <EditOutlined className="ml-2 cursor-pointer text-blue-500" onClick={() => setIsEditingQuestion(true)} />
                </Tooltip>
              )}
            </div>
            {isEditingQuestion ? (
              <TextArea className="mt-2" rows={4} value={questionContent} onChange={(e) => setQuestionContent(e.target.value)} />
            ) : (
              <p className="mt-2">{questionContent}</p>
            )}
          </div>
        </div>
        <div className="flex items-start mt-4">
          <Icon type='jiqiren3' className='text-2xl mr-2' />
          <div className="flex-1">
            <div className="flex">
              <h4 className="flex-1 font-semibold">{t('chat.answer')}</h4>
              {isEditingAnswer ? (
                <Tooltip title="Finish">
                  <CheckOutlined className="ml-2 cursor-pointer text-blue-500" onClick={() => setIsEditingAnswer(false)} />
                </Tooltip>
              ) : (
                <Tooltip title="Edit">
                  <EditOutlined className="ml-2 cursor-pointer text-blue-500" onClick={() => setIsEditingAnswer(true)} />
                </Tooltip>
              )}
            </div>
            {isEditingAnswer ? (
              <TextArea className="mt-2" rows={4} value={answerContent} onChange={(e) => setAnswerContent(e.target.value)} />
            ) : (
              <p className="mt-2">{answerContent}</p>
            )}
          </div>
        </div>
        <div className="flex items-start mt-4">
          <Icon type='zhishiku' className='text-2xl mr-2' />
          <div className="flex-1">
            <h4 className='font-semibold mb-2'>{t('chat.saveToKnowledgeBase')}</h4>
            <Select loading={loading} disabled={loading} value={knowledgeBase} onChange={(value) => setKnowledgeBase(value)} className="w-full">
              {knowledgeBases.map((kb) => (
                <Option key={kb.id} value={kb.id}>{kb.name}</Option>
              ))}
            </Select>
          </div>
        </div>
      </div>
      <div className="flex items-center justify-end mt-6 absolute bottom-[20px]">
        {!!annotation.tagId && (
          <Popconfirm
            title={t('chat.removeAnnotationConfirm')}
            onConfirm={handleRemoveAnnotation}
            okText={t('common.confirm')}
            cancelText={t('common.cancel')}
          >
            <Button type='text' danger loading={saving} className="mr-2">
              {t('chat.removeAnnotation')}
            </Button>
          </Popconfirm>
        )}
      </div>
    </OperateModal>
  );
};

export default AnnotationModal;
