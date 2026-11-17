-- 开发环境结构调整，不迁移旧会话。旧记录的 canvas_id 保留为空，不进入画布会话列表。
ALTER TABLE workflow_sessions
  ADD COLUMN canvas_id BIGINT UNSIGNED NULL AFTER user_id,
  ADD INDEX idx_canvas_sessions (canvas_id, user_id, deleted_at, updated_at),
  ADD CONSTRAINT fk_session_canvas FOREIGN KEY (canvas_id) REFERENCES canvas(id);

-- 画布、节点是任务的归属；会话和消息仅记录任务的发起来源。
ALTER TABLE workflow_executions
  MODIFY COLUMN session_id BIGINT UNSIGNED NULL,
  ADD COLUMN canvas_id BIGINT UNSIGNED NULL AFTER id,
  ADD COLUMN node_id VARCHAR(36) NULL AFTER canvas_id,
  ADD INDEX idx_canvas_node (canvas_id, node_id, started_at),
  ADD CONSTRAINT fk_execution_canvas FOREIGN KEY (canvas_id) REFERENCES canvas(id),
  ADD CONSTRAINT fk_execution_source_session FOREIGN KEY (session_id) REFERENCES workflow_sessions(id) ON DELETE SET NULL;
