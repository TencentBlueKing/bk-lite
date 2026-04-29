import React, { useState, useEffect, forwardRef, useImperativeHandle, useCallback, useRef } from 'react';
import { 
  Form, 
  Input, 
  Button, 
  message, 
  Popconfirm, 
  Space
} from 'antd';
import { 
  PlusOutlined, 
  EditOutlined, 
  DeleteOutlined 
} from '@ant-design/icons';
import { useTranslation } from '@/utils/i18n';
import CustomTable from '@/components/custom-table';
import QAEditDrawer from '@/app/opspilot/components/knowledge/qaEditDrawer';

interface QAItem {
  id: string;
  question: string;
  answer: string;
}

interface CustomQAFormData {
  name: string;
  qaList: QAItem[];
}

interface CustomQAFormProps {
  initialData?: Partial<CustomQAFormData>;
  onFormChange?: (isValid: boolean) => void;
  onFormDataChange?: (data: CustomQAFormData) => void;
}

const CustomQAForm = forwardRef<any, CustomQAFormProps>(({ 
  initialData, 
  onFormChange = () => {}, 
  onFormDataChange = () => {} 
}, ref) => {
  const { t } = useTranslation();
  const [form] = Form.useForm();
  
  // 状态管理
  const [drawerVisible, setDrawerVisible] = useState<boolean>(false);
  const [editingItem, setEditingItem] = useState<QAItem | null>(null);
  const [qaList, setQaList] = useState<QAItem[]>([]);
  const [selectedRowKeys, setSelectedRowKeys] = useState<React.Key[]>([]);

  const onFormChangeRef = useRef(onFormChange);
  const onFormDataChangeRef = useRef(onFormDataChange);

  useEffect(() => {
    onFormChangeRef.current = onFormChange;
    onFormDataChangeRef.current = onFormDataChange;
  }, [onFormChange, onFormDataChange]);

  const generateId = () => `qa_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;

  const validateAndNotify = useCallback(() => {
    const formName = form.getFieldValue('name') || '';
    const isValid = formName.trim() !== '' && qaList.length > 0;
    
    onFormChangeRef.current(isValid);
    onFormDataChangeRef.current({
      name: formName,
      qaList
    });
  }, [qaList]);

  useImperativeHandle(ref, () => ({
    validateFields: () => form.validateFields(),
    getFieldsValue: () => ({
      name: form.getFieldValue('name'),
      qaList
    }),
  }));

  useEffect(() => {
    if (initialData) {
      if (initialData.name) {
        form.setFieldsValue({ name: initialData.name });
      }
      if (initialData.qaList) {
        setQaList(initialData.qaList);
      }
    }
  }, [initialData, form]);

  useEffect(() => {
    validateAndNotify();
  }, [validateAndNotify]);

  const columns = [
    {
      title: t('knowledge.qaPairs.question'),
      dataIndex: 'question',
      key: 'question',
      width: '40%',
      ellipsis: true
    },
    {
      title: t('knowledge.qaPairs.answer'),
      dataIndex: 'answer',
      key: 'answer',
      width: '40%',
      ellipsis: true
    },
    {
      title: t('common.actions'),
      key: 'actions',
      width: '20%',
      render: (_: any, record: QAItem) => (
        <Space>
          <Button
            type="link"
            size="small"
            icon={<EditOutlined />}
            onClick={() => handleEdit(record)}
          >
            {t('common.edit')}
          </Button>
          <Popconfirm
            title={t('common.delConfirm')}
            onConfirm={() => handleDelete(record.id)}
            okText={t('common.yes')}
            cancelText={t('common.no')}
          >
            <Button
              type="link"
              size="small"
              danger
              icon={<DeleteOutlined />}
            >
              {t('common.delete')}
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  const handleAdd = () => {
    setEditingItem(null);
    setDrawerVisible(true);
  };

  const handleEdit = (item: QAItem) => {
    setEditingItem(item);
    setDrawerVisible(true);
  };

  const handleDelete = (id: string) => {
    setQaList(prev => prev.filter(item => item.id !== id));
    message.success(t('common.delSuccess'));
  };

  const handleBatchDelete = () => {
    if (selectedRowKeys.length === 0) {
      message.warning(t('common.selectFirst'));
      return;
    }
    
    setQaList(prev => prev.filter(item => !selectedRowKeys.includes(item.id)));
    setSelectedRowKeys([]);
    message.success(t('common.delSuccess'));
  };

  const handleSubmit = async (values: {question: string; answer: string}) => {
    if (editingItem) {
      setQaList(prev => prev.map(item => 
        item.id === editingItem.id 
          ? { ...item, question: values.question, answer: values.answer }
          : item
      ));
      message.success(t('common.updateSuccess'));
    } else {
      const newItem: QAItem = {
        id: generateId(),
        question: values.question,
        answer: values.answer,
      };
      setQaList(prev => [...prev, newItem]);
      message.success(t('common.addSuccess'));
    }
  };

  const handleSubmitAndContinue = async (values: {question: string; answer: string}) => {
    const newItem: QAItem = {
      id: generateId(),
      question: values.question,
      answer: values.answer,
    };
    setQaList(prev => [...prev, newItem]);
    message.success(t('common.addSuccess'));
  };

  const rowSelection = {
    selectedRowKeys,
    onChange: (keys: React.Key[]) => setSelectedRowKeys(keys),
  };

  return (
    <div className="max-w-4xl mx-auto">
      <Form form={form} layout="vertical" className="mb-6">
        <Form.Item
          name="name"
          label={t('knowledge.qaPairs.customName')}
          rules={[
            { required: true, message: t('common.required') }
          ]}
        >
          <Input 
            placeholder={t('common.inputMsg') + t('common.name')} 
            size="large"
            onChange={validateAndNotify}
          />
        </Form.Item>

        <Form.Item
          name="qaList"
          label={t('knowledge.qaPairs.customTitle')}
          rules={[
            { 
              validator: () => {
                if (qaList.length === 0) {
                  return Promise.reject(new Error(t('knowledge.qaPairs.required')));
                }
                return Promise.resolve();
              }
            }
          ]}
        >
          <div>
            <div className="flex justify-end items-center mb-4">
              <Space>
                <Button
                  danger
                  icon={<DeleteOutlined />}
                  onClick={handleBatchDelete}
                  disabled={selectedRowKeys.length === 0}
                >
                  {t('common.batchDelete')}
                </Button>
                <Button
                  type="primary"
                  icon={<PlusOutlined />}
                  onClick={handleAdd}
                >
                  {t('common.add')}
                </Button>
              </Space>
            </div>

            <CustomTable
              rowKey="id"
              columns={columns}
              dataSource={qaList}
              rowSelection={rowSelection}
              locale={{
                emptyText: t('knowledge.qaPairs.noData'),
              }}
              scroll={{ y: 400 }}
            />
          </div>
        </Form.Item>
      </Form>

      {/* 使用QAEditDrawer组件 */}
      <QAEditDrawer
        visible={drawerVisible}
        onClose={() => setDrawerVisible(false)}
        onSubmit={handleSubmit}
        onSubmitAndContinue={handleSubmitAndContinue}
        title={editingItem ? t('common.edit') : t('common.add') + t('knowledge.qaPairs.title')}
        initialData={editingItem ? { question: editingItem.question, answer: editingItem.answer } : undefined}
        showContinueButton={!editingItem}
      />
    </div>
  );
});

CustomQAForm.displayName = 'CustomQAForm';

export default CustomQAForm;