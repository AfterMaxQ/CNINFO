CREATE TABLE `crawl_run` (
  `run_id` CHAR(36) NOT NULL COMMENT '运行唯一标识，使用 UUID',
  `status` VARCHAR(24) NOT NULL COMMENT '运行状态',
  `started_at` DATETIME(6) NOT NULL COMMENT '运行开始时间（UTC）',
  `finished_at` DATETIME(6) NULL COMMENT '运行结束或暂停时间（UTC）',
  `export_path` VARCHAR(512) NULL COMMENT '最近一次九字段 XLSX 相对路径',
  `last_error_message` VARCHAR(1000) NULL COMMENT '最近一次已脱敏运行错误',
  PRIMARY KEY (`run_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='采集运行表：保存一次全站采集的状态和最终导出信息';

CREATE TABLE `industry_chain` (
  `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '数据库内部主题主键',
  `chain_id` VARCHAR(64) NOT NULL COMMENT 'CNINFO 返回的主题 ID',
  `chain_name` VARCHAR(255) NOT NULL COMMENT 'CNINFO 返回的主题正式名称',
  `menu_name` VARCHAR(255) NOT NULL COMMENT '主题所属目录名称',
  `sort_no` INT UNSIGNED NOT NULL COMMENT '主题在根目录响应中的来源顺序',
  `enabled` TINYINT(1) NOT NULL DEFAULT 1 COMMENT '目录是否仍包含该主题',
  `updated_at` DATETIME(6) NOT NULL COMMENT '主题最近更新时间（UTC）',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_industry_chain_chain_id` (`chain_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='产业链主题表：保存 CNINFO 主题和目录信息';

CREATE TABLE `company` (
  `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '数据库内部企业主键',
  `cninfo_company_id` VARCHAR(64) NULL COMMENT 'CNINFO 返回的企业 ID',
  `stock_code` VARCHAR(32) NULL COMMENT '接口返回的股票代码',
  `company_name` VARCHAR(512) NOT NULL COMMENT '接口返回的企业全称或原始名称',
  `company_short_name` VARCHAR(255) NULL COMMENT '接口返回并标准化的企业简称',
  `normalized_name` VARCHAR(512) NOT NULL COMMENT '内部精确去重名称',
  `listing_status` TINYINT UNSIGNED NOT NULL DEFAULT 9 COMMENT '上市状态：0非上市1上市2冲突9未知',
  `updated_at` DATETIME(6) NOT NULL COMMENT '企业最近更新时间（UTC）',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_company_cninfo_id` (`cninfo_company_id`),
  KEY `idx_company_stock_code` (`stock_code`),
  KEY `idx_company_short_name` (`company_short_name`),
  KEY `idx_company_normalized_name` (`normalized_name`(191))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='企业表：保存企业原名、标准化简称、接口代码和上市状态';

CREATE TABLE `industry_chain_node` (
  `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '数据库内部节点主键',
  `industry_chain_id` BIGINT UNSIGNED NOT NULL COMMENT '所属产业链主题内部主键',
  `node_id` VARCHAR(64) NOT NULL COMMENT 'CNINFO 返回的节点 ID',
  `parent_id` BIGINT UNSIGNED NULL COMMENT '父节点内部主键',
  `node_name` VARCHAR(255) NOT NULL COMMENT '节点原始名称',
  `node_definition` TEXT NULL COMMENT 'CNINFO 节点定义原文',
  `business_zone` VARCHAR(16) NOT NULL COMMENT '业务分类：上游中游下游或其他',
  `sort_no` INT UNSIGNED NOT NULL COMMENT '节点在主题中的来源顺序',
  `path_json` JSON NOT NULL COMMENT '从分区根节点到当前节点的名称数组',
  `industry_code` VARCHAR(64) NULL COMMENT '企业接口使用的行业编码',
  `industry_name` VARCHAR(255) NULL COMMENT '接口返回的行业名称',
  `source_url` VARCHAR(1024) NOT NULL COMMENT '当前节点 CNINFO 页面地址',
  `data_status` VARCHAR(24) NOT NULL COMMENT '节点当前业务数据状态',
  `updated_at` DATETIME(6) NOT NULL COMMENT '节点最近更新时间（UTC）',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_chain_node` (`industry_chain_id`, `node_id`),
  KEY `idx_chain_node_sort` (`industry_chain_id`, `sort_no`),
  KEY `idx_chain_node_parent` (`parent_id`),
  CONSTRAINT `fk_node_chain` FOREIGN KEY (`industry_chain_id`) REFERENCES `industry_chain` (`id`),
  CONSTRAINT `fk_node_parent` FOREIGN KEY (`parent_id`) REFERENCES `industry_chain_node` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='产业链节点表：保存节点、定义、路径、行业编码和当前数据状态';

CREATE TABLE `industry_chain_company` (
  `industry_chain_node_id` BIGINT UNSIGNED NOT NULL COMMENT '关联的产业链节点内部主键',
  `company_id` BIGINT UNSIGNED NOT NULL COMMENT '关联的企业内部主键',
  `listing_status` TINYINT UNSIGNED NOT NULL DEFAULT 9 COMMENT '节点下上市状态：0非上市1上市2冲突9未知',
  `sort_no` INT UNSIGNED NOT NULL COMMENT '企业在节点中的来源顺序',
  PRIMARY KEY (`industry_chain_node_id`, `company_id`),
  KEY `idx_chain_company_company` (`company_id`),
  CONSTRAINT `fk_chain_company_node` FOREIGN KEY (`industry_chain_node_id`) REFERENCES `industry_chain_node` (`id`),
  CONSTRAINT `fk_chain_company_company` FOREIGN KEY (`company_id`) REFERENCES `company` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='节点企业关系表：保存当前节点、企业及节点级上市状态';

CREATE TABLE `crawl_node_task` (
  `run_id` CHAR(36) NOT NULL COMMENT '所属采集运行唯一标识',
  `industry_chain_node_id` BIGINT UNSIGNED NOT NULL COMMENT '被采集节点内部主键',
  `status` VARCHAR(24) NOT NULL COMMENT '节点执行状态',
  `retry_count` SMALLINT UNSIGNED NOT NULL DEFAULT 0 COMMENT '节点已重试次数',
  `error_message` VARCHAR(1000) NULL COMMENT '最近一次已脱敏失败原因',
  `updated_at` DATETIME(6) NOT NULL COMMENT '任务状态最近更新时间（UTC）',
  PRIMARY KEY (`run_id`, `industry_chain_node_id`),
  KEY `idx_crawl_task_status` (`run_id`, `status`),
  KEY `idx_crawl_task_node` (`industry_chain_node_id`),
  CONSTRAINT `fk_task_run` FOREIGN KEY (`run_id`) REFERENCES `crawl_run` (`run_id`),
  CONSTRAINT `fk_task_node` FOREIGN KEY (`industry_chain_node_id`) REFERENCES `industry_chain_node` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='节点采集任务表：保存每次运行中每个节点的进度和失败原因';
