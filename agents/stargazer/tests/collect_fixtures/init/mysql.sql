-- MySQL 初始化：建测试库 + 测试表 + 种子数据
-- 用于采集器产出有意义数据
CREATE DATABASE IF NOT EXISTS test_db;
USE test_db;
CREATE TABLE IF NOT EXISTS test_users (
    id INT PRIMARY KEY AUTO_INCREMENT,
    name VARCHAR(50),
    age INT
);
INSERT INTO test_users (name, age) VALUES
    ('alice', 30), ('bob', 25), ('charlie', 35),
    ('diana', 28), ('eve', 40);