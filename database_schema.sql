-- データベース作成
CREATE DATABASE IF NOT EXISTS pos_system CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE pos_system;

-- 店舗用商品マスタテーブル
CREATE TABLE store_products (
    PRD_ID INT AUTO_INCREMENT PRIMARY KEY,
    CODE BIGINT NOT NULL,  -- INTからBIGINTに変更
    NAME VARCHAR(50) NOT NULL,
    PRICE INT NOT NULL,
    stock_quantity INT NOT NULL DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY unique_code (CODE),
    INDEX idx_code (CODE)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 本部用商品マスタテーブル (EC在庫確認用)
CREATE TABLE headquarters_products (
    PRD_ID INT AUTO_INCREMENT PRIMARY KEY,
    CODE BIGINT NOT NULL,  -- INTからBIGINTに変更
    NAME VARCHAR(50) NOT NULL,
    std_PRICE INT NOT NULL,
    ec_stock_quantity INT NOT NULL DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY unique_code (CODE),
    INDEX idx_code (CODE)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 売上トランザクションテーブル
CREATE TABLE sales_transactions (
    transaction_id INT AUTO_INCREMENT PRIMARY KEY,
    transaction_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    total_amount INT NOT NULL,
    payment_method ENUM('cash', 'credit', 'qr', 'emoney', 'pending') NOT NULL,
    cash_received INT DEFAULT NULL,
    change_amount INT DEFAULT NULL,
    is_pending BOOLEAN DEFAULT FALSE,
    is_cancelled BOOLEAN DEFAULT FALSE,
    cancelled_at TIMESTAMP NULL,
    INDEX idx_date (transaction_date),
    INDEX idx_cancelled (is_cancelled),
    INDEX idx_pending (is_pending)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 売上明細テーブル
CREATE TABLE sales_details (
    detail_id INT AUTO_INCREMENT PRIMARY KEY,
    transaction_id INT NOT NULL,
    PRD_ID INT NOT NULL,
    CODE BIGINT NOT NULL,  -- INTからBIGINTに変更
    NAME VARCHAR(50) NOT NULL,
    PRICE INT NOT NULL,
    quantity INT NOT NULL,
    subtotal INT NOT NULL,
    FOREIGN KEY (transaction_id) REFERENCES sales_transactions(transaction_id) ON DELETE CASCADE,
    FOREIGN KEY (PRD_ID) REFERENCES store_products(PRD_ID),
    INDEX idx_transaction (transaction_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 60日より古いデータを削除するイベント
CREATE EVENT IF NOT EXISTS cleanup_old_sales
ON SCHEDULE EVERY 1 DAY
DO
DELETE FROM sales_transactions 
WHERE transaction_date < DATE_SUB(NOW(), INTERVAL 60 DAY);

-- サンプルデータ挿入
INSERT INTO store_products (CODE, NAME, PRICE, stock_quantity) VALUES
(4902505364143, 'キャップレス　螺鈿ブラック／ペン種： M', 100000, 2),
(4902505638060, 'ジュースアップ4 シルバー', 600, 10),
(4902505625763, 'ソフト筆入 ワノフ　ネイビー', 1800, 5),
(4902505507601, 'フリクションボールスリムビズ', 1000, 10),
(4902505146190, 'ホワイトボード ホームボードＶシリーズ Lサイズ', 1700, 5);

INSERT INTO headquarters_products (CODE, NAME, std_PRICE, ec_stock_quantity) VALUES
(4902505364143, 'キャップレス　螺鈿ブラック／ペン種： M', 100000, 5),
(4902505638060, 'ジュースアップ4 シルバー', 600, 100),
(4902505625763, 'ソフト筆入 ワノフ　ネイビー', 1800, 30),
(4902505507601, 'フリクションボールスリムビズ', 1000, 1000),
(4902505146190, 'ホワイトボード ホームボードＶシリーズ Lサイズ', 1700, 20);