import { FC } from 'react';
import styles from './index.module.scss';
import EllipsisWithTooltip from '@/components/ellipsis-with-tooltip';

interface UserAvatarProps {
  userName: string;
  className?: string;
  size?: 'small' | 'default';
}

const getRandomColor = () => {
  const colors = [
    '#875CFF',
    '#FF9214',
    '#00CBA6',
    '#1272FF',
    '#f56a00',
    '#ffbf00',
    '#00a2ae',
    '#9c27b0',
    '#4caf50',
  ];
  const index = Math.floor(Math.random() * colors.length);
  return colors[index];
};

const UserAvatar: FC<UserAvatarProps> = ({
  userName,
  size = 'default',
  className = '',
}) => {
  if (!userName) return null;

  return (
    <div className={`${styles['user-avatar-wrapper']} ${className}`.trim()}>
      <span
        className={`${styles['member-circle']} ${size === 'small' ? styles.small : ''}`}
        style={{ background: getRandomColor() }}
      >
        {userName.slice(0, 1).toUpperCase()}
      </span>
      <EllipsisWithTooltip text={userName} className={styles['member-name']} />
    </div>
  );
};

export default UserAvatar;

export type { UserAvatarProps };
