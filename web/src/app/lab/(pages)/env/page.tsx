"use client";
import { Menu, Button, message } from 'antd';
import { PlayCircleOutlined, PauseCircleOutlined } from '@ant-design/icons';
import stlyes from '@/app/lab/styles/index.module.scss';
import { useState, useEffect, useRef } from 'react';
import EntityList from '@/components/entity-list';
import { ModalRef } from '@/app/lab/types';
import { useTranslation } from '@/utils/i18n';
import useLabEnv from '@/app/lab/api/env';
import LabEnvModal from './labEnvModal';

const EnvManage = () => {
  const { t } = useTranslation();
  const modalRef = useRef<ModalRef>(null);
  const {
    getEnvList,
    deleteEnv,
    startEnv,
    stopEnv,
    restartEnv
  } = useLabEnv();

  const [tableData, setTableData] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);

  // 请求环境列表
  const fetchEnvs = async () => {
    setLoading(true);
    try {
      const res = await getEnvList();
      const _res = res?.map((item: any) => {
        return {
          ...item,
          icon: 'tucengshuju',
          creator: item?.created_by || '--',
        }
      })
      setTableData(_res || []);
    } catch (e) {
      console.log(e);
      setTableData([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchEnvs();
  }, []);

  // 启动环境
  const handleStart = async (id: string | number, e: React.MouseEvent) => {
    e.stopPropagation(); // 阻止卡片点击事件
    setLoading(true);
    try {
      await startEnv(id);
      message.success('环境启动成功');
      fetchEnvs(); // 刷新列表
    } catch (error) {
      console.error('启动环境失败:', error);
      message.error('启动环境失败');
    } finally {
      setLoading(false);
    }
  };

  // 重启环境
  const handleRestart = async (id: string | number) => {
    setLoading(true);
    try {
      await restartEnv(id);
      message.success('环境重启成功');
      fetchEnvs();
    } catch (e) {
      console.log(e);
      message.error('重启环境失败')
    } finally {
      setLoading(false);
    }
  };

  // 停止环境
  const handleStop = async (id: string | number, e: React.MouseEvent) => {
    e.stopPropagation(); // 阻止卡片点击事件
    setLoading(true);
    try {
      await stopEnv(id);
      message.success('环境停止成功');
      fetchEnvs(); // 刷新列表
    } catch (error) {
      console.error('停止环境失败:', error);
      message.error('停止环境失败');
    } finally {
      setLoading(false);
    }
  };

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
        <Menu.Item
          className="!p-0"
          onClick={() => handleRestart(item.id)}
        >
          {/* <PermissionWrapper requiredPermissions={['Edit']} className="!block" > */}
          <Button type="text" className="w-full">
            {t(`lab.manage.restart`)}
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

  // 描述区域 - 左右布局，左侧显示creator，右侧显示启动/停止按钮
  const descSlot = (item: any) => {
    const isRunning = item.state === 'running';
    const isStarting = item.state === 'starting';
    const isStopping = item.state === 'stopping';

    return (
      <div className="flex justify-between items-center w-full">
        <p className="font-mini text-[var(--color-text-3)] m-0">
          {`creator: ${item.created_by || '--'}`}
        </p>
        <div className="flex gap-1">
          {!isRunning && !isStarting && (
            <Button
              // type="link"
              color="green" variant="link"
              size="small"
              icon={<PlayCircleOutlined />}
              onClick={(e) => handleStart(item.id, e)}
              loading={isStarting}
              className="text-green-600 hover:text-green-700"
            >
              启动
            </Button>
          )}
          {/* {(isRunning || isStarting) && (
            <Button
              type="text"
              size="small"
              icon={<PauseCircleOutlined />}
              onClick={(e) => handleStop(item.id, e)}
              loading={isStopping}
              className="text-red-600 hover:text-red-700"
            >
              停止
            </Button>
          )} */}
          <Button
            // type="link"
            size="small"
            color="danger" variant="link"
            icon={<PauseCircleOutlined />}
            onClick={(e) => handleStop(item.id, e)}
            loading={isStopping}
            className="text-red-600 hover:text-red-700"
          >
            停止
          </Button>
        </div>
      </div>
    );
  };

  // 卡片点击
  const handleCardClick = (item: any) => {
    console.log(item);
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
      await deleteEnv(id);
      message.success('环境删除成功');
      fetchEnvs(); // 刷新列表
    } catch (e) {
      console.error('删除环境失败:', e);
      message.error('删除环境失败');
    } finally {
      setLoading(false);
    }
  };

  // 搜索
  const handleSearch = () => {
    // 搜索逻辑
  };

  return (
    <>
      <div className={`w-full h-full ${stlyes.segmented}`}>
        {/* <Segmented options={tabOptions} value={activeTab} onChange={(value) => setActiveTab(value)} /> */}
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
      <LabEnvModal ref={modalRef} onSuccess={fetchEnvs} />
    </>
  )
};

export default EnvManage;