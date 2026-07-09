from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "food_logs" ADD "meal_name" VARCHAR(200);"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "food_logs" DROP COLUMN "meal_name";"""
