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
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
COMMENT ON TABLE "users" IS 'Пользователь Telegram.';
CREATE TABLE IF NOT EXISTS "user_profiles" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "gender" VARCHAR(6) NOT NULL,
    "age" SMALLINT NOT NULL,
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
    "user_id" BIGINT NOT NULL UNIQUE REFERENCES "users" ("telegram_id") ON DELETE CASCADE
);
COMMENT ON TABLE "user_profiles" IS 'Биометрия и настройки пользователя (1:1 с User).';
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
