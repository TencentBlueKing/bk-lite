-- mssql 初始化 SQL（python 入口 init_script）
-- 创建测试数据库 + 几张表 + 几行数据
USE master;
GO

IF DB_ID('cmdb_test') IS NULL
BEGIN
    CREATE DATABASE cmdb_test;
END
GO

USE cmdb_test;
GO

IF OBJECT_ID('servers', 'U') IS NULL
BEGIN
    CREATE TABLE servers (
        id INT IDENTITY(1,1) PRIMARY KEY,
        hostname NVARCHAR(128) NOT NULL,
        ip NVARCHAR(64) NULL,
        role NVARCHAR(64) NULL,
        created_at DATETIME2 DEFAULT GETDATE()
    );
END
GO

IF OBJECT_ID('app_users', 'U') IS NULL
BEGIN
    CREATE TABLE app_users (
        id INT IDENTITY(1,1) PRIMARY KEY,
        username NVARCHAR(64) NOT NULL,
        email NVARCHAR(128) NULL
    );
END
GO

INSERT INTO servers (hostname, ip, role) VALUES
    (N'srv-web-01', N'10.0.0.11', N'web'),
    (N'srv-db-01', N'10.0.0.21', N'database'),
    (N'srv-cache-01', N'10.0.0.31', N'cache');
GO

INSERT INTO app_users (username, email) VALUES
    (N'admin', N'admin@example.com'),
    (N'cmdb_collector', N'cmdb@example.com');
GO

SELECT 'cmdb_test' AS database_name, COUNT(*) AS server_count FROM servers;
SELECT 'cmdb_test' AS database_name, COUNT(*) AS user_count FROM app_users;
GO