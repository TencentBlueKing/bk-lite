"use client";
import { Segmented, Menu, Button, message } from 'antd';
import stlyes from '@/app/lab/styles/index.module.scss';
import { useState, useEffect, useRef } from 'react';
import EntityList from '@/components/entity-list';
import useLabManage from '@/app/lab/api/mirror';
import LabImageModal from './labImageModal';
import { ModalRef, LabImageItem } from '@/app/lab/types';
import { useTranslation } from '@/utils/i18n';

const MirrorManage = () => {
  const { t } = useTranslation();
  const modalRef = useRef<ModalRef>(null);
  const [activeTab, setActiveTab] = useState<('ide' | 'infra')>('ide');
  const tabOptions = [
    { label: t(`lab.manage.ide`), value: 'ide' },
    { label: t(`lab.manage.infra`), value: 'infra' }
  ];

  const { getIdeImages, getInfraImages, deleteImage } = useLabManage();
  const [tableData, setTableData] = useState<LabImageItem[]>([]);
  const [loading, setLoading] = useState(false);

  // tab切换时请求镜像列表
  const fetchImages = async (type: string) => {
    setLoading(true);
    try {
      let res;
      if (type === 'ide') {
        res = await getIdeImages();
      } else {
        res = await getInfraImages();
      }
      const _res = res?.map((item: LabImageItem) => {
        return {
          ...item,
          icon: 'tucengshuju',
          creator: item?.created_by || '--',
        }
      });
      setTableData(_res || []);
    } catch (e) {
      console.error(e);
      setTableData([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchImages(activeTab);
  }, [activeTab]);

  const menuActions = (item: any) => {
    return (
      <Menu onClick={(e) => e.domEvent.preventDefault()}>
        <Menu.Item
          className="!p-0"
          onClick={() => handleEdit({ type: 'edit', form: item })}
        >
          {/* <PermissionWrapper requiredPermissions={['Edit']} className="!block" > */}
          <Button type="text" className="w-full">
            {t(`common.edit`)}
          </Button>
          {/* </PermissionWrapper> */}
        </Menu.Item>
        {item?.name !== "default" && (
          <Menu.Item className="!p-0" onClick={() => handleDel(item.id)}>
            {/* <PermissionWrapper requiredPermissions={['Delete']} className="!block" > */}
            <Button type="text" className="w-full">
              {t(`common.delete`)}
            </Button>
            {/* </PermissionWrapper> */}
          </Menu.Item>
        )}
      </Menu>
    )
  };

  // 描述区域
  const descSlot = (item: any) => (
    <p className="text-right font-mini text-[var(--color-text-3)]">
      {`creator: ${item.created_by || '--'}`}
    </p>
  );

  // 卡片点击
  const handleCardClick = (item: LabImageItem) => {
    // 可跳转详情或弹窗
  };

  // 新增
  const handleAdd = () => {
    // 新增逻辑
    modalRef.current?.showModal({ type: 'add' });
  };

  // 编辑
  const handleEdit = (data: any) => {
    modalRef.current?.showModal(data)
  };

  // 删除
  const handleDel = async (id: string | number) => {
    setLoading(true);
    try {
      await deleteImage(id);
      message.success(t('common.deleteSuccess'));
      fetchImages(activeTab);
    } catch (e) {
      console.error('删除镜像失败:', e);
      message.error(t('common.deleteFailed'));
    } finally {
      setLoading(false);
    }
  };

  // 搜索
  const handleSearch = () => {
    // TODO: 待实现搜索功能
  };

  return (
    <>
      <div className={`w-full h-full ${stlyes.segmented}`}>
        <Segmented options={tabOptions} value={activeTab} onChange={(value) => setActiveTab(value as ("ide" | "infra"))} />
        <div className='flex h-full w-full mt-4'>
          <EntityList
            data={tableData}
            menuActions={menuActions}
            loading={loading}
            onCardClick={handleCardClick}
            openModal={handleAdd}
            onSearch={handleSearch}
            descSlot={descSlot}
          />
        </div>
      </div>
      <LabImageModal ref={modalRef} activeTap={activeTab} onSuccess={() => fetchImages(activeTab)} />
    </>
  )
};

export default MirrorManage;