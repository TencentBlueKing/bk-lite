import React, { useState, useEffect, useRef } from 'react';
import Link from '@docusaurus/Link';
import styles from './styles.module.css';

const productGroups = [
    {
        title: '经典运维',
        products: [
            { name: '监控平台', description: '指标采集 · 实时监控 · 智能告警', link: '/docs/monitor/feature' },
            { name: '日志平台', description: '日志聚合 · 全文检索 · 智能分析', link: '/docs/log/feature' },
            { name: 'CMDB', description: '资产管理 · 拓扑发现 · 配置追踪', link: '/docs/cmdb' },
            { name: '告警中心', description: '事件聚合 · 降噪收敛 · 智能分派', link: '/docs/alert' },
            { name: 'ITSM', description: '工单流转 · 变更管理 · 流程编排', link: '/docs/itsm/feature' },
            { name: '数据分析', description: '多维分析 · 数据可视化 · 运营报表', link: '/docs/analysis' },
        ]
    },
    {
        title: '平台底座',
        products: [
            { name: '控制台', description: '平台介绍 · 应用导航 · 快速入门', link: '/docs/console' },
            { name: '系统管理', description: '租户管理 · 权限控制 · 审计日志', link: '/docs/system/feature' },
            { name: '节点管理', description: 'Agent 部署 · 插件管理 · 进程托管', link: '/docs/node/feature' },
        ]
    },
    {
        title: '智能运维',
        products: [
            { name: 'OpsPilot', description: '智能问答 · 知识图谱 · 自动诊断', link: '/docs/opspilot/introduce' },
            { name: 'MLOps', description: '数据标注 · 模型训练 · 服务发布', link: '/docs/mlops/feature' },
            { name: 'AI Lab', description: 'Notebook · 算法开发 · 环境管理', link: '/docs/lab' },
            { name: 'Playground', description: '模型测试 · 效果验证 · 沙箱隔离', link: '/docs/playground' },
        ]
    },
];

export default function MegaMenu() {
    const [isOpen, setIsOpen] = useState(false);
    const [dropdownStyle, setDropdownStyle] = useState({});
    const menuRef = useRef(null);
    const buttonRef = useRef(null);

    useEffect(() => {
        function handleClickOutside(event) {
            if (
                menuRef.current &&
                !menuRef.current.contains(event.target) &&
                buttonRef.current &&
                !buttonRef.current.contains(event.target)
            ) {
                setIsOpen(false);
            }
        }

        if (isOpen) {
            document.addEventListener('mousedown', handleClickOutside);

            // 计算下拉菜单位置
            if (buttonRef.current) {
                const rect = buttonRef.current.getBoundingClientRect();
                setDropdownStyle({
                    top: `${rect.bottom + 8}px`,
                    left: `${rect.left - 200}px`,
                });
            }
        }

        return () => {
            document.removeEventListener('mousedown', handleClickOutside);
        };
    }, [isOpen]);

    return (
        <div className={styles.megaMenuWrapper}>
            <button
                ref={buttonRef}
                className={`${styles.megaMenuTrigger} ${isOpen ? styles.active : ''}`}
                onClick={() => setIsOpen(!isOpen)}
                onMouseEnter={() => setIsOpen(true)}
            >
                产品文档
                <svg
                    className={`${styles.megaMenuArrow} ${isOpen ? styles.open : ''}`}
                    width="10"
                    height="10"
                    viewBox="0 0 12 12"
                    fill="currentColor"
                >
                    <path d="M6 8L2 4h8z" />
                </svg>
            </button>

            {isOpen && (
                <div
                    ref={menuRef}
                    className={styles.megaMenuDropdown}
                    style={dropdownStyle}
                    onMouseLeave={() => setIsOpen(false)}
                >
                    <div className={styles.megaMenuContainer}>
                        <div className={styles.megaMenuGroups}>
                            {productGroups.map((group, groupIdx) => (
                                <div key={groupIdx} className={styles.productGroup}>
                                    <div className={styles.groupTitle}>{group.title}</div>
                                    <div className={styles.groupProducts}>
                                        {group.products.map((product, idx) => (
                                            <Link
                                                key={idx}
                                                to={product.link}
                                                className={styles.megaMenuItem}
                                                onClick={() => setIsOpen(false)}
                                            >
                                                <div className={styles.itemName}>{product.name}</div>
                                                <div className={styles.itemDescription}>{product.description}</div>
                                            </Link>
                                        ))}
                                    </div>
                                </div>
                            ))}
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}
