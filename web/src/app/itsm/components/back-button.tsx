"use client";

import { useRouter } from 'next/navigation';
import { ArrowLeftOutlined } from '@ant-design/icons';
import { Button, Tooltip, type ButtonProps } from 'antd';

type ItsmBackButtonProps = Pick<ButtonProps, 'href' | 'onClick' | 'disabled'> & {
  label: string;
};

/** 统一返回入口；目标与未保存检查由页面决定。 */
export function ItsmBackButton({ label, href, onClick, ...props }: ItsmBackButtonProps) {
  const router = useRouter();
  return <Tooltip title={label}>
    <Button {...props} href={href} onClick={event => {
      onClick?.(event);
      if (!href || props.disabled || event.defaultPrevented || event.button !== 0 || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
      event.preventDefault();
      router.push(href);
    }} aria-label={label} icon={<ArrowLeftOutlined />} className="shrink-0" />
  </Tooltip>;
}
