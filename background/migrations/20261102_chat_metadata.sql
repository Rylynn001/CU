-- 保存公开的工具调用过程和供应商返回的用量，历史消息保持兼容。
ALTER TABLE workflow_conversations ADD COLUMN metadata JSON NULL;

-- 未知模型保留空值，不使用其他模型的容量冒充。
ALTER TABLE api_models ADD COLUMN context_window INT UNSIGNED NULL COMMENT '上下文窗口大小（令牌）';
-- 来源：https://developers.openai.com/api/docs/models/gpt-6.1-sol
UPDATE api_models SET context_window = 1050000 WHERE name = 'gpt-6.1-sol' AND type = 'language';
