CREATE TABLE IF NOT EXISTS annual_plans (
    id INT NOT NULL AUTO_INCREMENT, source_key VARCHAR(100) NOT NULL,
    year INT NOT NULL, plan_type ENUM('AOP','ASP') NOT NULL, title VARCHAR(255) NOT NULL,
    status ENUM('approved','superseded') NOT NULL DEFAULT 'approved',
    source_document VARCHAR(255) NOT NULL, approval_reference VARCHAR(120) NULL,
    approval_date DATE NULL, imported_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id), UNIQUE KEY uq_annual_plans_source_key (source_key), KEY ix_annual_plans_year (year)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
CREATE TABLE IF NOT EXISTS annual_indicators (
    id INT NOT NULL AUTO_INCREMENT, source_key VARCHAR(100) NOT NULL, plan_id INT NOT NULL,
    code VARCHAR(80) NOT NULL, program VARCHAR(255) NOT NULL, name VARCHAR(500) NOT NULL,
    definition TEXT NULL, unit VARCHAR(80) NOT NULL, responsible_office VARCHAR(255) NOT NULL,
    evidence_basis VARCHAR(80) NOT NULL DEFAULT 'verified_attendance', shared_key VARCHAR(100) NULL,
    PRIMARY KEY (id), UNIQUE KEY uq_annual_indicators_source_key (source_key),
    KEY ix_annual_indicators_shared_key (shared_key),
    CONSTRAINT fk_annual_indicators_plan FOREIGN KEY (plan_id) REFERENCES annual_plans(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
CREATE TABLE IF NOT EXISTS annual_targets (
    id INT NOT NULL AUTO_INCREMENT, source_key VARCHAR(100) NOT NULL, indicator_id INT NOT NULL,
    campus_id INT NULL, target_value DECIMAL(18,4) NOT NULL, deadline DATE NULL, activity_scope VARCHAR(80) NULL,
    PRIMARY KEY (id), UNIQUE KEY uq_annual_targets_source_key (source_key),
    CONSTRAINT fk_annual_targets_indicator FOREIGN KEY (indicator_id) REFERENCES annual_indicators(id) ON DELETE CASCADE,
    CONSTRAINT fk_annual_targets_campus FOREIGN KEY (campus_id) REFERENCES campuses(id) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
CREATE TABLE IF NOT EXISTS annual_results (
    id INT NOT NULL AUTO_INCREMENT, source_key VARCHAR(100) NOT NULL, target_id INT NOT NULL,
    actual_value DECIMAL(18,4) NULL, evidence_status ENUM('pending','verified') NOT NULL DEFAULT 'pending',
    result_type ENUM('calculated','approved_aggregate') NOT NULL, source_document VARCHAR(255) NULL,
    coverage_note TEXT NULL, imported_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id), UNIQUE KEY uq_annual_results_source_key (source_key),
    CONSTRAINT fk_annual_results_target FOREIGN KEY (target_id) REFERENCES annual_targets(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
