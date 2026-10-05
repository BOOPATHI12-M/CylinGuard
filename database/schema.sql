-- ============================================================
-- CylinGuard - Smart LPG Monitoring & Safety System
-- MySQL 8+ schema
-- ============================================================
-- Loaded automatically by the mysql container entrypoint, and
-- by backend/scripts/init_db.py for the no-Docker local path.
-- ============================================================

SET NAMES utf8mb4;

-- ------------------------------------------------------------
-- users
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS users (
    id            INT UNSIGNED NOT NULL AUTO_INCREMENT,
    name          VARCHAR(120)  NOT NULL,
    email         VARCHAR(190)  NOT NULL,
    password_hash VARCHAR(255)  NOT NULL,
    created_at    DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at    DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uq_users_email (email)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ------------------------------------------------------------
-- cylinders
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS cylinders (
    id              INT UNSIGNED  NOT NULL AUTO_INCREMENT,
    user_id         INT UNSIGNED  NOT NULL,
    cylinder_code   VARCHAR(64)   NOT NULL,
    empty_weight_kg DECIMAL(6,3)  NOT NULL DEFAULT 15.000,
    capacity_kg     DECIMAL(6,3)  NOT NULL DEFAULT 14.200,
    created_at      DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uq_cylinders_code (cylinder_code),
    KEY ix_cylinders_user (user_id),
    CONSTRAINT fk_cylinders_user FOREIGN KEY (user_id)
        REFERENCES users (id) ON DELETE CASCADE,
    CONSTRAINT ck_cylinders_capacity CHECK (capacity_kg > 0),
    CONSTRAINT ck_cylinders_empty CHECK (empty_weight_kg >= 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ------------------------------------------------------------
-- devices  (one ESP32 per cylinder)
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS devices (
    id               INT UNSIGNED NOT NULL AUTO_INCREMENT,
    cylinder_id      INT UNSIGNED NOT NULL,
    device_code      VARCHAR(64)  NOT NULL,
    wifi_status      VARCHAR(16)  NOT NULL DEFAULT 'UNKNOWN',
    last_seen        DATETIME     NULL,
    firmware_version VARCHAR(32)  NULL,
    created_at       DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uq_devices_code (device_code),
    KEY ix_devices_cylinder (cylinder_id),
    KEY ix_devices_last_seen (last_seen),
    CONSTRAINT fk_devices_cylinder FOREIGN KEY (cylinder_id)
        REFERENCES cylinders (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ------------------------------------------------------------
-- sensor_readings  (high volume - indexed for range scans)
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS sensor_readings (
    id               BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    cylinder_id      INT UNSIGNED  NOT NULL,
    timestamp        DATETIME      NOT NULL,
    total_weight_kg  DECIMAL(7,3)  NOT NULL,
    gas_sensor_value INT           NOT NULL DEFAULT 0,
    device_status    VARCHAR(16)   NOT NULL DEFAULT 'ONLINE',
    is_simulated     TINYINT(1)    NOT NULL DEFAULT 0,
    created_at       DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    KEY ix_readings_cylinder_ts (cylinder_id, timestamp),
    KEY ix_readings_ts (timestamp),
    CONSTRAINT fk_readings_cylinder FOREIGN KEY (cylinder_id)
        REFERENCES cylinders (id) ON DELETE CASCADE,
    CONSTRAINT ck_readings_weight CHECK (total_weight_kg >= 0),
    CONSTRAINT ck_readings_gas CHECK (gas_sensor_value >= 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ------------------------------------------------------------
-- consumption_records  (one row per cylinder per day)
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS consumption_records (
    id               BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    cylinder_id      INT UNSIGNED NOT NULL,
    record_date      DATE         NOT NULL,
    timestamp        DATETIME     NOT NULL,
    consumption_kg   DECIMAL(7,3) NOT NULL DEFAULT 0.000,
    daily_average_kg DECIMAL(7,3) NOT NULL DEFAULT 0.000,
    created_at       DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uq_consumption_cyl_date (cylinder_id, record_date),
    KEY ix_consumption_cylinder_ts (cylinder_id, timestamp),
    CONSTRAINT fk_consumption_cylinder FOREIGN KEY (cylinder_id)
        REFERENCES cylinders (id) ON DELETE CASCADE,
    CONSTRAINT ck_consumption_nonneg CHECK (consumption_kg >= 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ------------------------------------------------------------
-- predictions
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS predictions (
    id                       BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    cylinder_id              INT UNSIGNED NOT NULL,
    timestamp                DATETIME     NOT NULL,
    remaining_kg             DECIMAL(7,3) NOT NULL,
    remaining_days           DECIMAL(6,2) NOT NULL,
    predicted_depletion_date DATE         NULL,
    confidence               DECIMAL(4,3) NOT NULL DEFAULT 0.000,
    method                   VARCHAR(16)  NOT NULL DEFAULT 'FALLBACK',
    sample_count             INT          NOT NULL DEFAULT 0,
    created_at               DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    KEY ix_predictions_cylinder_ts (cylinder_id, timestamp),
    CONSTRAINT fk_predictions_cylinder FOREIGN KEY (cylinder_id)
        REFERENCES cylinders (id) ON DELETE CASCADE,
    CONSTRAINT ck_predictions_conf CHECK (confidence >= 0 AND confidence <= 1)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ------------------------------------------------------------
-- alerts
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS alerts (
    id          BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    cylinder_id INT UNSIGNED NOT NULL,
    type        VARCHAR(48)  NOT NULL,
    severity    ENUM('INFO','WARNING','CRITICAL') NOT NULL DEFAULT 'INFO',
    message     VARCHAR(512) NOT NULL,
    is_read     TINYINT(1)   NOT NULL DEFAULT 0,
    created_at  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    KEY ix_alerts_cylinder_created (cylinder_id, created_at),
    KEY ix_alerts_unread (cylinder_id, is_read),
    CONSTRAINT fk_alerts_cylinder FOREIGN KEY (cylinder_id)
        REFERENCES cylinders (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ------------------------------------------------------------
-- safety_events
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS safety_events (
    id            BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    cylinder_id   INT UNSIGNED NOT NULL,
    gas_value     INT          NOT NULL,
    threshold     INT          NOT NULL,
    buzzer_status VARCHAR(16)  NOT NULL DEFAULT 'OFF',
    relay_status  VARCHAR(16)  NOT NULL DEFAULT 'NORMAL',
    event_type    VARCHAR(32)  NOT NULL,
    created_at    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    KEY ix_safety_cylinder_created (cylinder_id, created_at),
    CONSTRAINT fk_safety_cylinder FOREIGN KEY (cylinder_id)
        REFERENCES cylinders (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ------------------------------------------------------------
-- settings  (one row per cylinder)
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS settings (
    id                     INT UNSIGNED NOT NULL AUTO_INCREMENT,
    cylinder_id            INT UNSIGNED NOT NULL,
    low_lpg_threshold      DECIMAL(5,2) NOT NULL DEFAULT 20.00,
    critical_lpg_threshold DECIMAL(5,2) NOT NULL DEFAULT 10.00,
    gas_leakage_threshold  INT          NOT NULL DEFAULT 700,
    anomaly_threshold      DECIMAL(5,2) NOT NULL DEFAULT 60.00,
    measurement_interval   INT          NOT NULL DEFAULT 30,
    prediction_threshold   INT          NOT NULL DEFAULT 5,
    demo_mode              TINYINT(1)   NOT NULL DEFAULT 1,
    updated_at             DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uq_settings_cylinder (cylinder_id),
    CONSTRAINT fk_settings_cylinder FOREIGN KEY (cylinder_id)
        REFERENCES cylinders (id) ON DELETE CASCADE,
    CONSTRAINT ck_settings_gas CHECK (gas_leakage_threshold > 0),
    CONSTRAINT ck_settings_interval CHECK (measurement_interval > 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
