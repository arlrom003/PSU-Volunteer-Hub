-- Optional gender response for external volunteers and sex-disaggregated reports.
ALTER TABLE external_participants
  ADD COLUMN sex ENUM('male', 'female', 'prefer_not_to_say') NULL AFTER email;
