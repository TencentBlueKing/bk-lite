import React, { useState, useEffect, useRef } from 'react';
import Link from '@docusaurus/Link';
import styles from './styles.module.css';

const productGroups = [
    {
        title: '经典运维',
        products: [
            { name: '监控中心', description: '秒级监控 · 精准告警 · 稳定保障', link: '/docs/monitor/feature' },
            { name: '日志中心', description: '快速检索 · 故障定位 · 合规留存', link: '/docs/log/feature' },
            { name: 'CMDB', description: '资产可视 · 架构清晰 · 数据可信', link: '/docs/cmdb' },
            { name: '告警中心', description: '智能降噪 · 精准分派 · 快速闭环', link: '/docs/alert' },
            { name: 'ITSM', description: '标准执行 · 透明可控 · 合规保障', link: '/docs/itsm/feature' },
            { name: '运营分析', description: '数据融合 · 智能分析 · 价值呈现', link: '/docs/analysis' },
        ]
    },
    {
        title: '平台底座',
        products: [
            { name: '控制台', description: '一站访问 · 通知聚合 · 智能推荐', link: '/docs/console' },
            { name: '系统管理', description: '权限隔离 · 精细管控 · 全程追溯', link: '/docs/system/feature' },
            { name: '节点管理', description: '跨云管理 · 自动部署 · 状态可视', link: '/docs/node/feature' },
        ]
    },
    {
        title: '智能运维',
        products: [
            { name: 'OpsPilot', description: '自主诊断 · 智能决策 · 自动修复', link: '/docs/opspilot/introduce' },
            { name: 'MLOps', description: '数据标注 · 模型训练 · 能力发布', link: '/docs/mlops/feature' },
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
