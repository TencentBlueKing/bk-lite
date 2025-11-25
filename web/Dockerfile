FROM node:18-alpine AS builder

ARG NEXUS_NODEJS_REPOSITY

WORKDIR /app

# 设置Node.js最大堆内存为4GB
ENV NODE_OPTIONS="--max-old-space-size=8192"

# 如果提供了 NEXUS_NODEJS_REPOSITY，则切换 npm 源
RUN if [ -n "$NEXUS_NODEJS_REPOSITY" ]; then \
  echo "Setting npm registry to: $NEXUS_NODEJS_REPOSITY"; \
  npm config set registry "$NEXUS_NODEJS_REPOSITY"; \
  else \
  echo "Using default npm registry"; \
  fi

RUN npm install -g pnpm

# 如果提供了 NEXUS_NODEJS_REPOSITY，则切换 pnpm 源
RUN if [ -n "$NEXUS_NODEJS_REPOSITY" ]; then \
  echo "Setting pnpm registry to: $NEXUS_NODEJS_REPOSITY"; \
  pnpm config set registry "$NEXUS_NODEJS_REPOSITY"; \
  else \
  echo "Using default pnpm registry"; \
  fi

ADD . .

RUN cat > pnpm-workspace.yaml <<'EOF'
packages:
  - 'src/app/*'
EOF

RUN cat > .env.local <<'EOF'
NEXTAPI_URL="http://bklite-server:8000"
EOF

RUN pnpm install
RUN pnpm run build

FROM node:18-alpine
RUN npm install -g pnpm

# 在生产环境也设置内存限制
ENV NODE_OPTIONS="--max-old-space-size=2048"

WORKDIR /app
COPY --from=builder /app/.next ./.next
COPY --from=builder /app/public ./public
COPY --from=builder /app/node_modules ./node_modules
COPY --from=builder /app/package.json ./

CMD ["pnpm", "run", "start"]