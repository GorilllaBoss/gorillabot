CREATE TABLE IF NOT EXISTS projects (
  project_id UUID PRIMARY KEY,
  user_id BIGINT NOT NULL,
  channel_username TEXT NOT NULL,
  channel_id BIGINT,
  theme TEXT,
  custom_theme TEXT,
  post_style TEXT,
  posting_frequency TEXT,
  posting_time TEXT,
  content_sources JSONB NOT NULL DEFAULT '[]'::jsonb,
  is_autopost_enabled BOOLEAN NOT NULL DEFAULT FALSE,
  created_at TIMESTAMP NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS project_examples (
  example_id BIGSERIAL PRIMARY KEY,
  project_id UUID NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
  text TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS scheduler_settings (
  project_id UUID PRIMARY KEY REFERENCES projects(project_id) ON DELETE CASCADE,
  daily_posts INT NOT NULL DEFAULT 1,
  weekly_mode BOOLEAN NOT NULL DEFAULT FALSE,
  random_mode BOOLEAN NOT NULL DEFAULT FALSE,
  timezone TEXT NOT NULL DEFAULT 'Europe/Moscow'
);

-- Existing profile table for Navigator module
CREATE TABLE IF NOT EXISTS user_life_profile (
  user_id BIGINT PRIMARY KEY,
  answers_json JSONB NOT NULL DEFAULT '[]'::jsonb,
  ai_analysis TEXT,
  archetype TEXT,
  goals JSONB NOT NULL DEFAULT '[]'::jsonb,
  daily_plan TEXT,
  weekly_plan TEXT,
  monthly_plan TEXT,
  reminder_settings JSONB NOT NULL DEFAULT '{}'::jsonb,
  history JSONB NOT NULL DEFAULT '[]'::jsonb,
  created_at TIMESTAMP NOT NULL DEFAULT NOW(),
  last_update TIMESTAMP NOT NULL DEFAULT NOW()
);
