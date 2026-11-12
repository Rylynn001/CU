-- 在现有业务数据库中执行；不修改资产、历史记录、节点面板表。
CREATE TABLE IF NOT EXISTS `canvas` (
  `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '画布 ID',
  `user_id` BIGINT UNSIGNED NOT NULL COMMENT '所属用户，沿用登录用户 ID',
  `name` VARCHAR(100) NOT NULL DEFAULT '新画布' COMMENT '画布名称',
  `document` JSON NOT NULL COMMENT '完整画布：version、nodes、edges、viewport；素材只引用资产 ID',
  `created_at` DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  `updated_at` DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
  `deleted_at` DATETIME(3) NULL DEFAULT NULL COMMENT '软删除时间',
  PRIMARY KEY (`id`),
  KEY `idx_canvas_user_list` (`user_id`, `deleted_at`, `updated_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='独立创作画布';
