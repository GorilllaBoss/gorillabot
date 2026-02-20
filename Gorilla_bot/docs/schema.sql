CREATE TABLE IF NOT EXISTS users (
  id BIGSERIAL PRIMARY KEY,
  telegram_user_id BIGINT UNIQUE NOT NULL,
  is_premium BOOLEAN NOT NULL DEFAULT FALSE,
  created_at TIMESTAMP NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS channels (
  id BIGSERIAL PRIMARY KEY,
  user_id BIGINT NOT NULL REFERENCES users(telegram_user_id),
  channel_username TEXT,
  channel_chat_id BIGINT,
  bot_is_admin BOOLEAN NOT NULL DEFAULT FALSE,
  can_post BOOLEAN NOT NULL DEFAULT FALSE,
  created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS projects (
  id UUID PRIMARY KEY,
  user_id BIGINT NOT NULL REFERENCES users(telegram_user_id),
  channel_id BIGINT REFERENCES channels(id),
  topic TEXT NOT NULL,
  style TEXT NOT NULL,
  formatting JSONB NOT NULL,
  frequency JSONB NOT NULL,
  sources JSONB NOT NULL,
  permissions JSONB NOT NULL,
  enabled BOOLEAN NOT NULL DEFAULT FALSE,
  created_at TIMESTAMP NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS posting_jobs (
  id BIGSERIAL PRIMARY KEY,
  project_id UUID NOT NULL REFERENCES projects(id),
  status TEXT NOT NULL,
  payload JSONB,
  scheduled_at TIMESTAMP,
  executed_at TIMESTAMP,
  error TEXT
);

CREATE TABLE IF NOT EXISTS user_life_profile (
  user_id BIGINT PRIMARY KEY REFERENCES users(telegram_user_id),
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
