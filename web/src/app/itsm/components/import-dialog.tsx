'use client';
import { Alert, Button, Upload } from 'antd';
import { ImportOutlined } from '@ant-design/icons';
import { useState } from 'react';
import { ItsmModal } from './interaction-surfaces';

/** 文件选择与实际写入分开；失败保留文件，取消不触发导入。 */
export function ImportDialog({ accept, onImport }: { accept: string; onImport: (file: File) => Promise<boolean> }) {
  const [open,setOpen]=useState(false);
  const [file,setFile]=useState<File>();
  const [error,setError]=useState('');
  return <><Button aria-label="导入" icon={<ImportOutlined />} onClick={()=>{setFile(undefined);setError('');setOpen(true);}}>导入</Button>
    <ItsmModal title="导入" open={open} onCancel={()=>setOpen(false)} okText="导入" okButtonProps={{disabled:!file}} onOk={async()=>{
      if (!file) return;
      try {if(await onImport(file))setOpen(false);else setError('导入未完成，请检查文件后重试。');}catch(error){setError(error instanceof Error?error.message:'导入失败');}
    }}>
      <Upload accept={accept} maxCount={1} fileList={file?[{uid:'selected',name:file.name,status:'done'}]:[]} beforeUpload={next=>{setFile(next);setError('');return false;}} onRemove={()=>{setFile(undefined);return true;}}><Button>选择文件</Button></Upload>
      <p className="mt-3 text-sm text-[var(--color-text-3)]">导入会新增一份副本，自动生成唯一标识，不覆盖已有数据。</p>
      {error && <Alert type="error" message={error} />}
    </ItsmModal>
  </>;
}
