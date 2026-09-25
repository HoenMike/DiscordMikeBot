"""Current product identity and names accepted for existing user input."""

BOT_BRAND_NAME = "Asumi"
LEGACY_BOT_ALIASES = frozenset({"mikedabot", "mikebot", "mike bot", "mikesbot", "mike_bot"})


def runtime_bot_name(bot_user) -> str:
    return (getattr(bot_user, "display_name", None) or getattr(bot_user, "name", None) or BOT_BRAND_NAME)
