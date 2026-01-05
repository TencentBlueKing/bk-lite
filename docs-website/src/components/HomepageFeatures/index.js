import clsx from 'clsx';
import Heading from '@theme/Heading';
import styles from './styles.module.css';
import { FaUserShield, FaVial, FaSearch, FaChartBar, FaBell, FaLaptopCode, FaCloud, FaChartLine } from 'react-icons/fa';
import { RiMindMap, RiFlowChart } from 'react-icons/ri';
import { HiOutlineDatabase, HiOutlineChip } from 'react-icons/hi';

const FeatureGroups = [
  {
    groupTitle: '经典运维',
    groupSubtitle: '成熟稳定的运维能力体系',
    features: [
      {
        title: '监控中心',
        icon: <FaChartBar color="var(--ifm-color-primary)" />,
        gradient: 'gradient-monitoring',
        badge: '全域监控',
        highlights: ['秒级监控', '弹性采集', '精准告警'],
        description: (
          <>
            全域监控体系，秒级采集与精准告警，保障系统稳定运行
          </>
        ),
      },
      {
        title: '日志中心',
        icon: <FaSearch color="var(--ifm-color-primary)" />,
        gradient: 'gradient-log',
        badge: '日志分析',
        highlights: ['故障定位', '合规留存', '日志洞察'],
        description: (
          <>
            支持日志的合规留存与快速检索，为故障排查与审计追溯提供可靠依据
          </>
        ),
      },
      {
        title: 'CMDB',
        icon: <HiOutlineDatabase color="var(--ifm-color-primary)" />,
        gradient: 'gradient-3',
        badge: '资产地图',
        highlights: ['资产可视', '架构清晰', '数据可信'],
        description: (
          <>
            构建可信的IT资产地图。全面采集与架构还原，为运维决策与合规管理提供数据基础
          </>
        ),
      },
      {
        title: '告警中心',
        icon: <FaBell color="var(--ifm-color-primary)" />,
        gradient: 'gradient-6',
        badge: '告警响应',
        highlights: ['降低干扰', '精准分派', '快速闭环'],
        description: (
          <>
            汇聚多源告警并智能降噪，通过精准分派加速响应，确保问题快速闭环
          </>
        ),
      },
      {
        title: 'ITSM',
        icon: <RiFlowChart color="var(--ifm-color-primary)" />,
        gradient: 'gradient-2',
        badge: '流程规范',
        highlights: ['标准执行', '透明可控', '合规保障'],
        description: (
          <>
            规范工单、变更与事件流程，确保运维执行标准化、过程可追溯、合规有保障
          </>
        ),
      },
      {
        title: '运营分析',
        icon: <FaChartLine color="var(--ifm-color-primary)" />,
        gradient: 'gradient-9',
        badge: '洞察分析',
        highlights: ['数据融合', '智能分析', '价值呈现'],
        description: (
          <>
            融合多源运维数据，通过智能分析将运维洞察转化为业务价值与决策依据
          </>
        ),
      },
    ]
  },
  {
    groupTitle: '平台底座',
    groupSubtitle: '统一的基础支撑能力',
    features: [
      {
        title: '控制台',
        icon: <FaLaptopCode color="var(--ifm-color-primary)" />,
        gradient: 'gradient-7',
        badge: '工作门户',
        highlights: ['一站访问', '通知聚合', '智能推荐'],
        description: (
          <>
            统一工作门户。汇聚多源通知，提供智能入口与个性化配置，提升团队协作效率
          </>
        ),
      },
      {
        title: '系统管理',
        icon: <FaUserShield color="var(--ifm-color-primary)" />,
        gradient: 'gradient-8',
        badge: '安全合规',
        highlights: ['权限隔离', '精细管控', '全程追溯'],
        description: (
          <>
            多租户权限管理与审计追踪，确保系统访问安全可控、操作全程可追溯
          </>
        ),
      },
      {
        title: '节点管理',
        icon: <FaCloud color="var(--ifm-color-primary)" />,
        gradient: 'gradient-10',
        badge: '节点治理',
        highlights: ['跨云管理', '自动部署', '状态可视'],
        description: (
          <>
            跨云节点的统一管理。支持探针自动部署与进程托管，简化大规模集群运维
          </>
        ),
      },
    ]
  },
  {
    groupTitle: '智能运维',
    groupSubtitle: 'AI驱动的运维创新',
    features: [
      {
        title: 'OpsPilot',
        icon: <RiMindMap color="var(--ifm-color-primary)" />,
        gradient: 'gradient-opspilot',
        badge: '运维领航员',
        highlights: ['自主诊断', '智能决策', '自动修复'],
        description: (
          <>
            基于大模型与知识图谱，引导团队快速定位问题、智能决策并高效修复
          </>
        ),
      },
      {
        title: 'MLOps',
        icon: <HiOutlineChip color="var(--ifm-color-primary)" />,
        gradient: 'gradient-11',
        badge: '模型工厂',
        highlights: ['数据标注', '模型训练', '能力发布'],
        description: (
          <>
            面向运维场景，整合数据标注、模型训练与能力发布，打造统一的模型工厂，加速智能运维能力落地
          </>
        ),
      },
    ]
  },
];

function Feature({ title, description, gradient, icon, badge, metric, highlights }) {
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
      {/* AI风格装饰元素 */}
      <div className={styles.aiOrb1}></div>
      <div className={styles.aiOrb2}></div>
      <div className={styles.aiOrb3}></div>
      <div className={styles.gridPattern}></div>

      <div className="container">
        <div className={styles.sectionHeader}>
          <Heading as="h2" className={styles.sectionTitle}>
            产品模块
          </Heading>
        </div>

        {FeatureGroups.map((group, groupIdx) => {
          const gridClass = group.features.length === 2
            ? styles.featuresGrid2
            : group.features.length === 3
              ? styles.featuresGrid3
              : styles.featuresGrid;

          return (
            <div key={groupIdx} className={styles.featureGroup}>
              <div className={styles.groupHeader}>
                <h3 className={styles.groupTitle}>{group.groupTitle}</h3>
                <p className={styles.groupSubtitle}>{group.groupSubtitle}</p>
              </div>
              <div className={gridClass}>
                {group.features.map((props, idx) => (
                  <Feature key={idx} {...props} />
                ))}
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
}
