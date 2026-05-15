(function () {
    const navItems = [
        { key: 'workspace', label: '工作台', href: '../工作台/工作台.html', icon: 'workspace' },
        { key: 'agent', label: '智能体', href: '../智能体/智能体.html', icon: 'agent' },
        { key: 'memory', label: '记忆', href: '../记忆/记忆.html', icon: 'memory' },
        { key: 'knowledge', label: '知识库', href: '../知识库/知识库.html', icon: 'knowledge' },
        { key: 'tool', label: '工具', href: '../工具/工具.html', icon: 'tool' },
        { key: 'model', label: '模型', href: '../模型/模型.html', icon: 'model' }
    ];

    const launcherItems = [
        { key: 'workspace', label: 'OpsPilot', short: 'OP', href: '../工作台/工作台.html' },
        { key: 'opsconsole', label: 'OpsConsole', short: 'OC', message: 'OpsConsole 为原型占位。' },
        { key: 'setting', label: 'Setting', short: 'ST', message: 'Setting 为原型占位。' },
        { key: 'cmdb', label: 'CMDB', short: 'CM', message: 'CMDB 为原型占位。' },
        { key: 'monitor', label: 'Monitor', short: 'MO', message: 'Monitor 为原型占位。' },
        { key: 'log', label: 'Log', short: 'LG', message: 'Log 为原型占位。' },
        { key: 'node', label: 'Node', short: 'ND', message: 'Node 为原型占位。' },
        { key: 'alarm', label: 'Alarm', short: 'AL', message: 'Alarm 为原型占位。' },
        { key: 'itsm', label: 'ITSM', short: 'IT', message: 'ITSM 为原型占位。' },
        { key: 'opsanalysis', label: 'OpsAnalysis', short: 'OA', message: 'OpsAnalysis 为原型占位。' },
        { key: 'mlops', label: 'MLOps', short: 'ML', message: 'MLOps 为原型占位。' },
        { key: 'lab', label: 'Lab', short: 'LB', message: 'Lab 为原型占位。' }
    ];

    const headerStyle = `
        html,
        body {
            height: 100%;
        }

        body {
            overflow: hidden;
        }

        body .app-shell {
            height: 100vh;
            min-height: 100vh;
            overflow: hidden;
        }

        body .opspilot-unified-header {
            position: sticky;
            top: 0;
            z-index: 120;
            flex: 0 0 56px;
            height: 56px;
            padding: 0 16px;
            display: flex;
            align-items: center;
            justify-content: space-between;
            border-bottom: 1px solid #d9e2ee;
            background: #edf3fb;
        }

        body .opspilot-unified-header .oph-left,
        body .opspilot-unified-header .oph-actions {
            position: relative;
            z-index: 1;
            flex: 0 0 238px;
            min-width: 0;
            display: flex;
            align-items: center;
        }

        body .opspilot-unified-header .oph-left {
            gap: 8px;
        }

        body .opspilot-unified-header .oph-brand {
            display: inline-flex;
            align-items: center;
            gap: 8px;
            color: #475468;
            min-width: 0;
        }

        body .opspilot-unified-header .oph-brand img {
            width: auto;
            height: 24px;
            display: block;
            flex-shrink: 0;
        }

        body .opspilot-unified-header .oph-brand strong {
            color: #475468;
            font-size: 14px;
            font-weight: 500;
            white-space: nowrap;
        }

        body .opspilot-unified-header .oph-launcher {
            position: relative;
            flex-shrink: 0;
            margin-left: 4px;
        }

        body .opspilot-unified-header .oph-launcher-trigger,
        body .opspilot-unified-header .oph-icon-action,
        body .opspilot-unified-header .oph-user-trigger,
        body .opspilot-unified-header .oph-user-item,
        body .opspilot-unified-header .oph-launcher-item {
            border: none;
            outline: none;
            appearance: none;
            -webkit-appearance: none;
            box-shadow: none;
            font: inherit;
        }

        body .opspilot-unified-header .oph-launcher-trigger {
            height: 36px;
            padding: 0 12px;
            border-radius: 10px;
            background: rgba(16, 24, 40, 0.04);
            color: #7588A3;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            gap: 5px;
            cursor: pointer;
            transition: background 0.2s ease, color 0.2s ease;
        }

        body .opspilot-unified-header .oph-launcher-trigger:hover,
        body .opspilot-unified-header .oph-launcher-trigger.open {
            background: #fcfcfd;
            color: #155AEF;
        }

        body .opspilot-unified-header .oph-launcher-grid-icon {
            width: 14px;
            height: 14px;
            display: grid;
            grid-template-columns: repeat(2, 1fr);
            gap: 2px;
        }

        body .opspilot-unified-header .oph-launcher-grid-icon span {
            width: 6px;
            height: 6px;
            border-radius: 2px;
            background: currentColor;
            opacity: 0.95;
        }

        body .opspilot-unified-header .oph-nav {
            position: absolute;
            left: 50%;
            top: 50%;
            transform: translate(-50%, -50%);
            display: flex;
            align-items: center;
            gap: 4px;
            white-space: nowrap;
        }

        body .opspilot-unified-header .oph-nav a {
            height: 36px;
            padding: 0 12px;
            border-radius: 10px;
            display: inline-flex;
            align-items: center;
            gap: 8px;
            color: #475468;
            font-size: 14px;
            font-weight: 500;
            line-height: 1;
            transition: background 0.2s ease, color 0.2s ease, box-shadow 0.2s ease;
        }

        body .opspilot-unified-header .oph-nav a:hover {
            background: rgba(16, 24, 40, 0.04);
        }

        body .opspilot-unified-header .oph-nav a.active {
            color: #155AEF;
            background: #fcfcfd;
            box-shadow: 0 1px 2px rgba(16, 24, 40, 0.04);
        }

        body .opspilot-unified-header .oph-nav-icon {
            width: 15px;
            height: 15px;
            flex-shrink: 0;
            display: block;
        }

        body .opspilot-unified-header .oph-nav-icon svg {
            width: 100%;
            height: 100%;
            display: block;
            stroke: currentColor;
            fill: none;
            stroke-width: 1.5;
            stroke-linecap: round;
            stroke-linejoin: round;
        }

        body .opspilot-unified-header .oph-caret {
            width: 13px;
            height: 13px;
            flex-shrink: 0;
            display: block;
            color: #98A2B3;
        }

        body .opspilot-unified-header .oph-caret svg {
            width: 100%;
            height: 100%;
            display: block;
            stroke: currentColor;
            fill: none;
            stroke-width: 1.45;
            stroke-linecap: round;
            stroke-linejoin: round;
        }

        body .opspilot-unified-header .oph-actions {
            justify-content: flex-end;
            gap: 16px;
            color: #7588A3;
        }

        body .opspilot-unified-header .oph-icon-action {
            padding: 0;
            background: transparent;
            color: inherit;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            width: 30px;
            height: 30px;
            cursor: pointer;
            transition: color 0.2s ease, background 0.2s ease;
            border-radius: 6px;
        }

        body .opspilot-unified-header .oph-icon-action svg {
            width: 18px;
            height: 18px;
            display: block;
            stroke: currentColor;
            fill: none;
            stroke-width: 1.65;
            stroke-linecap: round;
            stroke-linejoin: round;
        }

        body .opspilot-unified-header .oph-icon-action:hover,
        body .opspilot-unified-header .oph-user-trigger:hover,
        body .opspilot-unified-header .oph-user-trigger.open {
            color: #155AEF;
        }

        body .opspilot-unified-header .oph-icon-action:hover {
            background: rgba(16, 24, 40, 0.04);
        }

        body .opspilot-unified-header .oph-user-menu {
            position: relative;
        }

        body .opspilot-unified-header .oph-user-trigger {
            padding: 0;
            background: transparent;
            display: inline-flex;
            align-items: center;
            gap: 6px;
            color: #475468;
            font-size: 14px;
            font-weight: 500;
            cursor: pointer;
            transition: color 0.2s ease;
        }

        body .opspilot-unified-header .oph-avatar {
            width: 26px;
            height: 26px;
            border-radius: 50%;
            background: #155AEF;
            color: #ffffff;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            font-size: 12px;
            font-weight: 700;
            flex-shrink: 0;
        }

        body .opspilot-unified-header .oph-user-name {
            white-space: nowrap;
            line-height: 1;
        }

        body .opspilot-unified-header .oph-user-trigger .oph-caret {
            width: 12px;
            height: 12px;
        }

        body .opspilot-unified-header .oph-launcher-panel,
        body .opspilot-unified-header .oph-user-panel {
            position: absolute;
            top: calc(100% + 10px);
            border: 1px solid #E6E9EE;
            border-radius: 8px;
            background: #ffffff;
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
            opacity: 0;
            visibility: hidden;
            pointer-events: none;
            transform: translateY(4px);
            transition: opacity 0.2s ease, transform 0.2s ease, visibility 0.2s ease;
        }

        body .opspilot-unified-header .oph-launcher-panel.open,
        body .opspilot-unified-header .oph-user-panel.open {
            opacity: 1;
            visibility: visible;
            pointer-events: auto;
            transform: translateY(0);
        }

        body .opspilot-unified-header .oph-launcher-panel {
            left: 0;
            width: 424px;
            padding: 12px;
        }

        body .opspilot-unified-header .oph-panel-title {
            margin-bottom: 10px;
            color: #1E252E;
            font-size: 14px;
            font-weight: 600;
        }

        body .opspilot-unified-header .oph-launcher-grid {
            display: grid;
            grid-template-columns: repeat(4, minmax(0, 1fr));
            gap: 10px;
        }

        body .opspilot-unified-header .oph-launcher-item {
            min-height: 72px;
            padding: 10px 8px;
            border-radius: 6px;
            background: #F6F8F9;
            color: #7588A3;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            gap: 8px;
            font-size: 12px;
            line-height: 1.2;
            text-align: center;
            cursor: pointer;
            transition: background 0.2s ease, color 0.2s ease;
        }

        body .opspilot-unified-header .oph-launcher-item:hover,
        body .opspilot-unified-header .oph-launcher-item.current {
            background: #eef4ff;
            color: #155AEF;
        }

        body .opspilot-unified-header .oph-launcher-item-badge {
            width: 30px;
            height: 30px;
            border-radius: 10px;
            background: #ffffff;
            color: #155AEF;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            font-size: 11px;
            font-weight: 700;
        }

        body .opspilot-unified-header .oph-user-panel {
            right: 0;
            width: 188px;
            padding: 8px;
        }

        body .opspilot-unified-header .oph-user-item,
        body .opspilot-unified-header .oph-user-meta {
            width: 100%;
            min-height: 36px;
            padding: 0 12px;
            border-radius: 6px;
            display: flex;
            align-items: center;
            color: #475468;
            font-size: 13px;
            font-weight: 500;
        }

        body .opspilot-unified-header .oph-user-item {
            background: transparent;
            justify-content: flex-start;
            cursor: pointer;
            transition: background 0.2s ease, color 0.2s ease;
        }

        body .opspilot-unified-header .oph-user-item:hover {
            background: #F6F8F9;
            color: #155AEF;
        }

        body .opspilot-unified-header .oph-user-meta {
            color: #7588A3;
        }

        body .app-shell > .workspace,
        body .app-shell > main.workspace,
        body .app-shell > .main,
        body .app-shell > main.main {
            flex: 1 1 auto;
            min-height: 0 !important;
            height: auto !important;
            overflow-y: auto !important;
            scrollbar-gutter: stable;
        }

        @media (max-width: 1560px) {
            body .opspilot-unified-header .oph-left,
            body .opspilot-unified-header .oph-actions {
                flex-basis: 220px;
            }
        }
    `;

    function appendStyle() {
        if (document.getElementById('opspilot-unified-header-style')) {
            return;
        }

        const style = document.createElement('style');
        style.id = 'opspilot-unified-header-style';
        style.textContent = headerStyle;
        document.head.appendChild(style);
    }

    function getIcon(name) {
        const icons = {
            workspace: '<svg viewBox="0 0 16 16" aria-hidden="true"><rect x="2.5" y="2.5" width="4.5" height="4.5" rx="1"></rect><rect x="9" y="2.5" width="4.5" height="4.5" rx="1"></rect><rect x="2.5" y="9" width="4.5" height="4.5" rx="1"></rect><rect x="9" y="9" width="4.5" height="4.5" rx="1"></rect></svg>',
            memory: '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M3 3.25h6.1L12.75 6.9V12A1.25 1.25 0 0 1 11.5 13.25H4.25A1.25 1.25 0 0 1 3 12z"></path><path d="M9.1 3.25V6.9h3.65"></path><path d="M5.3 8.1h4.8"></path><path d="M5.3 10.1h3.8"></path></svg>',
            agent: '<svg viewBox="0 0 16 16" aria-hidden="true"><rect x="3" y="4" width="10" height="8" rx="2"></rect><path d="M8 1.75v1.5"></path><path d="M5.6 7.7h0.01"></path><path d="M10.4 7.7h0.01"></path><path d="M6 10.4h4"></path></svg>',
            knowledge: '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M4.25 3.25h6a1.5 1.5 0 0 1 1.5 1.5v7.5h-6a1.5 1.5 0 0 0-1.5 1.5z"></path><path d="M4.25 3.25v9"></path></svg>',
            tool: '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M9.8 2.3a3 3 0 0 0 1.35 4.2L6.7 10.95a1.5 1.5 0 1 0 2.12 2.12l4.45-4.45A3 3 0 1 0 9.8 2.3z"></path></svg>',
            model: '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M2.5 5.2L8 2.5l5.5 2.7L8 8 2.5 5.2z"></path><path d="M2.5 8.1L8 10.8l5.5-2.7"></path><path d="M2.5 10.9L8 13.5l5.5-2.6"></path></svg>',
            bell: '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M6.65 12.1a1.35 1.35 0 0 0 2.7 0"></path><path d="M5.25 6.4a2.75 2.75 0 1 1 5.5 0c0 1.06.18 1.96.63 2.83l.18.35H4.44l.18-.35c.45-.87.63-1.77.63-2.83z"></path></svg>',
            doc: '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M5 2.75h4.1L11.5 5.1v6.9a1.1 1.1 0 0 1-1.1 1.1H5A1.1 1.1 0 0 1 3.9 12V3.85A1.1 1.1 0 0 1 5 2.75z"></path><path d="M9.1 2.75V5.1h2.4"></path><path d="M5.85 7.35h4.2"></path><path d="M5.85 9.45h3.4"></path></svg>',
            caret: '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M4.5 6.5L8 10l3.5-3.5"></path></svg>'
        };

        return icons[name] || icons.workspace;
    }

    function getActiveKey() {
        const pathname = decodeURIComponent(window.location.pathname);

        if (pathname.includes('/记忆/')) {
            return 'memory';
        }

        if (pathname.includes('/智能体/')) {
            return 'agent';
        }

        if (pathname.includes('/知识库/')) {
            return 'knowledge';
        }

        if (pathname.includes('/工具/')) {
            return 'tool';
        }

        if (pathname.includes('/模型/')) {
            return 'model';
        }

        return 'workspace';
    }

    function renderNav(activeKey) {
        return navItems.map((item) => {
            const activeClass = item.key === activeKey ? 'active' : '';
            const currentAttr = item.key === activeKey ? ' aria-current="page"' : '';

            return `
                <a class="${activeClass}" href="${item.href}"${currentAttr}>
                    <span class="oph-nav-icon">${getIcon(item.icon)}</span>
                    <span>${item.label}</span>
                </a>
            `;
        }).join('');
    }

    function renderLauncher(activeKey) {
        return launcherItems.map((item) => {
            const currentClass = item.key === activeKey ? ' current' : '';

            if (item.href) {
                return `
                    <a class="oph-launcher-item${currentClass}" href="${item.href}">
                        <span class="oph-launcher-item-badge">${item.short}</span>
                        <span>${item.label}</span>
                    </a>
                `;
            }

            return `
                <button class="oph-launcher-item${currentClass}" type="button" data-header-message="${item.message}">
                    <span class="oph-launcher-item-badge">${item.short}</span>
                    <span>${item.label}</span>
                </button>
            `;
        }).join('');
    }

    function buildHeader(activeKey) {
        return `
            <header class="opspilot-unified-header">
                <div class="oph-left">
                    <a class="oph-brand" href="../工作台/工作台.html" aria-label="BlueKing Lite">
                        <img src="../../../../web/public/logo-site.png" alt="BlueKing Lite">
                        <strong>BlueKing Lite</strong>
                    </a>
                    <div class="oph-launcher" id="appLauncher">
                        <button class="oph-launcher-trigger" id="appLauncherTrigger" type="button" aria-label="应用切换" aria-expanded="false">
                            <span class="oph-launcher-grid-icon" aria-hidden="true"><span></span><span></span><span></span><span></span></span>
                            <span class="oph-caret" aria-hidden="true">${getIcon('caret')}</span>
                        </button>
                        <div class="oph-launcher-panel" id="appLauncherPanel" role="menu" aria-label="应用列表">
                            <div class="oph-panel-title">应用列表</div>
                            <div class="oph-launcher-grid">
                                ${renderLauncher(activeKey)}
                            </div>
                        </div>
                    </div>
                </div>
                <nav class="oph-nav" aria-label="顶部导航">
                    ${renderNav(activeKey)}
                </nav>
                <div class="oph-actions">
                    <button class="oph-icon-action" type="button" aria-label="通知" data-header-message="通知中心为原型占位。">
                        ${getIcon('bell')}
                    </button>
                    <button class="oph-icon-action" type="button" aria-label="使用文档" data-header-message="使用文档为原型占位。">
                        ${getIcon('doc')}
                    </button>
                    <div class="oph-user-menu" id="userMenu">
                        <button class="oph-user-trigger" id="userMenuTrigger" type="button" aria-label="用户菜单" aria-expanded="false">
                            <span class="oph-avatar">陈</span>
                            <span class="oph-user-name">陈润桦</span>
                            <span class="oph-caret" aria-hidden="true">${getIcon('caret')}</span>
                        </button>
                        <div class="oph-user-panel" id="userMenuPanel" role="menu" aria-label="用户菜单">
                            <div class="oph-user-meta">默认组</div>
                            <button class="oph-user-item" type="button" data-header-message="个人设置为原型占位。">个人设置</button>
                            <button class="oph-user-item" type="button" data-header-message="版本信息为原型占位。">版本信息</button>
                            <button class="oph-user-item" type="button" data-header-message="退出登录为原型占位。">退出登录</button>
                        </div>
                    </div>
                </div>
            </header>
        `;
    }

    function notify(message) {
        if (!message) {
            return;
        }

        if (typeof window.showToast === 'function') {
            window.showToast(message);
            return;
        }

        if (typeof window.showTopNotice === 'function') {
            window.showTopNotice(message, 'success');
            return;
        }

        if (typeof window.alert === 'function') {
            window.alert(message);
        }
    }

    function bindHeaderEvents() {
        const appLauncherTrigger = document.getElementById('appLauncherTrigger');
        const appLauncherPanel = document.getElementById('appLauncherPanel');
        const userMenuTrigger = document.getElementById('userMenuTrigger');
        const userMenuPanel = document.getElementById('userMenuPanel');

        if (!appLauncherTrigger || !appLauncherPanel || !userMenuTrigger || !userMenuPanel) {
            return;
        }

        const setPanelState = (trigger, panel, visible) => {
            trigger.classList.toggle('open', visible);
            trigger.setAttribute('aria-expanded', String(visible));
            panel.classList.toggle('open', visible);
        };

        const closeAllPanels = () => {
            setPanelState(appLauncherTrigger, appLauncherPanel, false);
            setPanelState(userMenuTrigger, userMenuPanel, false);
        };

        appLauncherTrigger.addEventListener('click', (event) => {
            event.preventDefault();
            event.stopPropagation();
            const willOpen = !appLauncherPanel.classList.contains('open');
            setPanelState(userMenuTrigger, userMenuPanel, false);
            setPanelState(appLauncherTrigger, appLauncherPanel, willOpen);
        });

        userMenuTrigger.addEventListener('click', (event) => {
            event.preventDefault();
            event.stopPropagation();
            const willOpen = !userMenuPanel.classList.contains('open');
            setPanelState(appLauncherTrigger, appLauncherPanel, false);
            setPanelState(userMenuTrigger, userMenuPanel, willOpen);
        });

        appLauncherPanel.addEventListener('click', (event) => {
            const action = event.target.closest('[data-header-message]');
            if (action) {
                event.preventDefault();
                notify(action.getAttribute('data-header-message'));
            }
            event.stopPropagation();
        });

        userMenuPanel.addEventListener('click', (event) => {
            const action = event.target.closest('[data-header-message]');
            if (action) {
                event.preventDefault();
                closeAllPanels();
                notify(action.getAttribute('data-header-message'));
            }
            event.stopPropagation();
        });

        document.querySelectorAll('[data-header-message]').forEach((element) => {
            if (element.closest('#appLauncherPanel') || element.closest('#userMenuPanel')) {
                return;
            }

            element.addEventListener('click', (event) => {
                event.preventDefault();
                event.stopPropagation();
                notify(element.getAttribute('data-header-message'));
            });
        });

        document.addEventListener('click', (event) => {
            if (event.target.closest('#appLauncher') || event.target.closest('#userMenu')) {
                return;
            }

            closeAllPanels();
        });

        window.addEventListener('keydown', (event) => {
            if (event.key === 'Escape') {
                closeAllPanels();
            }
        });
    }

    function replaceHeader() {
        const header = document.querySelector('.app-shell > .top-header');
        if (!header) {
            return;
        }

        header.outerHTML = buildHeader(getActiveKey());
        bindHeaderEvents();
    }

    appendStyle();

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', replaceHeader);
    } else {
        replaceHeader();
    }
})();