-- Создание баз данных для каждого сервиса
CREATE DATABASE neomarket_b2b;
CREATE DATABASE neomarket_b2c;
CREATE DATABASE neomarket_moderation;

-- Предоставление прав пользователю neomarket
GRANT ALL PRIVILEGES ON DATABASE neomarket_b2b TO neomarket;
GRANT ALL PRIVILEGES ON DATABASE neomarket_b2c TO neomarket;
GRANT ALL PRIVILEGES ON DATABASE neomarket_moderation TO neomarket;
