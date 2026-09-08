CREATE TABLE `a_share_security` (
  `full_code` VARCHAR(16) NOT NULL COMMENT '标准完整代码，如600519.SH、000001.SZ、920047.BJ',
  `stock_code` CHAR(6) NOT NULL COMMENT '去除标记后的六位股票代码，如600519',
  `exchange` CHAR(2) NOT NULL COMMENT '交易所标识：SH、SZ或BJ',
  `security_name` VARCHAR(255) NOT NULL COMMENT '证券名称，按AkShare来源原文保存',
  `akshare_symbol` VARCHAR(16) NOT NULL COMMENT 'AkShare代码，如sh600519、sz000001、bj920047',
  `updated_at` DATETIME(6) NOT NULL COMMENT '参考记录最近更新时间（UTC）',
  PRIMARY KEY (`full_code`),
  UNIQUE KEY `uk_a_share_akshare_symbol` (`akshare_symbol`),
  KEY `idx_a_share_stock_code` (`stock_code`),
  KEY `idx_a_share_security_name` (`security_name`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
  COMMENT='当前A股证券参考表：保存名称、标准完整代码和AkShare代码映射';
