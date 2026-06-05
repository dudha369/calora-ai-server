import os
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from bot.handlers import setup_routers as setup_bot_routers
from api import setup_routers as setup_api_routers
from config_reader import config, dp, app

ALLOWED_ORIGINS = [
    config.WEBAPP_URL.get_secret_value(),
]

if os.getenv("ENV", "production") == "development":
    ALLOWED_ORIGINS += [
        "http://localhost:5173",
        "http://localhost:3000",
        "http://127.0.0.1:5173",
    ]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

dp.include_router(setup_bot_routers())
app.include_router(setup_api_routers())

if __name__ == "__main__":
    port = int(os.environ.get("PORT", config.APP_PORT))
    host = config.APP_HOST

    uvicorn.run(app, host=host, port=port)
