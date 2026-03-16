import React, {
  useState,
  useEffect,
  useRef,
  forwardRef,
  useImperativeHandle,
} from 'react';
import { Input, Button, Form, message, Empty, Modal } from 'antd';
import { DndContext, closestCenter, PointerSensor, useSensor, useSensors } from '@dnd-kit/core';
import { SortableContext, verticalListSortingStrategy, arrayMove } from '@dnd-kit/sortable';
import OperateModal from '@/components/operate-modal';
import GroupTreeSelector from '@/components/group-tree-select';
import SortableItem from '@/app/cmdb/components/sortable-item';
import type { FormInstance } from 'antd';
import {
  PlusOutlined,
  MinusOutlined,
  HolderOutlined,
  EditOutlined,
  DeleteOutlined,
} from '@ant-design/icons';
import { deepClone, getOrganizationDisplayText } from '@/app/cmdb/utils/common';
import { PublicEnumLibraryItem, PublicEnumOption } from '@/app/cmdb/types/assetManage';
import { useTranslation } from '@/utils/i18n';
import { useModelApi } from '@/app/cmdb/api';
import { useUserInfoContext } from '@/context/userInfo';
import EllipsisWithTooltip from '@/components/ellipsis-with-tooltip';

export interface PublicEnumLibraryModalRef {
  showModal: (initialLibraryId?: string) => void;
}

interface PublicEnumLibraryModalProps {
  onSuccess?: () => void;
}

