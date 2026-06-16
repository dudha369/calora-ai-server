from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS "users" (
    "telegram_id" BIGINT NOT NULL PRIMARY KEY,
    "full_name" VARCHAR(120) NOT NULL,
    "username" VARCHAR(64),
    "language_code" VARCHAR(8) NOT NULL DEFAULT 'ru',
    "current_streak" INT NOT NULL DEFAULT 0,
    "max_streak" INT NOT NULL DEFAULT 0,
    "quests_completed" INT NOT NULL DEFAULT 0,
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "last_active_at" TIMESTAMPTZ,
    "is_active" BOOL NOT NULL DEFAULT True,
    "deleted_at" TIMESTAMPTZ
);
COMMENT ON TABLE "users" IS 'Пользователь Telegram.';
CREATE TABLE IF NOT EXISTS "user_profiles" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "gender" VARCHAR(6) NOT NULL,
    "birth_date" DATE NOT NULL,
    "height_cm" SMALLINT NOT NULL,
    "weight_kg" DECIMAL(5,1) NOT NULL,
    "goal_type" VARCHAR(10) NOT NULL,
    "target_weight_kg" DECIMAL(5,1),
    "activity_level" VARCHAR(12) NOT NULL,
    "water_track" VARCHAR(6) NOT NULL DEFAULT 'auto',
    "water_goal_ml" SMALLINT,
    "dietary_restrictions" JSONB NOT NULL,
    "allergy_note" TEXT,
    "medical_conditions" JSONB NOT NULL,
    "timezone" VARCHAR(40) NOT NULL DEFAULT 'Europe/Kyiv',
    "units_preference" VARCHAR(10) NOT NULL DEFAULT 'metric',
    "updated_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "user_id" BIGINT NOT NULL UNIQUE REFERENCES "users" ("telegram_id") ON DELETE CASCADE
);
COMMENT ON TABLE "user_profiles" IS 'Биометрия и настройки пользователя (1:1 с User).';
CREATE TABLE IF NOT EXISTS "onboarding_drafts" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "step" SMALLINT NOT NULL DEFAULT 0,
    "gender" VARCHAR(6),
    "birth_date" DATE,
    "height_cm" SMALLINT,
    "weight_kg" DECIMAL(5,1),
    "goal" VARCHAR(10),
    "target_weight" DECIMAL(5,1),
    "activity_level" DOUBLE PRECISION,
    "dietary_restrictions" JSONB NOT NULL,
    "allergy_note" TEXT,
    "water_track" VARCHAR(6),
    "water_goal_ml" SMALLINT,
    "medical_conditions" JSONB NOT NULL,
    "timezone" VARCHAR(40),
    "user_id" BIGINT NOT NULL UNIQUE REFERENCES "users" ("telegram_id") ON DELETE CASCADE
);
COMMENT ON TABLE "onboarding_drafts" IS 'Черновик онбординга — хранит частично заполненные данные пока пользователь';
CREATE TABLE IF NOT EXISTS "daily_goals" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "calories" SMALLINT NOT NULL,
    "protein_g" DECIMAL(5,1) NOT NULL,
    "fat_g" DECIMAL(5,1) NOT NULL,
    "carbs_g" DECIMAL(5,1) NOT NULL,
    "water_ml" SMALLINT NOT NULL,
    "ai_tip" TEXT,
    "user_id" BIGINT NOT NULL UNIQUE REFERENCES "users" ("telegram_id") ON DELETE CASCADE
);
COMMENT ON TABLE "daily_goals" IS 'Рассчитанные дневные нормы (1:1 с User).';
CREATE TABLE IF NOT EXISTS "weight_history" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "weight_kg" DECIMAL(5,1) NOT NULL,
    "log_date" DATE,
    "recorded_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "user_id" BIGINT NOT NULL REFERENCES "users" ("telegram_id") ON DELETE CASCADE
);
COMMENT ON TABLE "weight_history" IS 'История взвешиваний для графика прогресса.';
CREATE TABLE IF NOT EXISTS "food_logs" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "log_date" DATE NOT NULL,
    "logged_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "photo_url" TEXT,
    "total_calories" SMALLINT NOT NULL DEFAULT 0,
    "total_protein_g" DECIMAL(6,1) NOT NULL DEFAULT 0,
    "total_fat_g" DECIMAL(6,1) NOT NULL DEFAULT 0,
    "total_carbs_g" DECIMAL(6,1) NOT NULL DEFAULT 0,
    "total_fiber_g" DECIMAL(6,1) NOT NULL DEFAULT 0,
    "total_sugar_g" DECIMAL(6,1) NOT NULL DEFAULT 0,
    "user_id" BIGINT NOT NULL REFERENCES "users" ("telegram_id") ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS "idx_food_logs_user_id_fe34d4" ON "food_logs" ("user_id", "log_date");
