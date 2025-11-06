'use client';
import React, { useState } from 'react';
import { useRouter } from 'next/navigation';
import BottomTabBar from '@/components/bottom-tab-bar';
import LanguageSelector from '@/components/language-selector';
import ImageCropper from '@/components/image-cropper';
import { useAuth } from '@/context/auth';
import { useTheme } from '@/context/theme';
import { useTranslation } from '@/utils/i18n';
import { List, Avatar, Switch, Toast, Dialog, ActionSheet, ImageViewer } from 'antd-mobile';
import {
  CameraOutline,
  PictureOutline,
} from 'antd-mobile-icons';

export default function ProfilePage() {
  const { t } = useTranslation();
  const { toggleTheme, isDark } = useTheme();
  const { userInfo, logout, isLoading: authLoading } = useAuth();
  const router = useRouter();

  const [avatarActionVisible, setAvatarActionVisible] = useState(false);
  const [changeAvatarVisible, setChangeAvatarVisible] = useState(false);
  const [imageViewerVisible, setImageViewerVisible] = useState(false);
  const [imageToCrop, setImageToCrop] = useState<string | null>(null);
  const [croppingImage, setCroppingImage] = useState(false);

  const avatarSrc = '/avatars/01.svg'; // TODO: 从 userInfo 获取头像

  // 点击头像
  const handleAvatarClick = () => {
    setAvatarActionVisible(true);
  };

  // 查看头像
  const handleViewAvatar = () => {
    setAvatarActionVisible(false);
    setImageViewerVisible(true);
  };

  // 更改头像
  const handleChangeAvatar = () => {
    setAvatarActionVisible(false);
    setChangeAvatarVisible(true);
  };

  // 选择相机
  const handleCamera = async () => {
    setChangeAvatarVisible(false);
    try {
      // 创建文件选择 input 元素（相机）
      const input = document.createElement('input');
      input.type = 'file';
      input.accept = 'image/*';
      input.capture = 'environment'; // 调用后置摄像头

      input.onchange = async (e: Event) => {
        const target = e.target as HTMLInputElement;
        const file = target.files?.[0];
        if (file) {
          // 读取文件并转换为 base64
          const reader = new FileReader();
          reader.onload = (event) => {
            const imageUrl = event.target?.result as string;
            console.log('拍照成功:', file.name);
            // 打开裁剪界面
            setImageToCrop(imageUrl);
            setCroppingImage(true);
          };
          reader.readAsDataURL(file);
        }
      };

      input.click();
    } catch (error) {
      console.error('相机调用失败:', error);
      Toast.show({
        content: '无法打开相机',
        icon: 'fail',
      });
    }
  };

  // 裁剪完成
  const handleCropComplete = async (croppedImage: string) => {
    setCroppingImage(false);
    setImageToCrop(null);

    Toast.show({
      content: '图片处理成功',
      icon: 'success',
    });

    console.log('裁剪后的图片:', croppedImage.substring(0, 50) + '...');
    // TODO: 上传到服务器
    // TODO: 更新头像显示
  };

  // 取消裁剪
  const handleCropCancel = () => {
    setCroppingImage(false);
    setImageToCrop(null);
  };

  // 选择相册
  const handleGallery = async () => {
    setChangeAvatarVisible(false);
    try {
      // 创建文件选择 input 元素（相册）
      const input = document.createElement('input');
      input.type = 'file';
      input.accept = 'image/*';

      input.onchange = async (e: Event) => {
        const target = e.target as HTMLInputElement;
        const file = target.files?.[0];
        if (file) {
          // 验证文件大小（限制 5MB）
          if (file.size > 5 * 1024 * 1024) {
            Toast.show({
              content: '图片大小不能超过 5MB',
              icon: 'fail',
            });
            return;
          }

          // 验证文件类型
          if (!file.type.startsWith('image/')) {
            Toast.show({
              content: '请选择图片文件',
              icon: 'fail',
            });
            return;
          }

          // 读取文件并转换为 base64
          const reader = new FileReader();
          reader.onload = (event) => {
            const imageUrl = event.target?.result as string;
            console.log('图片已选择:', file.name, '大小:', (file.size / 1024).toFixed(2), 'KB');
            // 打开裁剪界面
            setImageToCrop(imageUrl);
            setCroppingImage(true);
          };
          reader.readAsDataURL(file);
        }
      };

      input.click();
    } catch (error) {
      console.error('相册打开失败:', error);
      Toast.show({
        content: '无法打开相册',
        icon: 'fail',
      });
    }
  };

  const handleLogoutClick = () => {
    Dialog.confirm({
      content: t('auth.logoutConfirm'),
      confirmText: t('common.confirm'),
      cancelText: t('common.cancel'),
      onConfirm: async () => {
        try {
          await logout();
        } catch (error) {
          console.error('退出登录失败:', error);
          Toast.show({
            content: t('auth.logoutFailed'),
            icon: 'fail',
          });
        }
      },
    });
  };

  return (
    <div className="flex flex-col h-full bg-[var(--color-background-body)]">
      {/* 顶部导航栏 */}
      <div className="flex items-center justify-center px-4 py-3 bg-[var(--color-bg)]">
        <h1 className="text-lg font-medium text-[var(--color-text-1)]">
          {t('navigation.profile')}
        </h1>
      </div>

      {/* 用户信息卡片 */}
      <div className="mx-4 mt-4 mb-6 p-5 bg-[var(--color-bg)] rounded-2xl shadow-sm">
        <div className="flex items-center">
          <Avatar
            src={avatarSrc}
            style={{ '--size': '56px' }}
            className="mr-3 cursor-pointer"
            onClick={handleAvatarClick}
          />
          <div className="flex-1 min-w-0">
            <h2 className="text-lg font-semibold text-[var(--color-text-1)] mb-1 truncate">
              {userInfo?.display_name || userInfo?.username || '用户'}
            </h2>
            <span className="text-[var(--color-text-3)] text-xs font-medium truncate block">
              用户名:{userInfo?.username}
            </span>
          </div>
          {userInfo?.domain && (
            <div className="inline-flex items-center px-2 py-0.5 bg-blue-500 rounded">
              <span className="text-white text-xs font-medium">
                {userInfo.domain}
              </span>
            </div>
          )}
        </div>
      </div>

      {/* 功能菜单 */}
      <div className="flex-1">
        <div className="mx-4 mb-4 bg-[var(--color-bg)] rounded-2xl shadow-sm overflow-hidden">
          <List>
            <List.Item
              prefix={
                <div className="flex items-center justify-center w-7 h-7 bg-[var(--color-primary-bg-active)] rounded-lg mr-2.5">
                  <span className="iconfont icon-zhanghaoyuanquan text-[var(--color-primary)] text-lg"></span>
                </div>
              }
              onClick={() => {
                router.push('/profile/accountDetails');
              }}
              clickable
            >
              <span className="text-[var(--color-text-1)] text-base font-medium">
                {t('common.accountsAndSecurity')}
              </span>
            </List.Item>
          </List>
        </div>

        {/* 设置选项 */}
        <div className="mx-4 mb-4 bg-[var(--color-bg)] rounded-2xl shadow-sm overflow-hidden">
          <List>
            <LanguageSelector />
            <List.Item
              prefix={
                <div className="flex items-center justify-center w-7 h-7 bg-[var(--color-primary-bg-active)] rounded-lg mr-2.5">
                  <span className="text-[var(--color-primary)] text-base">
                    🌙
                  </span>
                </div>
              }
              extra={
                <Switch
                  checked={isDark}
                  onChange={toggleTheme}
                  style={{
                    '--height': '22px',
                    '--width': '40px',
                  }}
                />
              }
            >
              <span className="text-[var(--color-text-1)] text-base font-medium">
                {t('common.darkMode')}
              </span>
            </List.Item>
          </List>
        </div>

        {/* 退出登录按钮 */}
        <div className="mx-4 mt-6 mb-4">
          <div
            className="bg-[var(--color-bg)] rounded-2xl shadow-sm overflow-hidden cursor-pointer active:opacity-70"
            onClick={authLoading ? undefined : handleLogoutClick}
          >
            <div className="py-2.5 text-center">
              <span
                className={`text-base font-medium ${authLoading ? 'text-[var(--color-text-3)]' : 'text-red-500'
                  }`}
              >
                {authLoading ? t('common.loggingOut') : t('common.logout')}
              </span>
            </div>
          </div>
        </div>
      </div>

      {/* 底部导航 */}
      <BottomTabBar />

      {/* 头像操作 ActionSheet */}
      <ActionSheet
        visible={avatarActionVisible}
        onClose={() => setAvatarActionVisible(false)}
        actions={[
          {
            text: <span className="text-[var(--color-text-1)]">查看头像</span>,
            key: 'view',
            onClick: handleViewAvatar,
          },
          {
            text: <span className="text-[var(--color-text-1)]">更改头像</span>,
            key: 'change',
            onClick: handleChangeAvatar,
          },
        ]}
      />

      {/* 更改头像方式选择 */}
      <ActionSheet
        visible={changeAvatarVisible}
        onClose={() => setChangeAvatarVisible(false)}
        actions={[]}
        extra={
          <div className="w-full flex justify-around py-6 px-8">
            <div
              className="flex flex-col items-center cursor-pointer active:opacity-70"
              onClick={handleCamera}
            >
              <div className="w-16 h-16 flex items-center justify-center bg-[var(--color-primary-bg)] rounded-full mb-2">
                <CameraOutline fontSize={60} className="text-[var(--color-text-1)]" />
              </div>
              <span className="text-sm text-[var(--color-text-1)]">相机</span>
            </div>
            <div
              className="flex flex-col items-center cursor-pointer active:opacity-70"
              onClick={handleGallery}
            >
              <div className="w-16 h-16 flex items-center justify-center bg-[var(--color-primary-bg)] rounded-full mb-2">
                <PictureOutline fontSize={60} className="text-[var(--color-text-1)]" />
              </div>
              <span className="text-sm text-[var(--color-text-1)]">相册</span>
            </div>
          </div>
        }
      />

      {/* 头像预览 */}
      <ImageViewer
        image={avatarSrc}
        visible={imageViewerVisible}
        onClose={() => setImageViewerVisible(false)}
      />

      {/* 图片裁剪 */}
      {croppingImage && imageToCrop && (
        <ImageCropper
          image={imageToCrop}
          onCropComplete={handleCropComplete}
          onCancel={handleCropCancel}
        />
      )}
    </div>
  );
}
