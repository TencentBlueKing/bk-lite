import clsx from 'clsx';
import Link from '@docusaurus/Link';
import useDocusaurusContext from '@docusaurus/useDocusaurusContext';
import Layout from '@theme/Layout';
import HomepageFeatures from '@site/src/components/HomepageFeatures';
import PlatformShowcase from '@site/src/components/AIShowcase';
import PartnersShowcase from '@site/src/components/PartnersShowcase';
import FinalCTA from '@site/src/components/FinalCTA';
import LiquidNavbar from '@site/src/components/LiquidNavbar';
import React, { useState, useEffect } from 'react';
import confetti from 'canvas-confetti';
import styles from './index.module.css';

function HomepageHeader() {
  const [selectedVersion, setSelectedVersion] = useState('ai');
  
  // 版本配置
  const versions = {
    basic: {
      name: '基础版',
      command: 'curl -sSL https://bklite.ai/install.run | bash -',
      description: '核心功能，极简部署',
      icon: '⚡',
      color: '#6b7280',
      gradient: 'linear-gradient(135deg, #6b7280, #9ca3af)'
    },
    ai: {
      name: '智能版',
      command: 'curl -sSL https://bklite.ai/install.run | bash -s - --opspilot',
      description: 'AI驱动，智能运维',
      icon: '✨',
      color: '#3b82f6',
      gradient: 'linear-gradient(135deg, #3b82f6, #8b5cf6)'
    }
  };

  // 版本切换处理函数
  const handleVersionChange = (version) => {
    if (version !== selectedVersion) {
      setSelectedVersion(version);
    }
  };

  // 基础炮台效果
  const basicCannon = () => {
    confetti({
      particleCount: 100,
      spread: 70,
      origin: { y: 0.6 }
    });
  };

  // 随机方向效果
  const randomDirection = () => {
    function randomInRange(min, max) {
      return Math.random() * (max - min) + min;
    }

    confetti({
      angle: randomInRange(55, 125),
      spread: randomInRange(50, 70),
      particleCount: randomInRange(50, 100),
      origin: { y: 0.6 }
    });
  };

  // 逼真效果
  const realisticLook = () => {
    const count = 200;
    const defaults = {
      origin: { y: 0.7 }
    };

    function fire(particleRatio, opts) {
      confetti({
        ...defaults,
        ...opts,
        particleCount: Math.floor(count * particleRatio)
      });
    }

    fire(0.25, {
      spread: 26,
      startVelocity: 55,
    });

    fire(0.2, {
      spread: 60,
    });

    fire(0.35, {
      spread: 100,
      decay: 0.91,
      scalar: 0.8
    });

    fire(0.1, {
      spread: 120,
      startVelocity: 25,
      decay: 0.92,
      scalar: 1.2
    });

    fire(0.1, {
      spread: 120,
      startVelocity: 45,
    });
  };

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(versions[selectedVersion].command);
      
      // 添加视觉反馈 - 复制按钮样式变化
      const copyBtn = document.querySelector(`.${styles.copyButton}`);
      if (copyBtn) {
        copyBtn.classList.add(styles.copied);
        copyBtn.querySelector(`.${styles.copyIcon}`).textContent = '✅';
        
        // 2秒后恢复原状
        setTimeout(() => {
          copyBtn.classList.remove(styles.copied);
          copyBtn.querySelector(`.${styles.copyIcon}`).textContent = '📋';
        }, 2000);
      }
      
      // 随机选择一种撒花效果
      const effects = [basicCannon, randomDirection, realisticLook];
      const randomEffect = effects[Math.floor(Math.random() * effects.length)];
      randomEffect();
      
    } catch (err) {
      console.error('复制失败:', err);
      // 添加失败反馈
      const copyBtn = document.querySelector(`.${styles.copyButton}`);
      if (copyBtn) {
        copyBtn.style.background = 'rgba(239, 68, 68, 0.2)';
        copyBtn.style.color = '#ef4444';
        copyBtn.querySelector(`.${styles.copyIcon}`).textContent = '❌';
        
        setTimeout(() => {
          copyBtn.style.background = '';
          copyBtn.style.color = '';
          copyBtn.querySelector(`.${styles.copyIcon}`).textContent = '📋';
        }, 2000);
      }
    }
  };

  return (
    <header className={styles.heroBanner}>
      <div className={styles.heroBackground}>
        <div className={styles.floatingShapes}>
          <div className={styles.shape1}></div>
          <div className={styles.shape2}></div>
          <div className={styles.shape3}></div>
        </div>
      </div>
      <div className={styles.heroContent}>
        <div className={styles.heroAnimation}>
          <div className={styles.heroTitleAccent}>BlueKing Lite</div>
          <p className={styles.heroSubtitle}>
            AI 原生的轻量化运维平台，重塑智能运维体验
          </p>
          <div className={styles.heroStats}>
            <div className={styles.statCard}>
              <div className={styles.statValue}>AI原生</div>
            </div>
            <div className={styles.statCard}>
              <div className={styles.statValue}>渐进式体验</div>
            </div>
            <div className={styles.statCard}>
              <div className={styles.statValue}>轻量化架构</div>
            </div>
          </div>
          <div className={styles.quickInstall}>
            {/* 版本选择器 */}
            <div className={styles.versionSelector}>
              <div className={styles.versionTabs} data-selected={selectedVersion}>
                {Object.entries(versions).map(([key, version]) => (
                  <button
                    key={key}
                    className={`${styles.versionTab} ${selectedVersion === key ? styles.versionTabActive : ''}`}
                    onClick={() => handleVersionChange(key)}
                  >
                    <span className={styles.versionIcon}>{version.icon}</span>
                    <div className={styles.versionInfo}>
                      <div className={styles.versionName}>{version.name}</div>
                      <div className={styles.versionDesc}>{version.description}</div>
                    </div>
                  </button>
                ))}
              </div>
            </div>
            
            {/* 代码块 */}
            <div className={styles.codeBlock}>
              <div className={styles.codeContentWrapper}>
                <pre className={styles.codeContent}>
                  <code>{versions[selectedVersion].command}</code>
                </pre>
                <button 
                  className={styles.copyButton}
                  onClick={handleCopy}
                  title="复制脚本"
                  style={{
                    background: `${versions[selectedVersion].gradient.replace('135deg,', '135deg, ')}15`,
                    color: versions[selectedVersion].color
                  }}
                >
                  <span className={styles.copyIcon}>
                    📋
                  </span>
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </header>
  );
}

