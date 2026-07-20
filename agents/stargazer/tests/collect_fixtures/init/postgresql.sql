-- PostgreSQL 初始化：建测试库 + 测试表 + 种子数据
CREATE TABLE test_users (
    id SERIAL PRIMARY KEY,
    name VARCHAR(50),
    age INT
);
INSERT INTO test_users (name, age) VALUES
    ('alice', 30), ('bob', 25), ('charlie', 35),
    ('diana', 28), ('eve', 40);