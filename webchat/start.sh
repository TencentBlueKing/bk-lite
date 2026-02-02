#!/bin/bash

# WebChat 快速启动脚本

echo "╔════════════════════════════════════════════════════════════════╗"
echo "║          WebChat 项目 - 快速启动脚本                           ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo ""
echo "请选择启动模式："
echo "  1) 开发模式 (dev) - 直接启动，无需构建"
echo "  2) 生产模式 (build) - 先构建再启动"
echo ""
read -p "请输入选项 (1 或 2, 默认为 1): " mode
mode=${mode:-1}

# 检查 Node.js
if ! command -v node &> /dev/null; then
    echo "❌ Node.js 未安装"
    exit 1
fi

echo "✅ Node.js 版本: $(node --version)"
echo "✅ npm 版本: $(npm --version)"
echo ""

if [ "$mode" = "1" ]; then
    echo "🚀 启动开发模式..."
    echo ""
    cd packages/webchat-demo
    npm run dev
    exit 0
fi

# 第一步：构建核心库
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "第一步：构建 WebChat Core 库..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
cd packages/webchat-core
npm run build
if [ $? -ne 0 ]; then
    echo "❌ Core 库构建失败"
    exit 1
fi
echo "✅ Core 库构建成功"
echo ""

# 第二步：进入演示应用目录
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "第二步：安装演示应用依赖..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
cd ../webchat-demo

# 检查是否已经安装
if [ ! -d "node_modules" ]; then
    echo "安装依赖中... (这可能需要几分钟)"
    npm install --no-save
    if [ $? -ne 0 ]; then
        echo "❌ 依赖安装失败"
        exit 1
    fi
fi
echo "✅ 依赖已准备好"
echo ""

# 第三步：启动开发服务器
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "第三步：启动开发服务器..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "🚀 Next.js 开发服务器启动中..."
echo "📍 访问: http://localhost:3000"
echo "🔌 聊天 API: http://localhost:3000/api/chat/stream"
echo ""
echo "按 Ctrl+C 停止服务器"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

npm run dev