COMMENT ON TABLE "food_logs" IS 'Одна запись еды пользователя (без деления на завтрак/обед/ужин).';
CREATE TABLE IF NOT EXISTS "food_items" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "food_name" VARCHAR(200) NOT NULL,
    "portion_g" DECIMAL(6,1) NOT NULL,
    "calories" SMALLINT NOT NULL,
    "protein_g" DECIMAL(5,1) NOT NULL,
    "fat_g" DECIMAL(5,1) NOT NULL,
    "carbs_g" DECIMAL(5,1) NOT NULL,
    "fiber_g" DECIMAL(5,1) NOT NULL DEFAULT 0,
    "sugar_g" DECIMAL(5,1) NOT NULL DEFAULT 0,
    "food_log_id" INT NOT NULL REFERENCES "food_logs" ("id") ON DELETE CASCADE
);
COMMENT ON TABLE "food_items" IS 'Отдельное блюдо/продукт внутри FoodLog.';
CREATE TABLE IF NOT EXISTS "water_logs" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "log_date" DATE NOT NULL,
    "logged_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "amount_ml" SMALLINT NOT NULL,
    "user_id" BIGINT NOT NULL REFERENCES "users" ("telegram_id") ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS "idx_water_logs_user_id_93b1ba" ON "water_logs" ("user_id", "log_date");
CREATE TABLE IF NOT EXISTS "quests" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "quest_key" VARCHAR(40) NOT NULL,
    "title" VARCHAR(100) NOT NULL,
    "description" TEXT NOT NULL,
    "icon" VARCHAR(8) NOT NULL,
    "target_value" DECIMAL(8,1) NOT NULL,
    "current_value" DECIMAL(8,1) NOT NULL DEFAULT 0,
    "status" VARCHAR(10) NOT NULL DEFAULT 'active',
    "expires_at" TIMESTAMPTZ NOT NULL,
    "completed_at" TIMESTAMPTZ,
    "user_id" BIGINT NOT NULL REFERENCES "users" ("telegram_id") ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS "idx_quests_user_id_7f2f42" ON "quests" ("user_id", "status");
COMMENT ON TABLE "quests" IS 'Квест пользователя. Генерируется Gemini раз в неделю.';
CREATE TABLE IF NOT EXISTS "ai_tips" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "tip_text" TEXT NOT NULL,
    "tip_type" VARCHAR(20) NOT NULL,
    "icon" VARCHAR(8) NOT NULL,
    "based_on_date" DATE NOT NULL,
    "user_id" BIGINT NOT NULL REFERENCES "users" ("telegram_id") ON DELETE CASCADE,
    CONSTRAINT "uid_ai_tips_user_id_f6f1c3" UNIQUE ("user_id", "based_on_date")
);
COMMENT ON TABLE "ai_tips" IS 'Ежедневный совет от Gemini (промт tips). Один совет в день на пользователя.';
CREATE TABLE IF NOT EXISTS "app_settings" (
    "key" VARCHAR(64) NOT NULL PRIMARY KEY,
    "value" TEXT NOT NULL
);
COMMENT ON TABLE "app_settings" IS 'Key-value таблица для feature flags и настроек приложения.';
CREATE TABLE IF NOT EXISTS "broadcasts" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "text" TEXT NOT NULL,
    "photo_url" TEXT,
    "segment" VARCHAR(32) NOT NULL DEFAULT 'all',
    "button_text" VARCHAR(64),
    "button_url" TEXT,
    "status" VARCHAR(16) NOT NULL DEFAULT 'pending',
    "total" INT NOT NULL DEFAULT 0,
    "sent" INT NOT NULL DEFAULT 0,
    "failed" INT NOT NULL DEFAULT 0,
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "finished_at" TIMESTAMPTZ
);
COMMENT ON TABLE "broadcasts" IS 'История рассылок, отправленных через админ-панель.';
CREATE TABLE IF NOT EXISTS "aerich" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "version" VARCHAR(255) NOT NULL,
    "app" VARCHAR(100) NOT NULL,
    "content" JSONB NOT NULL
);"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        """


MODELS_STATE = (
    "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"
)
