ALTER TABLE workflow_sessions
    ADD COLUMN deleted_at DATETIME NULL DEFAULT NULL COMMENT '软删除时间';
