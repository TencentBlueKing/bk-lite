import { message as antdMessage, notification as antdNotification, Modal } from 'antd';

// 配置全局 message。请求拦截器另经 requestErrorToast 保证 maxCount / 同文案去重生效。
// top 避开顶栏（约 56px）及常见二级导航，避免挡住「集成」等入口。
antdMessage.config({
  top: 100,
  maxCount: 2,
  duration: 3,
  prefixCls: 'ant-message',
  getContainer: () => document.body,
});

// 配置全局 notification
antdNotification.config({
  placement: 'topRight',
  top: 100,
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
