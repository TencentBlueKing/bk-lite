import React, { useState } from 'react';
import clsx from 'clsx';
import Link from '@docusaurus/Link';
import Heading from '@theme/Heading';
import styles from './styles.module.css';

export default function FinalCTA() {
  const [showQRCode, setShowQRCode] = useState(false);

  const handleJoinCommunity = (e) => {
    e.preventDefault();
    setShowQRCode(true);
  };

  const closeQRCode = () => {
    setShowQRCode(false);
  };

  return (
    <section className={styles.finalCTA}>
      <div className="container">
        <div className={styles.ctaContainer}>
          <div className={styles.ctaContent}>
            <Heading as="h2" className={styles.ctaTitle}>
              开启您的 AI 驱动运维探索之旅
            </Heading>
            <p className={styles.ctaDescription}>
              BlueKing Lite 提供轻量化的运维开源方案，从部署到运维，从监控到自动化，帮助社区和团队快速构建智能运维能力。现在就上手，体验下一代开源运维平台。
            </p>
            <div className={styles.ctaButtons}>
              <Link
                className={clsx(styles.ctaButton, styles.ctaPrimary)}
                to="https://github.com/TencentBlueKing/bk-lite"
              >
                ⭐ 支持我们
              </Link>
              <button
                className={clsx(styles.ctaButton, styles.ctaSecondary)}
                onClick={handleJoinCommunity}
              >
                🌍 加入社区
              </button>
            </div>
            <div className={styles.ctaFeatures}>
              <div className={styles.feature}>
                <span className={styles.featureIcon}>⚡</span>
                <span>5分钟快速上手</span>
              </div>
              <div className={styles.feature}>
                <span className={styles.featureIcon}>🛠️</span>
                <span>模块化设计</span>
              </div>
              <div className={styles.feature}>
                <span className={styles.featureIcon}>🤝</span>
                <span>开源社区共建</span>
              </div>
            </div>
          </div>
        </div>
      </div>
      
      {/* QR Code Modal */}
      {showQRCode && (
        <div className={styles.qrModal} onClick={closeQRCode}>
          <div className={styles.qrModalContent} onClick={(e) => e.stopPropagation()}>
            <button className={styles.closeButton} onClick={closeQRCode}>
              ×
            </button>
            <h3 className={styles.qrTitle}>扫码加入社区</h3>
            <div className={styles.qrImageContainer}>
              <img 
                src="/img/community-qrcode.png" 
                alt="社区二维码" 
                className={styles.qrImage}
              />
            </div>
            <p className={styles.qrDescription}>
              扫描二维码加入 BlueKing Lite 开源社区，与开发者们一起交流讨论
            </p>
          </div>
        </div>
      )}
    </section>
  );
}