import clsx from 'clsx';
import Heading from '@theme/Heading';
import styles from './styles.module.css';
import { FaUserShield,FaVial,FaSearch, FaChartBar, FaBell, FaLaptopCode,FaCloud,FaChartLine } from 'react-icons/fa';
import { RiMindMap,RiFlowChart } from 'react-icons/ri';
import { HiOutlineDatabase,HiOutlineChip } from 'react-icons/hi';

const FeatureList = [
  {
    title: 'OpsPilot',
    icon: <RiMindMap color="var(--ifm-color-primary)" />,
    gradient: 'gradient-opspilot',
    badge: '智能中枢',
    highlights: ['运维大模型','知识图谱','领域智能体'],
    description: (
      <>
       融合大模型与知识图谱，结合领域智能体，打造运维智能中枢，驱动更精准、高效的故障诊断与修复
      </>
    ),
  },
  {
    title: '控制台',
    icon: <FaLaptopCode color="var(--ifm-color-primary)" />,
    gradient: 'gradient-7',
    badge: '智能门户',
    highlights: ['智能协同', '个性化门户','通知聚合'],
    description: (
      <>
        提供统一的应用入口与个性化门户，聚合多源通知，构建智能门户，提升运维与管理的协同效率。
      </>
    ),
  },    
  {
    title: '系统管理',
    icon: <FaUserShield color="var(--ifm-color-primary)" />,
    gradient: 'gradient-8',
    badge: '访问控制',
    highlights: ['多租户管理', '权限管控','审计合规'],
    description: (
      <>
        支持多租户管理与精细化权限控制，结合审计追踪，统一构建访问控制体系，全面保障系统的安全性与合规性。
      </>
    ),
  },  
  {
    title: 'CMDB',
    icon: <HiOutlineDatabase color="var(--ifm-color-primary)" />,
    gradient: 'gradient-3',
    badge: '资产地图',
    highlights: ['全面采集', '架构还原','数据可信赖'],
    description: (
      <>
        通过全面采集与架构还原，构建可信的资产地图，以一致可靠的数据支撑合规管理和运维决策
      </>
    ),
  },   
  {
    title: '监控中心',
    icon: <FaChartBar color="var(--ifm-color-primary)" />,
    gradient: 'gradient-monitoring',
    badge: '全域监控',
    highlights: ['秒级监控', '弹性采集','精准告警'],
    description: (
      <>
        提供全域监控能力，支持秒级监控、弹性采集与精准告警，保障多环境系统的稳定运行
      </>
    ),
  },  
  {
    title: '日志中心',
    icon: <FaSearch color="var(--ifm-color-primary)" />,
    gradient: 'gradient-log',
    badge: '日志分析',
    highlights: ['故障定位', '合规留存','日志洞察'],
    description: (
      <>
        集中日志平台，支持合规留存、故障定位与日志洞察，提升运维效率与系统可靠性
      </>
    ),
  },  
  {
    title: '节点管理',
    icon: <FaCloud color="var(--ifm-color-primary)" />,
    gradient: 'gradient-10',
    badge: '探针管理',
    highlights: ['跨云节点', '进程托管','探针分发'],
    description: (
      <>
        支持跨云节点、进程托管与探针分发，构建统一的探针管理体系，简化大规模集群的运维管理
      </>
    ),
  },  
  {
    title: '告警中心',
    icon: <FaBell color="var(--ifm-color-primary)" />,
    gradient: 'gradient-6',
    badge: '智能告警',
    highlights: ['多源接入', '灵活分派','智能分析'],
    description: (
      <>
        统一汇聚多源事件，结合智能分析与灵活分派，构建高效可控的告警处理体系
      </>
    ),
  },  
  {
    title: 'ITSM',
    icon: <RiFlowChart color="var(--ifm-color-primary)" />,
    gradient: 'gradient-2',
    badge: '服务流程',
    highlights: ['工单管理', '变更审批', '事件流程'],
    description: (
      <>
        提供工单、变更与事件的流程治理能力，助力运维高效执行与合规管理
      </>
    ),
  },  
  {
    title: '运营分析',
    icon: <FaChartLine color="var(--ifm-color-primary)" />,
    gradient: 'gradient-9',
    badge: '数据洞察',
    highlights: ['联邦分析', '业务优化','合规报表'],
    description: (
      <>
        统一整合多源数据，支持联邦分析与合规报表，将运维洞察转化为业务优化与决策价值
      </>
    ),
  },
  {
    title: 'MLOps',
    icon: <HiOutlineChip color="var(--ifm-color-primary)" />,
    gradient: 'gradient-11',
    badge: '模型工厂',
    highlights: ['数据标注','模型训练','能力发布'],
    description: (
      <>
        面向运维场景，整合数据标注、模型训练与能力发布，打造统一的模型工厂，加速智能运维能力落地
      </>
    ),
  },
  {
    title: 'PlayGround',
    icon: <FaVial color="var(--ifm-color-primary)" />,
    gradient: 'gradient-12',
    badge: '算法体验',
    highlights: ['算法验证', '安全沙箱','效果验证'],
    description: (
      <>
        作为算法体验环境，支持验证与安全沙箱实验，确保模型在应用前的效果可控与可靠
      </>
    ),
  },
  {
    title: 'Lab',
    icon: <FaVial color="var(--ifm-color-primary)" />,
    gradient: 'gradient-13',
    badge: '算法实验',
    highlights: ['在线开发', '实验环境','算法设计'],
    description: (
      <>
        提供 VSCode、JupyterLab 等云端环境，支持算法设计与实验，加速 AI 能力的开发与验证
      </>
    ),
  },

];

function Feature({title, description, gradient, icon, badge, metric, highlights}) {
  return (
    <div className={styles.featureItem}>
      <div className={clsx(styles.featureCard, styles[gradient])}>
        <div className={styles.cardHeader}>
          <div className={styles.featureIcon}>
            <div className={styles.iconEmoji}>{icon}</div>
          </div>
          <div className={styles.cardBadge}>{badge}</div>
        </div>
        
        <div className={styles.featureContent}>
          <Heading as="h3" className={styles.featureTitle}>
            {title}
          </Heading>
          <p className={styles.featureDescription}>{description}</p>
          
          <div className={styles.metricHighlight}>
            <div className={styles.highlightTags}>
              {highlights.map((highlight, idx) => (
                <span key={idx} className={styles.highlightTag}>
                  {highlight}
                </span>
              ))}
            </div>
          </div>
        </div>
        
        <div className={clsx(styles.featureGlow, styles[gradient])}></div>
      </div>
    </div>
  );
}

export default function HomepageFeatures() {
  return (
    <section className={styles.features}>
      <div className="container">
        <div className={styles.sectionHeader}>
          <Heading as="h2" className={styles.sectionTitle}>
            产品模块
          </Heading>
          <p className={styles.sectionSubtitle}>
            灵活、可扩展的运维体系,为持续增长的业务提供可靠支撑
          </p>
        </div>
        <div className={styles.featuresGrid}>
          {FeatureList.map((props, idx) => (
            <Feature key={idx} {...props} />
          ))}
        </div>
      </div>
    </section>
  );
}
