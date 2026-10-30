-- Apply after 20261030_annual_plans.sql, once, before deploying the new views.
ALTER TABLE annual_targets
  ADD COLUMN comparison_rule VARCHAR(4) NOT NULL DEFAULT 'gte',
  ADD COLUMN is_active BOOLEAN NOT NULL DEFAULT TRUE;
-- Preserve campus scope: deleting a campus must never turn its targets into university targets.
ALTER TABLE annual_targets DROP FOREIGN KEY fk_annual_targets_campus;
ALTER TABLE annual_targets ADD CONSTRAINT fk_annual_targets_campus_workflow
  FOREIGN KEY (campus_id) REFERENCES campuses(id) ON DELETE RESTRICT;
ALTER TABLE annual_results
  ADD COLUMN coverage_start DATE NULL,
  ADD COLUMN coverage_end DATE NULL,
  ADD COLUMN sex_counts JSON NULL;
CREATE TABLE annual_activity_mappings (
 id INT NOT NULL AUTO_INCREMENT PRIMARY KEY, target_id INT NOT NULL, event_id INT NOT NULL,
 CONSTRAINT uq_annual_target_event UNIQUE(target_id,event_id),
 FOREIGN KEY(target_id) REFERENCES annual_targets(id) ON DELETE CASCADE,
 FOREIGN KEY(event_id) REFERENCES events(id) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE annual_goal_proposals (
 id INT NOT NULL AUTO_INCREMENT PRIMARY KEY, campus_id INT NULL,
 replaces_target_id INT NULL, published_target_id INT NULL, payload JSON NOT NULL,
 status VARCHAR(16) NOT NULL DEFAULT 'draft', proposed_by_id INT NOT NULL, reviewed_by_id INT NULL,
 created_at DATETIME NOT NULL, submitted_at DATETIME NULL, reviewed_at DATETIME NULL,
 review_note TEXT NULL, history JSON NOT NULL,
 FOREIGN KEY(campus_id) REFERENCES campuses(id) ON DELETE RESTRICT,
 FOREIGN KEY(replaces_target_id) REFERENCES annual_targets(id) ON DELETE RESTRICT,
 FOREIGN KEY(published_target_id) REFERENCES annual_targets(id) ON DELETE RESTRICT,
 FOREIGN KEY(proposed_by_id) REFERENCES users(id) ON DELETE RESTRICT,
 FOREIGN KEY(reviewed_by_id) REFERENCES users(id) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
