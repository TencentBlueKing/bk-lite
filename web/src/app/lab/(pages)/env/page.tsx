"use client";
import { Menu, Button, message, Tooltip, Tag } from 'antd';
import { PlayCircleOutlined, PauseCircleOutlined, RedoOutlined, ReloadOutlined } from '@ant-design/icons';
import stlyes from '@/app/lab/styles/index.module.scss';
import { useState, useEffect, useRef } from 'react';
import EntityList from '@/components/entity-list';
import { ModalRef } from '@/app/lab/types';
import { useTranslation } from '@/utils/i18n';
import useLabEnv from '@/app/lab/api/env';
import LabEnvModal from './labEnvModal';
import PermissionWrapper from "@/components/permission"

type ContarinerState = 'starting' | 'stopping' | 'running' | 'stopped' | 'error';

const EnvManage = () => {
  const { t } = useTranslation();
  const modalRef = useRef<ModalRef>(null);
  const {
    getEnvListWithStatus,
    deleteEnv,
    startEnv,
    stopEnv,
    restartEnv,
  } = useLabEnv();

  const [tableData, setTableData] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);

  // 请求环境列表
  const fetchEnvs = async () => {
    setLoading(true);
    try {
      // 使用新接口一次性获取环境列表和状态
      const res = await getEnvListWithStatus();
      const _res = res?.map((item: any) => {
        return {
          ...item,
          icon: 'tucengshuju',
          creator: item?.created_by || '--',
        }
      });
      console.log(_res);
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

  const changeState = (id: string | number, state: ContarinerState) => {
    const _env = tableData.map((item: any) => {
      if (item.id === id) {
        return {
          ...item,
          state
        }
      }
      return item;
    });
    setTableData(_env);
  }

  // 启动环境
  const handleStart = async (id: string | number, e: React.MouseEvent) => {
    e.stopPropagation();
    message.info('环境启动中');
    changeState(id, 'starting');
    try {
      await startEnv(id);
      message.success('环境启动成功');
    } catch (error) {
      console.error('启动环境失败:', error);
      message.error('启动环境失败');
    } finally {
      fetchEnvs();
    }
  };

  // 重启环境
  const handleRestart = async (id: string | number) => {
    message.info("环境重启中");
    changeState(id, 'starting');
    try {
      await restartEnv(id);
      message.success('环境重启成功');

    } catch (e) {
      console.log(e);
      message.error('重启环境失败')
    } finally {
      fetchEnvs();
    }
  };

  // 停止环境
  const handleStop = async (id: string | number, e: React.MouseEvent) => {
    e.stopPropagation();
    message.info("停止环境中");
    changeState(id, 'stopping');
    try {
      await stopEnv(id);
      message.success('环境停止成功');

    } catch (error) {
      console.error('停止环境失败:', error);
      message.error('停止环境失败');
    } finally {
      fetchEnvs();
    }
  };

  const menuActions = (item: any) => {
    return (
      <Menu onClick={(e) => e.domEvent.preventDefault()}>
        <Menu.Item
          className="!p-0"
          onClick={() => handleEdit({ type: 'edit', form: item })}
        >
          <PermissionWrapper requiredPermissions={['Edit']} className="!block" >
            <Button type="text" className="w-full">
              {t(`common.edit`)}
            </Button>
          </PermissionWrapper>
        </Menu.Item>
        {item?.name !== "default" && (
          <Menu.Item className="!p-0" onClick={() => handleDel(item.id)}>
            <PermissionWrapper requiredPermissions={['Delete']} className="!block" >
              <Button type="text" className="w-full" disabled={['stopped', 'error'].includes(item?.state) ? false : true}>
                {t(`common.delete`)}
              </Button>
            </PermissionWrapper>
          </Menu.Item>
        )}
      </Menu>
    )
  };

  const descSlot = (item: any) => {
    const isRunning = item.state === 'running';
    const isStarting = item.state === 'starting';
    const isStopping = item.state === 'stopping';
    const containers: any[] = item.container_status?.containers || [];


    // 状态标签颜色映射
    const getStateTagColor = (state: string): 'success' | 'processing' | 'error' | 'warning' | 'default' => {
      const colorMap: Record<string, 'success' | 'processing' | 'error' | 'warning' | 'default'> = {
        'running': 'success',
        'stopped': 'default',
        'starting': 'processing',
        'stopping': 'warning',
        'error': 'error'
      };
      return colorMap[state] || 'default';
    };

    const getContainerToolTip = () => {
      let tooltip = '';
      containers.forEach((item: any) => {
        tooltip += `${item.State} / `
      });
      return tooltip;
    };

    return (
      <div className="flex justify-between items-center w-full gap-3">
        <div className="flex items-center gap-2 flex-1 min-w-0 ">
          <span className='font-mini'>State: </span>
          <Tag color={getStateTagColor(item.state)} className="!m-0 font-mini">
            {item.state}
          </Tag>
          {item.state === 'running' && (
            <Tooltip title={getContainerToolTip}>
              <Tag color="blue" className="!m-0 font-mini">
                Containers: {containers.length}
              </Tag>
            </Tooltip>
          )}
        </div>
        <div className="flex gap-1.5 flex-shrink-0">
          <Tooltip title="重启">
            <Button
              type="text"
              size="small"
              disabled={['starting', 'stopping', 'stopped'].includes(item.state)}
              icon={<RedoOutlined />}
              onClick={(e) => {
                e.stopPropagation();
                handleRestart(item.id);
              }}
              className={
                ['starting', 'stopping', 'stopped'].includes(item.state) ?
                  "" :
                  "!text-blue-500 hover:!bg-blue-50 hover:!text-blue-600 transition-colors"
              }
            />
          </Tooltip>
          {!isRunning && !isStarting && (
            <Tooltip title="启动">
              <Button
                type="text"
                size="small"
                disabled={['stopping'].includes(item.state)}
                icon={<PlayCircleOutlined />}
                onClick={(e) => handleStart(item.id, e)}
                loading={isStarting}
                className={
                  !['stopping'].includes(item.state) ? "!text-green-500 hover:!bg-green-50 hover:!text-green-600 transition-colors" : ''
                }
              />
            </Tooltip>
          )}
          {(isRunning || isStarting) && (
            <Tooltip title="停止">
              <Button
                type="text"
                size="small"
                icon={<PauseCircleOutlined />}
                disabled={['starting'].includes(item.state)}
                onClick={(e) => handleStop(item.id, e)}
                loading={isStopping}
                className={
                  !['starting'].includes(item.state) ? "!text-red-500 hover:!bg-red-50 hover:!text-red-600 transition-colors" : ''
                }
              />
            </Tooltip>
          )}
        </div>
      </div>
    );
  };

  // 卡片点击
  // const handleCardClick = (item: any) => {
  //   console.log(item);
  //   // 可跳转详情或弹窗
  // };

  // 新增
  const handleAdd = () => {
    // 新增逻辑
    modalRef.current?.showModal({ type: 'add' });
  };

  // 编辑
  const handleEdit = (data: any) => {
    modalRef.current?.showModal(data);
  };

  // 容器状态
  // const getContainerStatus = async (item: any) => {
  //   try {
  //     const data = await getEnvStatus(item.id);
  //     console.log(data);
  //   } catch (e) {
  //     console.log(e)
  //   }
  // };

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
            // onCardClick={handleCardClick}
            openModal={handleAdd}
            onSearch={handleSearch}
            descSlot={descSlot}
            operateSection={
              <Button icon={<ReloadOutlined />} color='default' variant='link' className='w-full' onClick={fetchEnvs} />
            }
          />
        </div>
      </div>
      <LabEnvModal ref={modalRef} onSuccess={fetchEnvs} />
    </>
  )
};

export default EnvManage;