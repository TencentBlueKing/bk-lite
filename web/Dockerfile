FROM node:24-alpine AS builder

ARG NEXUS_NODEJS_REPOSITY

WORKDIR /app

# 设置Node.js最大堆内存为4GB
ENV NODE_OPTIONS="--max-old-space-size=8192"
ENV PNPM_HOME="/pnpm"

# 跳过 electron 二进制下载（react-devtools 的传递依赖，构建期不需要）
ENV ELECTRON_SKIP_BINARY_DOWNLOAD=1

# 如果提供了 NEXUS_NODEJS_REPOSITY，则切换 npm 源
RUN if [ -n "$NEXUS_NODEJS_REPOSITY" ]; then \
  echo "Setting npm registry to: $NEXUS_NODEJS_REPOSITY"; \
  npm config set registry "$NEXUS_NODEJS_REPOSITY"; \
  else \
  echo "Using default npm registry"; \
  fi

RUN corepack enable && corepack prepare pnpm@11.20.0 --activate
RUN pnpm config set store-dir /pnpm/store

# 如果提供了 NEXUS_NODEJS_REPOSITY，则切换 pnpm 源
RUN if [ -n "$NEXUS_NODEJS_REPOSITY" ]; then \
  echo "Setting pnpm registry to: $NEXUS_NODEJS_REPOSITY"; \
  pnpm config set registry "$NEXUS_NODEJS_REPOSITY"; \
  else \
  echo "Using default pnpm registry"; \
  fi

ADD . .

RUN echo 'NEXTAPI_URL="http://bklite-server:8000"' > .env.local

RUN pnpm install --frozen-lockfile
RUN pnpm run build

FROM node:24-alpine
RUN corepack enable && corepack prepare pnpm@11.20.0 --activate

# 在生产环境也设置内存限制
ENV NODE_OPTIONS="--max-old-space-size=2048"

WORKDIR /app
COPY --from=builder /app/.next ./.next
COPY --from=builder /app/public ./public
COPY --from=builder /app/node_modules ./node_modules
COPY --from=builder /app/package.json ./

CMD ["pnpm", "run", "start"]
# 或者直接写明端口（如需更显式可改为：CMD ["pnpm", "exec", "next", "start", "-p", "3001"]）
