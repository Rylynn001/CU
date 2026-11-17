-- 在 20261116_canvas_workflow.sql 之后执行；不修改已有生成结果。
ALTER TABLE workflow_executions MODIFY COLUMN status VARCHAR(20) NULL DEFAULT 'running';

CREATE TABLE workflow_generation_plans (
  id CHAR(36) NOT NULL PRIMARY KEY,
  user_id BIGINT UNSIGNED NOT NULL,
  canvas_id BIGINT UNSIGNED NOT NULL,
  session_id BIGINT UNSIGNED NOT NULL,
  definition JSON NOT NULL,
  status VARCHAR(20) NOT NULL DEFAULT 'running',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  INDEX idx_active_plans (status, created_at),
  INDEX idx_plan_session (session_id),
  CONSTRAINT fk_plan_canvas FOREIGN KEY (canvas_id) REFERENCES canvas(id),
  CONSTRAINT fk_plan_session FOREIGN KEY (session_id) REFERENCES workflow_sessions(id)
);
