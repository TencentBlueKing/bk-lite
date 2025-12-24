import { message as antdMessage, notification as antdNotification, Modal } from 'antd';

// 配置全局 message
antdMessage.config({
  top: 80,
  maxCount: 2,
  duration: 3,
  prefixCls: 'ant-message',
  getContainer: () => document.body,
});

// 配置全局 notification
antdNotification.config({
  placement: 'topRight',
  top: 80,
  duration: 4.5,
  prefixCls: 'ant-notification',
  getContainer: () => document.body,
});

// 配置全局 Modal
Modal.config({
  rootPrefixCls: 'ant',
});

export const message = antdMessage;
export const notification = antdNotification;
export { Modal };
