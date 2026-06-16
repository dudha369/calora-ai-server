from tortoise import fields
from tortoise.models import Model


class AppSettings(Model):
    """
    Key-value таблица для feature flags и настроек приложения.
    Управляется через админ-панель (PUT /api/admin/settings).

    Примеры ключей:
        whitelist_enabled  — "true" / "false"
        whitelist_ids      — "123,456,789"
        maintenance_mode   — "true" / "false"
        registration_open  — "true" / "false"
    """

    key = fields.CharField(max_length=64, pk=True)
    value = fields.TextField(default="")

    class Meta:
        table = "app_settings"

    # ── helpers ──────────────────────────────────────────────────

    @classmethod
    async def get_value(cls, key: str, default: str = "") -> str:
        row = await cls.get_or_none(pk=key)
        return row.value if row else default

    @classmethod
    async def get_bool(cls, key: str, default: bool = False) -> bool:
        val = await cls.get_value(key, str(default).lower())
        return val.lower() in ("true", "1", "yes")

    @classmethod
    async def set_value(cls, key: str, value: str) -> None:
        await cls.update_or_create({"value": value}, key=key)

    @classmethod
    async def get_all_dict(cls) -> dict[str, str]:
        rows = await cls.all()
        return {r.key: r.value for r in rows}