const PublicEnumLibraryModal = forwardRef<PublicEnumLibraryModalRef, PublicEnumLibraryModalProps>(
  ({ onSuccess }, ref) => {
    const { t } = useTranslation();
    const { flatGroups } = useUserInfoContext();
    const libraryFormRef = useRef<FormInstance>(null);
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
    const [selectedLibrary, setSelectedLibrary] =
      useState<PublicEnumLibraryItem | null>(null);
    const [optionList, setOptionList] = useState<PublicEnumOption[]>([
      { id: '', name: '' },
    ]);
    const [hoveredLibraryId, setHoveredLibraryId] = useState<string | null>(
      null,
    );
    const [optionsSaving, setOptionsSaving] = useState<boolean>(false);

    const [libraryModalVisible, setLibraryModalVisible] =
      useState<boolean>(false);
    const [libraryModalMode, setLibraryModalMode] = useState<'add' | 'edit'>(
      'add',
    );
    const [editingLibrary, setEditingLibrary] =
      useState<PublicEnumLibraryItem | null>(null);

    const [isEditingOptions, setIsEditingOptions] = useState<boolean>(false);

    const sensors = useSensors(useSensor(PointerSensor));

    useImperativeHandle(ref, () => ({
      showModal: (initialLibraryId?: string) => {
        setVisible(true);
        setIsEditingOptions(false);
        loadLibraries(false, initialLibraryId);
      },
    }));

    const loadLibraries = async (preserveSelection = false, initialLibraryId?: string) => {
      const currentLibraryId = selectedLibrary?.library_id;
      setLoading(true);
      try {
        const res = await getPublicEnumLibraries();
        const list = res || [];
        setLibraries(list);
        if (list.length > 0) {
          if (initialLibraryId) {
            const targetLib = list.find((lib: PublicEnumLibraryItem) => lib.library_id === initialLibraryId);
            if (targetLib) {
              setSelectedLibrary(targetLib);
              setOptionList(deepClone(targetLib.options));
              return;
            }
          }
          if (preserveSelection && currentLibraryId) {
            const current = list.find((lib: PublicEnumLibraryItem) => lib.library_id === currentLibraryId);
            if (current) {
              setSelectedLibrary(current);
              setOptionList(deepClone(current.options));
              return;
            }
          }
          setSelectedLibrary(list[0]);
          setOptionList(deepClone(list[0].options));
        } else {
          setSelectedLibrary(null);
          setOptionList([]);
        }
      } finally {
        setLoading(false);
      }
    };

    useEffect(() => {
      if (libraryModalVisible) {
        setTimeout(() => {
          if (libraryModalMode === 'edit' && editingLibrary) {
            libraryFormRef.current?.setFieldsValue({
              name: editingLibrary.name,
              team: editingLibrary.team,
            });
          } else {
            libraryFormRef.current?.resetFields();
          }
        }, 100);
      }
    }, [libraryModalVisible, libraryModalMode, editingLibrary]);

    useEffect(() => {
      if (selectedLibrary) {
        setOptionList(deepClone(selectedLibrary.options));
        setIsEditingOptions(false);
      }
    }, [selectedLibrary]);

    const handleClose = () => {
      setVisible(false);
    };

    const handleSelectLibrary = (library: PublicEnumLibraryItem) => {
      setSelectedLibrary(library);
    };

    const handleAddNewLibrary = () => {
      setLibraryModalMode('add');
      setEditingLibrary(null);
      setLibraryModalVisible(true);
    };

    const handleEditLibrary = (
      library: PublicEnumLibraryItem,
      e: React.MouseEvent,
    ) => {
      e.stopPropagation();
      setLibraryModalMode('edit');
      setEditingLibrary(library);
      setLibraryModalVisible(true);
    };

    const handleLibraryModalCancel = () => {
      setLibraryModalVisible(false);
      setEditingLibrary(null);
    };

    const handleDeleteLibrary = (
      library: PublicEnumLibraryItem,
      e: React.MouseEvent,
    ) => {
      e.stopPropagation();
      Modal.confirm({
        title: t('common.delConfirm'),
        content: t('common.delConfirmCxt'),
        okText: t('common.confirm'),
        cancelText: t('common.cancel'),
        centered: true,
        onOk: async () => {
          try {
            await deletePublicEnumLibrary(library.library_id);
            message.success(t('successfullyDeleted'));
            const newLibraries = libraries.filter(
              (l) => l.library_id !== library.library_id,
            );
            setLibraries(newLibraries);
            if (selectedLibrary?.library_id === library.library_id) {
              setSelectedLibrary(newLibraries.length > 0 ? newLibraries[0] : null);
            }
            onSuccess?.();
          } catch (error: any) {
            const errorMsg = error?.response?.data?.message || error?.message;
            if (errorMsg) {
              message.error(errorMsg);
            }
          }
        },
      });
    };

    const handleSubmitLibrary = async () => {
      try {
        const values = await libraryFormRef.current?.validateFields();

        setConfirmLoading(true);
        const params = {
          name: values.name,
          team: Array.isArray(values.team) ? values.team : [values.team],
          options:
            libraryModalMode === 'add' ? [] : editingLibrary?.options || [],
        };

        if (libraryModalMode === 'add') {
          await createPublicEnumLibrary(params);
          message.success(t('successfullyAdded'));
        } else if (editingLibrary) {
          await updatePublicEnumLibrary(editingLibrary.library_id, params);
          message.success(t('successfullyModified'));
        }

        setLibraryModalVisible(false);
        setEditingLibrary(null);
        await loadLibraries();
        onSuccess?.();
      } catch (error) {
        console.error(error);
      } finally {
        setConfirmLoading(false);
      }
    };

    const handleStartEditOptions = () => {
      if (optionList.length === 0) {
        setOptionList([{ id: '', name: '' }]);
      }
      setIsEditingOptions(true);
    };

    const handleCancelEditOptions = () => {
      if (selectedLibrary) {
        setOptionList(deepClone(selectedLibrary.options));
      }
      setIsEditingOptions(false);
    };

    const handleSaveOptions = async () => {
      if (!selectedLibrary) return;

      const validOptions = optionList.filter((opt) => opt.id && opt.name);


      const ids = validOptions.map((o) => o.id);
      if (new Set(ids).size !== ids.length) {
        message.error(t('PublicEnumLibrary.optionIdDuplicate'));
        return;
      }

      setOptionsSaving(true);
      try {
        const params = {
          name: selectedLibrary.name,
          team: selectedLibrary.team,
          options: validOptions,
        };
        await updatePublicEnumLibrary(selectedLibrary.library_id, params);
        message.success(t('successfullyModified'));
        setIsEditingOptions(false);
        await loadLibraries(true);
        onSuccess?.();
      } catch (error) {
        console.error(error);
      } finally {
        setOptionsSaving(false);
      }
    };

    const addOption = () => {
      setOptionList([...optionList, { id: '', name: '' }]);
    };

    const deleteOption = (index: number) => {
      const newList = deepClone(optionList);
      newList.splice(index, 1);
      setOptionList(newList);
    };

    const onOptionChange = (
      field: 'id' | 'name',
      value: string,
      index: number,
    ) => {
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
          ghost
          icon={<PlusOutlined />}
          onClick={handleAddNewLibrary}
          className="mb-4"
        >
          {t('common.add')}
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
                  onMouseEnter={() => setHoveredLibraryId(lib.library_id)}
                  onMouseLeave={() => setHoveredLibraryId(null)}
                  className={`group px-3 py-2 rounded cursor-pointer transition-colors flex items-center justify-between ${
                    selectedLibrary?.library_id === lib.library_id
                      ? 'bg-blue-50 text-[var(--color-primary)]'
                      : 'hover:bg-[var(--color-fill-2)]'
                  }`}
                >
                  <EllipsisWithTooltip text={lib.name} className="truncate flex-1" />
                  {lib.editable && hoveredLibraryId === lib.library_id && (
                    <span className="flex items-center gap-2 ml-1">
                      <EditOutlined
                        className="text-[var(--color-primary)] hover:text-[var(--color-primary-hover)]"
                        onClick={(e) => handleEditLibrary(lib, e)}
                      />
                      <DeleteOutlined
                        className="text-red-500 hover:text-red-600"
                        onClick={(e) => handleDeleteLibrary(lib, e)}
                      />
                    </span>
                  )}
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    );

    const renderOptionsPanel = () => {
      if (!selectedLibrary) {
        return (
          <div className="flex-1 flex items-center justify-center">
            <Empty description={t('PublicEnumLibrary.selectLibraryHint')} />
          </div>
        );
      }

      return (
        <div className="flex-1 pl-4 flex flex-col">
          <div className="mb-4 flex items-start justify-between">
            <div>
              <h3 className="text-lg font-medium mb-1">
                {selectedLibrary.name}
              </h3>
              <div className="text-sm text-[var(--color-text-quaternary)]">
                {t('PublicEnumLibrary.team')}：
                {getOrganizationDisplayText(selectedLibrary.team, flatGroups)}
              </div>
            </div>
          </div>
          {selectedLibrary.editable && (isEditingOptions || optionList.length > 0) && (
            <div className="flex justify-end gap-2 mb-3">
              {isEditingOptions ? (
                <>
                  <Button size="small" onClick={handleCancelEditOptions}>
                    {t('common.cancel')}
                  </Button>
                  <Button
                    type="primary"
                    size="small"
                    loading={optionsSaving}
                    onClick={handleSaveOptions}
                  >
                    {t('common.save')}
                  </Button>
                </>
              ) : (
                <Button
                  size="small"
                  type="link"
                  onClick={handleStartEditOptions}
                  className="p-0"
                >
                  {t('common.edit')}
                </Button>
              )}
            </div>
          )}

          <div className="flex-1 overflow-y-auto">
            {optionList.length === 0 ? (
              <div className="flex flex-col items-center justify-center h-full">
                <Empty
                  image={Empty.PRESENTED_IMAGE_SIMPLE}
                  description={t('common.noData')}
                  className="m-4"
                />
                {selectedLibrary.editable && (
                  <Button
                    type="link"
                    icon={<PlusOutlined />}
                    onClick={handleStartEditOptions}
                    className="-mt-2"
                  >
                    {t('PublicEnumLibrary.addOption')}
                  </Button>
                )}
              </div>
            ) : (
              <DndContext
                sensors={sensors}
                collisionDetection={closestCenter}
                onDragEnd={isEditingOptions ? onDragEnd : undefined}
              >
                <SortableContext
                  items={optionList.map((_, idx) => idx.toString())}
                  strategy={verticalListSortingStrategy}
                  disabled={!isEditingOptions}
                >
                  <ul>
                    <li className="flex items-center mb-2 text-sm text-[var(--color-text-secondary)]">
                      {isEditingOptions && (
                        <span className="mr-2 w-[14px]"></span>
                      )}
                      <span className="flex-1 mr-2">
                        {t('PublicEnumLibrary.optionId')}
                      </span>
                      <span className="flex-1 mr-2">
                        {t('PublicEnumLibrary.optionName')}
                      </span>
                      {isEditingOptions && <span className="w-[50px]"></span>}
                    </li>
                    {optionList.map((opt, index) => (
                      <SortableItem
                        key={index}
                        id={index.toString()}
                        index={index}
                      >
                        {isEditingOptions && (
                          <HolderOutlined className="mr-2 cursor-move text-[var(--color-text-tertiary)]" />
                        )}
                        <Input
                          placeholder={t('PublicEnumLibrary.optionId')}
                          className={`flex-1 mr-2 ${!isEditingOptions ? '[&.ant-input-filled]:bg-[var(--color-fill-1)] text-[var(--color-text-tertiary)]' : ''}`}
                          value={opt.id}
                          readOnly={!isEditingOptions}
                          variant={isEditingOptions ? 'outlined' : 'filled'}
                          onChange={(e) =>
                            onOptionChange('id', e.target.value, index)
                          }
                        />
                        <Input
                          placeholder={t('PublicEnumLibrary.optionName')}
                          className={`flex-1 mr-2 ${!isEditingOptions ? '[&.ant-input-filled]:bg-[var(--color-fill-1)] text-[var(--color-text-tertiary)]' : ''}`}
                          value={opt.name}
                          readOnly={!isEditingOptions}
                          variant={isEditingOptions ? 'outlined' : 'filled'}
                          onChange={(e) =>
                            onOptionChange('name', e.target.value, index)
                          }
                        />
                        {isEditingOptions && (
                          <span className="w-[50px] flex items-center gap-1">
                            <PlusOutlined
                              className="cursor-pointer text-[var(--color-primary)]"
                              onClick={addOption}
                            />
                            <MinusOutlined
                              className="cursor-pointer text-red-500 hover:text-red-600"
                              onClick={() => deleteOption(index)}
                            />
                          </span>
                        )}
                      </SortableItem>
                    ))}
                  </ul>
                </SortableContext>
              </DndContext>
            )}
          </div>
        </div>
      );
    };

    return (
      <>
        <OperateModal
          width={800}
          title={t('PublicEnumLibrary.title')}
          subTitle={t('PublicEnumLibrary.description')}
          visible={visible}
          onCancel={handleClose}
          footer={<Button onClick={handleClose}>{t('common.close')}</Button>}
        >
          <div className="flex h-[400px]">
            {renderLeftPanel()}
            {renderOptionsPanel()}
          </div>
        </OperateModal>

        <Modal
          title={
            libraryModalMode === 'add'
              ? t('PublicEnumLibrary.addLibrary')
              : t('PublicEnumLibrary.editLibrary')
          }
          open={libraryModalVisible}
          onCancel={handleLibraryModalCancel}
          onOk={handleSubmitLibrary}
          confirmLoading={confirmLoading}
          okText={t('common.confirm')}
          cancelText={t('common.cancel')}
          width={480}
          centered
          destroyOnClose={false}
          afterClose={() => libraryFormRef.current?.resetFields()}
        >
          <Form ref={libraryFormRef} layout="vertical" className="mt-4">
            <Form.Item
              label={t('PublicEnumLibrary.name')}
              name="name"
              rules={[
                {
                  required: true,
                  message: t('PublicEnumLibrary.nameRequired'),
                },
                {
                  validator: (_, value) => {
                    if (!value) return Promise.resolve();
                    const isDuplicate = libraries.some(
                      (lib) =>
                        lib.name === value &&
                        lib.library_id !== editingLibrary?.library_id
                    );
                    if (isDuplicate) {
                      return Promise.reject(
                        new Error(t('PublicEnumLibrary.nameExists'))
                      );
                    }
                    return Promise.resolve();
                  },
                },
              ]}
            >
              <Input placeholder={t('PublicEnumLibrary.namePlaceholder')} />
            </Form.Item>
            <Form.Item
              label={t('PublicEnumLibrary.team')}
              name="team"
              rules={[
                {
                  required: true,
                  message: t('PublicEnumLibrary.teamRequired'),
                },
              ]}
            >
              <GroupTreeSelector placeholder={t('common.selectTip')} />
            </Form.Item>
          </Form>
        </Modal>
      </>
    );
  }
);

PublicEnumLibraryModal.displayName = 'PublicEnumLibraryModal';
export default PublicEnumLibraryModal;
