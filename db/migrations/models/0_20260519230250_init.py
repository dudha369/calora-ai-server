from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS "user" (
    "id" BIGSERIAL NOT NULL PRIMARY KEY,
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "name" VARCHAR(64) NOT NULL UNIQUE
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
    "eJzdVu9zmkAQ/VcYP9mZNGMQf7Tf0NrGTtVOQtpOMhnmhBNvhDsCRxMnw//e2wM8QaWmk7"
    "ZpPwlv33K777kLj42AudiPT69iHDXeao8NigIsLkr4idZAYahQADia+5KYFIx5zCPkcIEt"
    "kB9jAbk4diIScsKoQGni+wAyRxAJ9RSUUHKXYJszD/OlrOPmVsCEuvgBx8VtuLIXBPtuqU"
    "ziwtkSt/k6lNiAeGPK30suHDi3HeYnAVX8cM2XjG4SCOWAepjiCHEMJ/AogQ6gwLzRoqms"
    "WEXJqtzKcfECJT7f6vhIGRxGQUJRTSx79OCU1290vd3u6a12t98xer1Ov9UXXFnSbqiXZg"
    "0rQbJHSVnGH8ZTCxplwqfMPABSmYM4yrKk3kpgJ8IgiY34rtDvRISTAO+XupxZkdzNU0+L"
    "i6oBhdx1DhSAskD9857JA9GDO6P+Ore3Rl5rPBldWubkM3QSxPGdLyUyrRFEdImuK2iz+6"
    "rsx+Yh2texda7BrXY9m46kgizmXiRPVDzrugE1oYQzm7J7G7lb/8QCLYQRTGWs/N2xdLhE"
    "0X47C37FSKHWr1j324cnQA+2j6nHl+K2a9QY98W8GJ6bF82uUTFjmkd0GUpTWEKL1daUAD"
    "BHzuoeRa69E2E6O8TdDQV6UEUQRZ6UBjqE+vOVbOKIOMt9yzqP1K5rpDgvZmH/R9taPzN6"
    "Rr/dNTZLeoPU7eaf7+HvOIqhpCdM7FbK8wztH9i3pbHVO50j5lawDg6ujKWlvQej8QQRc/"
    "q/KeBZq3WEgIJ1UEAZKwsoTuSY7vkc+Hg5mx74FFApFSGvqGjwxiUOP9F8EvPblylrjYrQ"
    "demVX4jXnJjfqroOP80G1Xc5PGDwt18v6Q+en9J0"
)
