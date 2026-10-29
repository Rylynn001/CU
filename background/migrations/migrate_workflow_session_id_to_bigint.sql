-- 将工作流会话 UUID 主键迁移为自增整数，并保留所有现有会话、消息和执行记录。
-- 执行前请备份数据库。此脚本设计为一次性迁移，不要重复执行。

-- 给现有会话分配新的整数编号，同时保留旧编号用于更新子表。
ALTER TABLE workflow_sessions
    ADD COLUMN new_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    ADD UNIQUE KEY uq_workflow_sessions_new_id (new_id);

ALTER TABLE workflow_conversations
    ADD COLUMN new_session_id BIGINT UNSIGNED NULL;

ALTER TABLE workflow_executions
    ADD COLUMN new_session_id BIGINT UNSIGNED NULL;

UPDATE workflow_conversations c
JOIN workflow_sessions s ON c.session_id = s.id
SET c.new_session_id = s.new_id;

UPDATE workflow_executions e
JOIN workflow_sessions s ON e.session_id = s.id
SET e.new_session_id = s.new_id;

-- 用映射后的编号替换子表外键。
ALTER TABLE workflow_conversations
    DROP FOREIGN KEY workflow_conversations_ibfk_1,
    DROP INDEX idx_session_id,
    DROP COLUMN session_id,
    CHANGE COLUMN new_session_id session_id BIGINT UNSIGNED NOT NULL,
    ADD INDEX idx_session_id (session_id);

ALTER TABLE workflow_executions
    DROP FOREIGN KEY workflow_executions_ibfk_1,
    DROP INDEX idx_session_id,
    DROP COLUMN session_id,
    CHANGE COLUMN new_session_id session_id BIGINT UNSIGNED NOT NULL,
    ADD INDEX idx_session_id (session_id);

-- 替换会话主键。new_id 已按旧会话逐条映射，相关子记录已同步更新。
ALTER TABLE workflow_sessions
    DROP PRIMARY KEY,
    DROP COLUMN id,
    CHANGE COLUMN new_id id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    ADD PRIMARY KEY (id);

-- 恢复外键约束。
ALTER TABLE workflow_conversations
    ADD CONSTRAINT workflow_conversations_ibfk_1
    FOREIGN KEY (session_id) REFERENCES workflow_sessions(id) ON DELETE CASCADE;

ALTER TABLE workflow_executions
    ADD CONSTRAINT workflow_executions_ibfk_1
    FOREIGN KEY (session_id) REFERENCES workflow_sessions(id) ON DELETE CASCADE;
