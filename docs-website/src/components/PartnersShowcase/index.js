import React from 'react';
import clsx from 'clsx';
import Heading from '@theme/Heading';
import styles from './styles.module.css';

const Partners = [
  {
    name: '企业名字1',
    logo: '🐧',
    description: '科技巨头',
  },
  {
    name: '企业名字2',
    logo: '🛒',
    description: '电商云计算',
  },
  {
    name: '企业名字3',
    logo: '🔍',
    description: 'AI搜索',
  },
  {
    name: '企业名字4',
    logo: '📱',
    description: '移动互联网',
  },
  {
    name: '企业名字5',
    logo: '🍔',
    description: '生活服务',
  },
  {
    name: '企业名字6',
    logo: '�',
    description: '出行服务',
  },
  {
    name: '企业名字7',
    logo: '📦',
    description: '电商物流',
  },
  {
    name: '企业名字8',
    logo: '�',
    description: '智能硬件',
  },
  {
    name: '企业名字9',
    logo: '�',
    description: '通信技术',
  },
  {
    name: '企业名字10',
    logo: '🏦',
    description: '金融服务',
  },
  {
    name: '企业名11',
    logo: '💳',
    description: '银行业务',
  },
  {
    name: '企业名字12',
    logo: '📶',
    description: '运营商',
  },
];

const Stats = [
  {
    number: '100+',
    label: '企业客户',
    icon: '🏢',
  },
  {
    number: '1M+',
    label: '日活用户',
    icon: '👥',
  },
  {
    number: '99.9%',
    label: '系统稳定性',
    icon: '⚡',
  },
  {
    number: '24/7',
    label: '技术支持',
    icon: '🛠️',
  },
];

function PartnerCard({ name, logo, description }) {
  return (
    <div className={styles.partnerCard}>
      <div className={styles.partnerLogo}>
        <span className={styles.logoEmoji}>{logo}</span>
      </div>
      <div className={styles.partnerName}>{name}</div>
    </div>
  );
}

function StatCard({ number, label, icon }) {
  return (
    <div className={clsx('col col--3', styles.statCol)}>
      <div className={styles.statCard}>
        <div className={styles.statIcon}>
          <span className={styles.iconEmoji}>{icon}</span>
        </div>
        <div className={styles.statNumber}>{number}</div>
        <div className={styles.statLabel}>{label}</div>
      </div>
    </div>
  );
}

export default function PartnersShowcase() {
  return (
    <section className={styles.partnersSection}>
      <div className="container">
        {/* Statistics Section */}
        {/* <div className={styles.statsSection}>
          <div className="text--center margin-bottom--xl">
            <Heading as="h2" className={styles.sectionTitle}>
              值得信赖的选择
            </Heading>
            <p className={styles.sectionSubtitle}>
              全球众多知名企业选择BKLite构建AI驱动的数字化平台
            </p>
          </div>
          <div className="row">
            {Stats.map((props, idx) => (
              <StatCard key={idx} {...props} />
            ))}
          </div>
        </div> */}

        {/* Partners Logo Wall */}
        {/* <div className={styles.partnersLogoWall}>
          <div className="text--center margin-bottom--xl">
            <Heading as="h3" className={styles.partnersTitle}>
              生态合作伙伴
            </Heading>
            <p className={styles.partnersSubtitle}>
              与行业领先企业深度合作，共建数字化生态
            </p>
          </div>
          <div className={styles.logoGrid}>
            {Partners.map((props, idx) => (
              <PartnerCard key={idx} {...props} />
            ))}
          </div>
        </div> */}
      </div>
    </section>
  );
}
