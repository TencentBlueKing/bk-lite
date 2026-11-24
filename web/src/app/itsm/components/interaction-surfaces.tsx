'use client';

import { Alert, Button } from 'antd';
import { useEffect, useState, type ComponentProps, type ReactNode } from 'react';
import OperateModal from '@/components/operate-modal';
import OperateDrawer from '@/components/operate-drawer';

import { confirmLeave } from './page-leave';
export { confirmLeave, usePageLeave } from './page-leave';

function useDirty(open: boolean, value: unknown) {
  const serialized = JSON.stringify(value);
  const [snapshot, setSnapshot] = useState({ open, serialized });
  if (snapshot.open !== open) setSnapshot({ open, serialized });
  return open && snapshot.open && value !== undefined && snapshot.serialized !== serialized;
}

type ModalProps = ComponentProps<typeof OperateModal> & { formValue?: unknown };
export function ItsmModal({ formValue, onCancel, onOk, confirmLoading, open, children, ...props }: ModalProps) {
  const dirty = useDirty(!!open, formValue);
  const [saving,setSaving]=useState(false);
  const [error,setError]=useState('');
  useEffect(()=>{if(open)setError('');},[open]);
  const busy=!!confirmLoading || saving;
  return <OperateModal zIndex={1300} onOk={async event=>{if(busy)return;setSaving(true);setError('');try{await onOk?.(event);}catch(error){setError(error instanceof Error?error.message:'保存失败');}finally{setSaving(false);}}} okText="保存" cancelText="取消" {...props} open={open} confirmLoading={busy} cancelButtonProps={{...props.cancelButtonProps,disabled:busy || props.cancelButtonProps?.disabled}}
    closable={busy ? false : props.closable} keyboard={!busy && props.keyboard !== false} maskClosable={false}
    onCancel={event => { if (!busy) confirmLeave(dirty, () => onCancel?.(event)); }}>{error && <Alert type="error" message={error} />}{children}</OperateModal>;
}

type DrawerProps = Omit<ModalProps, 'styles' | 'classNames' | 'onCancel' | 'onOk' | 'footer' | 'width'> & {
  width?: number | string; onCancel?: () => void; onOk?: () => void | Promise<unknown>; footer?: ReactNode;
};
export function ItsmDrawer({ title, subTitle, open, onCancel, onOk, formValue, confirmLoading, footer, children, width = 860, okText = '保存', cancelText = '取消', okButtonProps, destroyOnHidden }: DrawerProps) {
  const dirty = useDirty(!!open, formValue);
  const [saving,setSaving]=useState(false);
  const [error,setError]=useState('');
  useEffect(()=>{if(open)setError('');},[open]);
  const busy=!!confirmLoading || saving;
  const save=async()=>{if(busy)return;setSaving(true);setError('');try{await onOk?.();}catch(error){setError(error instanceof Error?error.message:'保存失败');}finally{setSaving(false);}};
  const close = () => { if (!busy) confirmLeave(dirty, () => onCancel?.()); };
  return <OperateDrawer zIndex={1300} title={title} subTitle={subTitle} open={open} width={width} onClose={close}
    maskClosable={false} closable={!busy} keyboard={!busy} destroyOnHidden={destroyOnHidden}
    footer={footer !== undefined ? footer : onOk ? <><Button disabled={busy} onClick={close}>{cancelText}</Button><Button type="primary" {...okButtonProps} loading={busy} onClick={()=>void save()}>{okText}</Button></> : undefined}>
    {error && <Alert type="error" message={error} />}{children}
  </OperateDrawer>;
}
