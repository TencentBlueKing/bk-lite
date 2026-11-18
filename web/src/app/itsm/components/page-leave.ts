'use client';

import { Modal } from 'antd';
import { useRouter } from 'next/navigation';
import { useEffect, useRef } from 'react';

export function confirmLeave(dirty: boolean, leave: () => void) {
  if (!dirty) { leave(); return; }
  Modal.confirm({ zIndex: 1400, title: '放弃未保存的修改？', content: '离开后，本次修改不会保存。', okText: '放弃修改', cancelText: '继续编辑', onOk: leave });
}

export function usePageLeave(dirty: boolean) {
  const router = useRouter();
  const confirmed = useRef(false);
  useEffect(() => {
    if (!dirty) {confirmed.current=false;return;}
    const beforeUnload = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = ''; };
    const click = (event: MouseEvent) => {
      const link=(event.target as HTMLElement).closest?.('a[href]') as HTMLAnchorElement | null;
      if (!link || link.target==='_blank' || link.hasAttribute('download') || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey || event.button !== 0 || link.href===location.href) return;
      event.preventDefault();event.stopImmediatePropagation();
      confirmLeave(true,()=>{confirmed.current=true;window.removeEventListener('beforeunload',beforeUnload);const target = new URL(link.href);
        if (target.origin === location.origin) router.push(target.pathname + target.search + target.hash);
        else location.assign(link.href);});
    };
    // 在历史导航提交前取消，避免 popstate 后回跳破坏 Next.js 路由状态。
    const navigation = (window as Window & { navigation?: EventTarget }).navigation;
    const back = (event: Event) => {
      const kind=(event as Event & { navigationType?: string }).navigationType;
      if (confirmed.current) {confirmed.current=false;return;}
      if ((kind==='traverse' || kind==='push') && event.cancelable) {
        if (!window.confirm('放弃未保存的修改？离开后，本次修改不会保存。')) event.preventDefault();
        else window.removeEventListener('beforeunload',beforeUnload);
      }
    };
    window.addEventListener('beforeunload', beforeUnload);
    navigation?.addEventListener('navigate',back);
    document.addEventListener('click',click,true);
    return () => {window.removeEventListener('beforeunload',beforeUnload);navigation?.removeEventListener('navigate',back);document.removeEventListener('click',click,true);};
  }, [dirty, router]);
  return (leave: () => void) => confirmLeave(dirty, () => {confirmed.current=dirty;leave();});
}