export default function Home() {
  const {siteConfig} = useDocusaurusContext();
  
  // 确保页面加载时滚动到顶部
  useEffect(() => {
    // 立即滚动到顶部
    window.scrollTo({
      top: 0,
      left: 0,
      behavior: 'instant'
    });
    
    // 使用requestAnimationFrame确保DOM渲染完成后再次检查
    const handleLoad = () => {
      requestAnimationFrame(() => {
        window.scrollTo({
          top: 0,
          left: 0,
          behavior: 'instant'
        });
      });
    };
    
    // 监听窗口加载完成
    if (document.readyState === 'complete') {
      handleLoad();
    } else {
      window.addEventListener('load', handleLoad);
    }
    
    // 延迟执行，确保所有动画开始后页面位置正确
    const timeoutId = setTimeout(() => {
      window.scrollTo({
        top: 0,
        left: 0,
        behavior: 'instant'
      });
    }, 100);
    
    return () => {
      window.removeEventListener('load', handleLoad);
      clearTimeout(timeoutId);
    };
  }, []);
  
  return (
    <Layout
      title={`${siteConfig.title} - 轻量级运维平台`}
      description="">
      <LiquidNavbar />
      <HomepageHeader />
      <main>
        <HomepageFeatures />
        <PlatformShowcase />
        <PartnersShowcase />
        <FinalCTA />
      </main>
    </Layout>
  );
}
