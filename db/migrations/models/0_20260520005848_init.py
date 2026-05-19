from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS "user" (
    "id" BIGSERIAL NOT NULL PRIMARY KEY,
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "name" VARCHAR(64) NOT NULL
);
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
    "eJzdVl1vmzAU/SsoT5nUVSkhH9sbybI105JMLd2mVhVywCFWwKZg2kYV/32+BuJAEpZKk5"
    "buCTj3XHzvOfial0bAXOzH5zcxjhoftZcGRQEWNyX8TGugMFQoABzNfUlMCsY85hFyuMAW"
    "yI+xgFwcOxEJOWFUoDTxfQCZI4iEegpKKHlIsM2Zh/lS1nF3L2BCXfyM4+IxXNkLgn23VC"
    "ZxYW2J23wdSmxAvDHlnyUXFpzbDvOTgCp+uOZLRjcJhHJAPUxxhDiGFXiUQAdQYN5o0VRW"
    "rKJkVW7luHiBEp9vdXykDA6jIKGoJpY9erDK+w+63m739Fa72+8YvV6n3+oLrixpN9RLs4"
    "aVINmrpCzjL+OpBY0y4VNmHgCpzEEcZVlSbyWwE2GQxEZ8V+hPIsJJgPdLXc6sSO7mqefF"
    "TdWAQu46BwpAWaC+vL/kgejBnVF/ndtbI681noyuLXPyHToJ4vjBlxKZ1ggiukTXFbTZfV"
    "f2Y/MS7efYutTgUbudTUdSQRZzL5IrKp5124CaUMKZTdmTjdytL7FAC2EEUxkrrzuWDpco"
    "2m9nwa8YKdQ6UesC9Gz7mHp8KR67Ro11P8yr4aV51ewaFTumeUSXoTSFMbRYbe0TAObIWT"
    "2hyLV3Ikxnh7i7oUAPqgiiyJPaQIdQfz6UTRwRZ7lvXOeR2oGNFOdkRvZ/NK/1C6Nn9Ntd"
    "YzOmN0jddP7zJH7EUQwlvWLPbqW8zW2rdzpH7FvBOrhxZSwtTT7YGq8QMae/TQEvWq0jBB"
    "SsgwLKWFlAsSLHdM8Pwdfr2fTAz4BKqQh5Q0WDdy5x+Jnmk5jfn6asNSpC16VDvxCvOTF/"
    "VXUdfpsNqqc5vGDwr4+X9DfjR9MK"
)
