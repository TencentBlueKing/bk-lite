'use client';

import React, {
  useState,
  useEffect,
  useRef,
  forwardRef,
  useImperativeHandle,
} from 'react';
import { Input, Button, Form, message, Space, Popconfirm, Empty } from 'antd';
import { DndContext, closestCenter, PointerSensor, useSensor, useSensors } from '@dnd-kit/core';
import { SortableContext, verticalListSortingStrategy, useSortable, arrayMove } from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import OperateModal from '@/components/operate-modal';
import GroupTreeSelector from '@/components/group-tree-select';
import type { FormInstance } from 'antd';
import { PlusOutlined, MinusOutlined, HolderOutlined, EditOutlined, DeleteOutlined } from '@ant-design/icons';
import { deepClone } from '@/app/cmdb/utils/common';
import { PublicEnumLibraryItem, PublicEnumOption } from '@/app/cmdb/types/assetManage';
import { useTranslation } from '@/utils/i18n';
import { useModelApi } from '@/app/cmdb/api';

export interface PublicEnumLibraryModalRef {
  showModal: () => void;
}

interface PublicEnumLibraryModalProps {
  onSuccess?: () => void;
}

const SortableItem = ({
  id,
  index,
  children,
}: {
  id: string;
  index: number;
  children: React.ReactNode;
}) => {
  const { attributes, listeners, setNodeRef, transform, transition } =
    useSortable({ id });
  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    marginTop: index ? 10 : 0,
    display: 'flex',
    width: '100%',
    minWidth: 0,
  };
  return (
    <li ref={setNodeRef} style={style}>
      {React.Children.map(children, (child, idx) =>
        idx === 0 && React.isValidElement(child)
          ? React.cloneElement(child, { ...attributes, ...listeners } as React.HTMLAttributes<HTMLElement>)
          : child
      )}
    </li>
  );
};

