-- 挂到现有 BK-Lite PostgreSQL 的 docker-entrypoint-initdb.d。
-- 库已存在时不重复创建。本文件只在数据目录首次初始化时执行。
SELECT 'CREATE DATABASE flowable'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'flowable')\gexec
