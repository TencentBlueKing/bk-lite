import React from 'react';
import Layout from '@theme/Layout';
import Link from '@docusaurus/Link';
import styles from './pricing.module.css';

// 价格方案数据
const pricingPlans = [
  {
    name: '社区版',
    price: '免费',
    description: '开箱可用的轻量化基础能力，适合个人或小团队快速体验与使用。',
    features: [
      '提供基础直控与可视化看板能力',
      '支持应用与主机的基本健康呈现',
      '支持邮件/企微等基础告警通知',
      '提供 ChatOps 基础智能问答与协助',
      '采用轻量单节点即可快速部署',
      '支持常见日志的基础检索与查看',
      '提供社区文档与示例快速上手',
      '通过社区渠道获取帮助与讨论'
    ],
    buttonText: '免费试用',
    buttonLink: 'https://bklite.canway.net/',
    highlighted: false,
  },
  {
    name: '标准版',
    price: '---',
    description: '覆盖核心运维与AI能力的完整解决方案,满足中小团队的日常场景需求。',
    features: [
      '提供全量监控、指标分析与可视化',
      '支持多渠道告警、收敛与升级策略',
      'Chatflow 支持可视化流程与任务编排',
      'OpsPilot 提供智能诊断与操作建议',
      '提供完整角色与权限管理体系',
      '支持多环境、多区域、多节点管理',
      '提供日志的可观测性增强能力',
      '自动生成 SLA、周报和趋势分析报告',
      '获得官方技术支持与更新保障'
    ],
    buttonText: '立即购买',
    buttonLink: '#',
    highlighted: true,
  },
  {
    name: '企业版',
    price: '---',
    description: '面向大型组织的全栈智能运维平台,提供高级能力、权限体系与企业级保障。',
    features: [
      '支持企业级组织、角色与权限分级',
      '支持大规模复杂集群的集中化管理',
      '提供智能根因分析与全链路判断',
      '支持自动化修复策略实现告警闭环',
      '可集成企业自有工具与流程系统',
      '支持私有化部署与大模型本地化',
      '提供审计、加密、高可用等安全能力',
      '支持 SSO/LDAP 等企业统一认证系统',
      '提供灰度、隔离、优先级等运维策略',
      '专属技术顾问与企业级服务保障'
    ],
    buttonText: '联系商务团队',
    buttonLink: '#',
    highlighted: false,
  },
];

function PricingCard({ plan }) {
  return (
    <div className={`${styles.pricingCard} ${plan.highlighted ? styles.highlighted : ''}`}>
      {plan.highlighted && <div className={styles.popularBadge}>推荐</div>}
      <div className={styles.cardHeader}>
        <h3 className={styles.planName}>{plan.name}</h3>
        <p className={styles.description}>{plan.description}</p>
        <div className={styles.priceContainer}>
          <span className={styles.price}>{plan.price}</span>
        </div>
      </div>

      <Link
        to={plan.buttonLink}
        className={`${styles.ctaButton} ${plan.highlighted ? styles.ctaButtonPrimary : ''}`}
      >
        {plan.buttonText}
      </Link>

      <div className={styles.features}>
        <h4 className={styles.featuresTitle}>功能列表</h4>
        <ul className={styles.featuresList}>
          {plan.features.map((feature, index) => (
            <li key={index} className={styles.featureItem}>
              <span className={styles.checkIcon}>✓</span>
              <span>{feature}</span>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}

export default function Pricing() {
  return (
    <Layout
      title="价格"
      description="BlueKing Lite 价格方案 - 选择适合您的版本">
      <div className={styles.pricingContainer}>
        <div className={styles.pricingHeader}>
          <h1 className={styles.title}>BlueKing Lite</h1>
          <p className={styles.subtitle}>AI 原生的轻量化运维平台，重塑智能运维体验</p>
        </div>

        <div className={styles.pricingGrid}>
          {pricingPlans.map((plan, index) => (
            <PricingCard key={index} plan={plan} />
          ))}
        </div>
      </div>
    </Layout>
  );
}