const PublicEnumLibraryModal = forwardRef<PublicEnumLibraryModalRef, PublicEnumLibraryModalProps>(
  ({ onSuccess }, ref) => {
    const { t } = useTranslation();
    const formRef = useRef<FormInstance>(null);
    const {
      getPublicEnumLibraries,
      createPublicEnumLibrary,
      updatePublicEnumLibrary,
      deletePublicEnumLibrary,
    } = useModelApi();

    const [visible, setVisible] = useState<boolean>(false);
    const [loading, setLoading] = useState<boolean>(false);
    const [confirmLoading, setConfirmLoading] = useState<boolean>(false);
    const [libraries, setLibraries] = useState<PublicEnumLibraryItem[]>([]);
    const [selectedLibrary, setSelectedLibrary] = useState<PublicEnumLibraryItem | null>(null);
    const [isEditing, setIsEditing] = useState<boolean>(false);
    const [isAdding, setIsAdding] = useState<boolean>(false);
    const [optionList, setOptionList] = useState<PublicEnumOption[]>([{ id: '', name: '' }]);

    const sensors = useSensors(useSensor(PointerSensor));

    useImperativeHandle(ref, () => ({
      showModal: () => {
        setVisible(true);
        setIsEditing(false);
        setIsAdding(false);
        setSelectedLibrary(null);
        loadLibraries();
      },
    }));

    const loadLibraries = async () => {
      setLoading(true);
      try {
        const res = await getPublicEnumLibraries();
        const list = res || [];
        setLibraries(list);
        if (list.length > 0 && !selectedLibrary) {
          setSelectedLibrary(list[0]);
        }
      } finally {
        setLoading(false);
      }
    };

    useEffect(() => {
      if (isEditing && formRef.current && selectedLibrary) {
        formRef.current.resetFields();
        formRef.current.setFieldsValue({
          name: selectedLibrary.name,
          team: selectedLibrary.team,
        });
        setOptionList(selectedLibrary.options.length > 0 
          ? selectedLibrary.options 
          : [{ id: '', name: '' }]);
      } else if (isAdding && formRef.current) {
        formRef.current.resetFields();
        setOptionList([{ id: '', name: '' }]);
      }
    }, [isEditing, isAdding, selectedLibrary]);

    const handleClose = () => {
      setVisible(false);
    };

    const handleSelectLibrary = (library: PublicEnumLibraryItem) => {
      if (isEditing || isAdding) return;
      setSelectedLibrary(library);
    };

    const handleAddNew = () => {
      setIsAdding(true);
      setIsEditing(false);
      setSelectedLibrary(null);
    };

    const handleEdit = () => {
      setIsEditing(true);
      setIsAdding(false);
    };

    const handleCancel = () => {
      setIsEditing(false);
      setIsAdding(false);
      if (isAdding && libraries.length > 0) {
        setSelectedLibrary(libraries[0]);
      }
    };

    const handleDelete = async () => {
      if (!selectedLibrary) return;
      try {
        await deletePublicEnumLibrary(selectedLibrary.library_id);
        message.success(t('successfullyDeleted'));
        const newLibraries = libraries.filter(l => l.library_id !== selectedLibrary.library_id);
        setLibraries(newLibraries);
        setSelectedLibrary(newLibraries.length > 0 ? newLibraries[0] : null);
        onSuccess?.();
      } catch (error: any) {
        const errorMsg = error?.response?.data?.message || error?.message;
        if (errorMsg) {
          message.error(errorMsg);
        }
      }
    };

    const handleSubmit = async () => {
      try {
        const values = await formRef.current?.validateFields();
        const validOptions = optionList.filter(opt => opt.id && opt.name);
        
        if (validOptions.length === 0) {
          message.error(t('PublicEnumLibrary.optionIdRequired'));
          return;
        }

        const ids = validOptions.map(o => o.id);
        if (new Set(ids).size !== ids.length) {
          message.error(t('PublicEnumLibrary.optionIdDuplicate'));
          return;
        }

        setConfirmLoading(true);
        const params = {
          name: values.name,
          team: Array.isArray(values.team) ? values.team : [values.team],
          options: validOptions,
        };

        if (isAdding) {
          await createPublicEnumLibrary(params);
          message.success(t('successfullyAdded'));
        } else if (isEditing && selectedLibrary) {
          await updatePublicEnumLibrary(selectedLibrary.library_id, params);
          message.success(t('successfullyModified'));
        }

        setIsEditing(false);
        setIsAdding(false);
        await loadLibraries();
        onSuccess?.();
      } catch (error) {
        console.error(error);
      } finally {
        setConfirmLoading(false);
      }
    };

    const addOption = () => {
      setOptionList([...optionList, { id: '', name: '' }]);
    };

    const deleteOption = (index: number) => {
      const newList = deepClone(optionList);
      newList.splice(index, 1);
      setOptionList(newList.length > 0 ? newList : [{ id: '', name: '' }]);
    };

    const onOptionChange = (field: 'id' | 'name', value: string, index: number) => {
      const newList = deepClone(optionList);
      newList[index][field] = value;
      setOptionList(newList);
    };

    const onDragEnd = (event: any) => {
      const { active, over } = event;
      if (!over) return;
      const oldIndex = parseInt(active.id as string, 10);
      const newIndex = parseInt(over.id as string, 10);
      if (oldIndex !== newIndex) {
        setOptionList((items) => arrayMove(items, oldIndex, newIndex));
      }
    };

    const renderLeftPanel = () => (
      <div className="w-[200px] border-r border-[var(--color-border)] pr-4 flex flex-col h-full">
        <Button 
          type="primary" 
          icon={<PlusOutlined />} 
          onClick={handleAddNew}
          disabled={isEditing || isAdding}
          className="mb-4"
        >
          {t('PublicEnumLibrary.addLibrary')}
        </Button>
        <div className="flex-1 overflow-y-auto">
          {libraries.length === 0 && !loading ? (
            <div className="text-center text-[var(--color-text-tertiary)] py-4">
              {t('common.noData')}
            </div>
          ) : (
            <ul className="space-y-1">
              {libraries.map((lib) => (
                <li
                  key={lib.library_id}
                  onClick={() => handleSelectLibrary(lib)}
                  className={`px-3 py-2 rounded cursor-pointer transition-colors ${
                    selectedLibrary?.library_id === lib.library_id
                      ? 'bg-[var(--color-primary-bg)] text-[var(--color-primary)]'
                      : 'hover:bg-[var(--color-fill-2)]'
                  } ${(isEditing || isAdding) ? 'opacity-50 cursor-not-allowed' : ''}`}
                >
                  {lib.name}
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    );

    const renderViewMode = () => {
      if (!selectedLibrary) {
        return (
          <div className="flex-1 flex items-center justify-center">
            <Empty description={t('PublicEnumLibrary.selectLibraryHint')} />
          </div>
        );
      }

      return (
        <div className="flex-1 pl-4 flex flex-col">
          <div className="flex justify-between items-center mb-4">
            <h3 className="text-lg font-medium">{selectedLibrary.name}</h3>
            {selectedLibrary.editable && (
              <Space>
                <Button type="primary" icon={<EditOutlined />} onClick={handleEdit}>
                  {t('common.edit')}
                </Button>
                <Popconfirm
                  title={t('PublicEnumLibrary.deleteConfirm')}
                  onConfirm={handleDelete}
                  okText={t('common.confirm')}
                  cancelText={t('common.cancel')}
                >
                  <Button danger icon={<DeleteOutlined />}>
                    {t('common.delete')}
                  </Button>
                </Popconfirm>
              </Space>
            )}
          </div>

          <div className="mb-4">
            <span className="text-[var(--color-text-secondary)]">{t('PublicEnumLibrary.team')}：</span>
            <span>{Array.isArray(selectedLibrary.team) ? selectedLibrary.team.join(', ') : selectedLibrary.team}</span>
          </div>

          <div className="flex items-center py-2 border-b border-[var(--color-border)] text-[var(--color-text-secondary)] text-sm">
            <span className="w-1/2">{t('PublicEnumLibrary.optionId')}</span>
            <span className="w-1/2">{t('PublicEnumLibrary.optionName')}</span>
          </div>

          <div className="flex-1 overflow-y-auto">
            {selectedLibrary.options.length === 0 ? (
              <div className="text-center text-[var(--color-text-tertiary)] py-4">
                {t('common.noData')}
              </div>
            ) : (
              <ul>
                {selectedLibrary.options.map((opt, index) => (
                  <li key={index} className="flex items-center py-2 border-b border-[var(--color-border-secondary)]">
                    <span className="w-1/2">{opt.id}</span>
                    <span className="w-1/2">{opt.name}</span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      );
    };

    const renderEditMode = () => (
      <div className="flex-1 pl-4 flex flex-col">
        <Form
          ref={formRef}
          layout="vertical"
          className="flex-1 flex flex-col"
        >
          <div className="flex items-center gap-4 mb-4">
            <Form.Item
              name="name"
              rules={[{ required: true, message: t('PublicEnumLibrary.nameRequired') }]}
              className="mb-0 flex-1"
            >
              <Input placeholder={t('PublicEnumLibrary.namePlaceholder')} />
            </Form.Item>
            <Space>
              <Button type="primary" loading={confirmLoading} onClick={handleSubmit}>
                {t('common.save')}
              </Button>
              <Button onClick={handleCancel}>{t('common.cancel')}</Button>
            </Space>
          </div>

          <Form.Item
            label={t('PublicEnumLibrary.team')}
            name="team"
            rules={[{ required: true, message: t('PublicEnumLibrary.teamRequired') }]}
          >
            <GroupTreeSelector placeholder={t('common.selectTip')} />
          </Form.Item>

          <div className="flex-1 overflow-y-auto">
            <div className="bg-[var(--color-fill-1)] p-4 rounded">
              <DndContext
                sensors={sensors}
                collisionDetection={closestCenter}
                onDragEnd={onDragEnd}
              >
                <SortableContext
                  items={optionList.map((_, idx) => idx.toString())}
                  strategy={verticalListSortingStrategy}
                >
                  <ul>
                    <li className="flex items-center mb-2 text-sm text-[var(--color-text-secondary)]">
                      <span className="mr-[4px] w-[14px]"></span>
                      <span className="mr-[10px] w-2/5">{t('PublicEnumLibrary.optionId')}</span>
                      <span className="mr-[10px] w-2/5">{t('PublicEnumLibrary.optionName')}</span>
                    </li>
                    {optionList.map((opt, index) => (
                      <SortableItem key={index} id={index.toString()} index={index}>
                        <HolderOutlined className="mr-[4px] cursor-move" />
                        <Input
                          placeholder={t('PublicEnumLibrary.optionId')}
                          className="mr-[10px] w-2/5"
                          value={opt.id}
                          onChange={(e) => onOptionChange('id', e.target.value, index)}
                        />
                        <Input
                          placeholder={t('PublicEnumLibrary.optionName')}
                          className="mr-[10px] w-2/5"
                          value={opt.name}
                          onChange={(e) => onOptionChange('name', e.target.value, index)}
                        />
                        <PlusOutlined
                          className="mr-[10px] cursor-pointer text-[var(--color-primary)]"
                          onClick={addOption}
                        />
                        {optionList.length > 1 && (
                          <MinusOutlined
                            className="cursor-pointer text-[var(--color-primary)]"
                            onClick={() => deleteOption(index)}
                          />
                        )}
                      </SortableItem>
                    ))}
                  </ul>
                </SortableContext>
              </DndContext>
            </div>
          </div>
        </Form>
      </div>
    );

    return (
      <OperateModal
        width={800}
        title={t('PublicEnumLibrary.title')}
        subTitle={t('PublicEnumLibrary.description')}
        visible={visible}
        onCancel={handleClose}
        footer={
          <Button onClick={handleClose}>{t('common.close')}</Button>
        }
      >
        <div className="flex h-[400px]">
          {renderLeftPanel()}
          {(isEditing || isAdding) ? renderEditMode() : renderViewMode()}
        </div>
      </OperateModal>
    );
  }
);

PublicEnumLibraryModal.displayName = 'PublicEnumLibraryModal';
export default PublicEnumLibraryModal;
