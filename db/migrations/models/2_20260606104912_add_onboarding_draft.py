from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS "onboarding_drafts" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "step" SMALLINT NOT NULL DEFAULT 0,
    "gender" VARCHAR(6),
    "age" SMALLINT,
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
    "user_id" BIGINT NOT NULL UNIQUE REFERENCES "users" ("telegram_id") ON DELETE CASCADE
);
COMMENT ON TABLE "onboarding_drafts" IS 'Черновик онбординга — хранит частично заполненные данные пока пользователь';"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP TABLE IF EXISTS "onboarding_drafts";"""


MODELS_STATE = (
    "eJztXY9zmzgW/ld0nrmxk00dg+3EyVxvJm3TbvbSppektze37XiwkR0mGFyM2+Zu+7+ffs"
    "ITAgK2k5iWzmzWCD0hfZIe0vveE/9rzHwbu4v2hwUOGsfofw3PmmHyQ0nfQw1rPo9TaUJo"
    "jVyWcUlysBRrtAgDaxySxInlLjBJsvFiHDjz0PE9mvXjstMzJvRvF7O/I/q3N2a/D0G6yf"
    "522F3+uw/zo2vs4mlgzdr0ubY/Jg92vOnDPOKjF4qfQ8dGH5dmx+ghlqkDxDraw2z2m6V0"
    "j9D1G3T2ag/Fd7p9ZC1D/5njjQM8w16IWlPs4cAKsf38NcUPxbUVNbTAQ3j6IXh4n+dEV6"
    "eXZyfnO6TiNME04gJEjQe8MN4IA5QzAM9SygQ5J7xaAmIUYymaqmEvmwt+8+cI4Z6WyQQp"
    "WODH+pW132D1MA5Y47rPWFEHyQ7sDhJY65XWgOXo8GaIdKWiEw3CEagirAJs5UT0g8GzGV"
    "rbTNCpk3zQTWQ5+2S6fXHGeLFvW457Nxy7/gK353cpddST4BP7IN2CKMFRwAW6UFjrNdJE"
    "Og2XnvN5iYehP8XhDVMmf3wiyY5n4294IS/nt8OJg11b0TVggtGSWIZheDdnN1840zMvfM"
    "2E6GwfDce+u5x5KYLzu/DG9yJJxwtpajStgGLylq4rFJhM4vUnCWGwxFHF7TjBxhNr6VL1"
    "RqU17SYTgTYSSWPfo5qRVGfBmj2lT3l2ZJrd7qHZ6R4M+r3Dw/6gQ8Zsg1VJv3X4nTc9ho"
    "YXxQA6e3P27pq21CfqlytlmvCdyVihxaVYF8SYT0jdhuxCQ/zljRWk460IJdAmTVwFbZkQ"
    "wx2/PDaE98z6NnSxNw1vyKVhdnKw/NfJ5ctfTy5bJNeOiug7ccvk9yi4MZj0HVgWSyizEp"
    "RiWD4Zkge9AkAe9DJxpLdUGF3Lmy6tKSYo2aWw1AQfb2w2gmVjU4gOCgA6yMRzkIRzvAwC"
    "srAYkgdi61bHM1Ot6oKb0axF8OysrVhNo3fYG3QPepE+jVLy1KhUmWAJTPqmNHaq0E+JG6"
    "n0IlwQTGZzF9NWFkcvTfSnxJBsCmjjhlaoo/eK3AmdGc6YvIpkAjxbiLbljy19ZZM22Bee"
    "eydecznQXZ+9Pb26Pnn7nrZktlh8dhlEJ9en9I7JUu8Sqa2DhBKNCkG/n13/iugl+s/Fu1"
    "OGoL8IpwF7Ypzv+j8NWie6gxt6/tehZYOFokyVwHynC9/JLViG0YSRNb79agX2ULkTj4Cv"
    "2JnehMMbZxH6wV3KuljIv/7HJXYthrDe32IX/zsr69e4qO3r8u9yHMvUuOvBotX37aHrTx"
    "frwfGaFHPuTysMxFdS5WADSPxOy6k2FPyVsR4M/6RlVBgDyxmGznxNEE6ca2deMRCoIvVN"
    "P0u1qrdivOaBP3HclC2GxOvCw9c++XM/atRA+j4ubuv2bIXGj++NfNJqUs7QDqxJypqjPD"
    "AXUZmvZJHVBIfb2aa+5W4Clle0tDeisOoAQqfVzJwlJtrM8siu2xbFUeGUWZHBKoBJk08u"
    "DMVsLUMyGMBKy+2WY820Ciy50sA6gEbjDjDAmpoR9QgYTgeKeRnYc8vSDhPUMo4NYZhHFK"
    "WdDIrjB2og5ClEIYfAxsyK6sNa6kSEavGGpIhm6+4N0g31UhiDG6BK4gk9IGAD23gHtd5f"
    "XF2jfWvu7MfadF9uZGUrjZTqDkClx1rlMisKaCBYUWmsz+qxCTp5f8ZZk772gF6cUWKmMz"
    "yH4HcKVwQfDDmGPui7Q9inKFKJFCSP6EQbB8dI/mvOLBc30Z+oOcHsJ8lC8jK9KnI1KQfC"
    "ssyoziL/sYsp/fHRI9rC+eKEd0MXf8HuMWousI1JruCO5XLp1ogLE/1DtTG7YFL8J/4WUo"
    "qOFMWX3VQB3bJHN+lWTzzYW1ou++n5Hs1rO5g+Y0i2jmTqjql6WhC12WTDAM6MbnLiitkD"
    "maZO3Elwwgr8cXMPNYFa4OUeIlA8JA3hw4UmIAW02+1PH70Ztp0xQZe8AWxH1BmJWosp2g"
    "GDB9ZUJTy16dIBI1UOFT5YINkmBo6s0JrEUhqflGl7KsohibfyFlBIa1qbsskhPgfLWOBj"
    "iWrSQgdFuIxsKiNpeierIh29K6K+3MzhJ0Qez9q5kSHYNQ8PotFHL/IG3tXbk/Nz3dZ5wy"
    "1d41lZyBTBnxA4YSK8nabYiPHYIdil46bIJS3EXLAtCthODHOgenX68oyg1ervGWy6Lj67"
    "TojhNO5p9G20niil8aBQNZWeUYgKz2HCNSTJioe8pYerDsw08bXH55Ptojc1PNUFbJkxqk"
    "tWdKCahXw2clw2kpiClXwZQBNij+hmQHcaG3M02PBqh6PCFOIsZXzmv8Q14ZVe5E/gDLO5"
    "93jaVlGH8beri3fpEGbJJ5D84JEbf5D9XbiHXGcRfnqwwfq3ydJj1UCjpeOGjrdo0wf+fY"
    "0BnIMqBUZhf+VQbb09+XdyFL88v3iRpHVpAS+SStd1cTC9G3p+mLIsuMbfspbxCbmKuHbl"
    "Meyn/77Ohzci2M8v3r2R2ZOYJ3xrNDtDmQGfLl0P99WHOzO0l3W/BUK1663qelvC5UPnMN"
    "Vu0ftEsk2sV85ICy1vnKZsEjEc29YbWWQTSQ6sr5E5Dw4z0jjSJMxXzC9Prl6evDptfM/h"
    "fEvyVknSMoW7SuE1s/mrJLFagsMyDzUTuh42AEM5VqYuYEwLfBx86AAY92HUiWKNHoC7Nq"
    "QhICNTJEAEmpL70JTcyc8Ey7ai1qXyIKUjglJ5uLqTtquTOMumx7wIugInQZZg6SSojusB"
    "b0qbSZhdrcGFQnhS+D+NW1PDdFAuscgoM3WbX2iM6DWzQFYLTVzfChlNyDnJHqSRxsnhJL"
    "puBIe71lFinKOW0Tb3kNHuHvbpoDYPdvZEt1naDNHpWziIO6BmOUFTGT0MRmCvm9U7vVxa"
    "OsHLArcG1i/cPr3PzVmwsyFNpwyk3L7jYyu7jfkuAFGQV2s827+dUtB3h+RdH0LVoiDQBz"
    "UDc5PrjhQWUfE0gFQjIKmVVmXGzEFtMgJJvZ7Wf3ZGZQSg64am1QziagziIsTzspYgKVMl"
    "h/9NmH8enW198sixSpOtlTY1PiHXWmnctoNq3Sq74KpMa1mStbJq7oHp1XW41Xo0NgoQq6"
    "/pJmhFZpVtoCoH4sWHF+en6P0lAfPqTJiZo+g5dlPF9vL05Lwms7beul+TWQ9KZj2hM8FT"
    "v+NqT4KtWqbWtOp2Kd6aVq1p1ZpWBUGPKYSqEhGZTaXGYZhlSFRgbhYm8/wD7+6htjKOqV"
    "OzAgZQmKo5YTIqGt239bWGwWz5QV4K35QZM6YzGhuJkwN8DOREtQp3D5WD9dgKgrwHx0vX"
    "Cv2gPb9jbA7rmV4GSoAeEyyOMQbt78V/FZZMhF8xos00kg3pmeyGAXkS+OgOahUYHJkY26"
    "C2kJLqZYROypGiB5kZA/535/ijR+PiXry9RM+R0dnVCjLQL+igbfZ3QbEYVM1Ez1AfigHm"
    "radPC5MU1xLVAmNPYoxowOAeemYcGNl5eFjhDq/5jGhgZ+46OFgcoyhQ8DmjLFmk4HNGXO"
    "4hGSxIrvvkkocLkotDk1yJiEFyecSLvX51ekoQobjsgmfwm2So+YGDFyQDy0cQ6JCupUGN"
    "O+hPntaSkY1Ryi+oS3PRIEdR93lAtmmON5ySggJ/6dmtFPh3kdEmr2VDyEyskOSn/6RMVJ"
    "td1GmT0bGPjuLsYysYLZiAzB7nfxZXYLdHrljRu0c7pIReXAJfpM9cWgLZSbRIq9Kr2e3u"
    "ECmCxA6juNkJFwpVOQaDB3LR0EXgAKRDXhkGQKdQix2gajoKn4ne4JnjOXzipZytKahxxN"
    "5TkaIEFDVUV0qEdiEyW3Ng6NpIr/cmyOx9kDX30NLsCGXdCwNWXPC6NUH7NAStnLZlN9lQ"
    "7icMuYtUXEnruyJXh9w12MuhJIaRTI1fQ7yISyIIpGoMG3IpspqdcQ0TY7VVIF+KlaIRIo"
    "mK2Lgfm0CozYS1mbA2EyaOKU0xFWrnmGabC/XjUwseHTaA5gWwd0k5TcsEGym4fR2k70aV"
    "PdJRlo8rdwhWbB1w26R7zCv7TygMjXHi6J6M08R+7DaLTbge3wCbPYZ1g9teaAwr5OIPBB"
    "T/5zFonR6KAS1T+qFrqiV01V155Iwmvcahw3q9D3+Sffh2OBZWfzEf4LEf2CudmJ4QrY9M"
    "34Ij07dvdfxoe7SnWB/ft+Z97QdE33j/wHcPvOp9NL2z4XXvPXuKza2R5dn1KatjcKx99r"
    "pYOUK/4JIYsg6QNEwJGU1ZUoEwst5ogwfJgkWQcuBlL5k5O8IsszFg9aZQK5ZOi4jmsRuC"
    "voGsk511gm8N6lqgUlKQDOMhfSsjhRcElJbkwSFAWd4Tsg0t+srbUeIq4Xf+YJis9rlHud"
    "KHsZ7Qz0B3W9jcycptzq/Kf2yMZThoFDtZGXxtsqsdmqzubNrAC0DsYXJbdB/NmbJD1GaF"
    "7jwQf6GwAfBXClaarxSsD3Nb1LrRZiNtyhaIcqR9uH4JoqP1I7glSiV518zWQh1ABk2LLp"
    "h2BOwpcbLayQJ63LQyqpQdJ3QR6oIuUvag6gcgpX+MqEvKtMNaJeETxOwWbknHGzsPQE5j"
    "s3vcH4DgahjJrB5cXUj7yiGWEsitqfXe5GNDBrh3oIbsy3F6n45sKHDQoaecBqHMR+gNAA"
    "0z6hHdkeLkjSg+35kxxZvf+GS5vgzcaDZcngMnCjX2WyL20vWX9sS1AowuTbSP6KcTRq71"
    "X4xemPp7R9EiI62TVf+1q+5OQvu9+3B+nu3xA7oo19KjaGrlW7fAWQMepSFScJafVBo+DN"
    "HQDy13uAs7eg23OnjOt/YF2bmzT9eA6idjFTWquAXC992BBpxy2HxJBz1SJ7piPQvxrKDx"
    "6Q+4KJdjuPGptklt2CYVQZtqSEmHD8rkWVC2elOYaowiy8Hkd0rlaqCspUkRrO1MW2Znil"
    "5rZbhtRaimt1Ppbf52W9XjTJf+2Q4I4Qis6nqWIv00fMEaYBYgCw5KkAUcklV80BKSNZB8"
    "bq7ijKbJ/uxg1jzHXs1zVInnADstsonbwEd56V6wWmiW+wLpClwPgySD7JFw3cP2RJ1Thu"
    "4R5gnN7p9i7lbCwuBn6YSlYD+2Myimx15sMhHHMJrFDJCC6MojVqpQfWEyFbFzWlATPB5R"
    "Fg3ilvgHGqVdVzEsAlsOPFITAmBBw01K01OoHJ2wgmxHhukvpmXyDUl9/dTIIn13VMhoyx"
    "umRq1mGrzK2gWFLQtSVdqpsBlkmWkcFf9c4j2RtEdIsSGa0BCccuxtOrYpg2aszLbaQezR"
    "jXFMhbMLDb7so2UUoWp+88fsFDk+jeTKPF2G3UuEb/kBrVX58C0o94N625XZqtTRg3X04I"
    "aHXx09WEcPVglD6UiXarHJVIAJqYrpwLUWOTnGGInKBgwywAly+2AsapNJjJJt8j/9nQa/"
    "ZjigRvf2ciOzWPhsYRfUbHBrh4Ft2aPUDgO1w8BP6DBgzfylF65wgoAiWLE1wCb2QTXTtV"
    "czXVViuh5yRfXPJV6kfmmQ38hdS32mWcpwOxYwHEMTs6k5g64ch8Cd0jdx5Jk4aw3IKQec"
    "mRrpkcIZ4AyW6CcEInLSh6E0h5qofpgoZ1mUw/SEszg775GffSj5DNv3MEKoNV4GASYvuS"
    "+Wu8To78+R+AAFu96RualWafNRPJTftLPRL8+RoZc8sRyX3Gzhb3OHvMR5NEaC62G49QWN"
    "wU4OZIUPb/GdwkbBkJ6u1q5VjxpIYc34fRsUrn+lrM9gbEZWPt9ym0i2+hejWJwKOEhB3p"
    "YHMlL0o1N229Fj2EPJtMDWbTMOG2IPfc47RvYhz8Qryfwdybq0CfMnKyl24TK+IA4Y+Mtz"
    "pv5YUTd3dsCcAnKLKtNeMC0h59VRAZDnN7FKCIv0WqBDZTEB0/OeIB82bTsjw+j8VWE/QV"
    "Whvbzkdpe8z8Plot7sbnyzGymUMoScIlRNQq5XhI/rZdNxKd6DTuiWojUjgWoiaBSiNI0c"
    "StPQKU1YMw3KbL/1hFhVAH1s13VnnAZr9giV+auCpzpABwWG5yBzcA4yPlfGVnxlnYMToj"
    "8o4TQoQ9rBBXVZ6i4p+yP6WpcBU6yOSszsWOLx5jb/zBzrsC39ImG8Fytr2lYlq2nbrogt"
    "WzY715gd7b5X6Muk7AZ6c7ui4qrWmbWBfa82sNcGdg7siXPtzBspBnZ+Yy/PwM6Pri5jYe"
    "f2IfjJniIfYTrSD4qBtmlTNRAV/AgJrbk8JCbzyyH3PNK8x/alGDs3YTVPN9fXqK57ONTI"
    "WpD3M52X/OCXTR2YtaeeTsP+BwIIUs4ThqEbAqjCJIne3HsR5wesOHOmb49Rc2aNA384sl"
    "yqjpvoT8UQTa78LzjA5NKbkkt4rExzSTRsfEvazodzohMXvCTmuPV5aZENyF0zw2irWGmV"
    "XuHG2jqY4uFst2wY4G8pC9xsSxmUqYpZ59FPeBDTq5wxN5apCq7JEJVCESo5ASrJ7XRtbl"
    "zD3Kjq0tQtbDqKmuCP7o9Ybw/r7WG9PZS7QBw445vU/SG/k79BjPM8pCd7vRLc8EqQLPIX"
    "qZRp9ssWiFTzfWv2+0UWLP1+9oqF3kt8Dmye8i2wbBBF9moC+CAEPnliiL2ULclvVxfvsu"
    "ztkUgCyA8eaeAftjMO6feKF+Gn7YQ1B0Xa6vz9SXIrsqfaz2kBL9b9CNi6r5fv/wd8nJyv"
)
