"""Konstanta tenancy."""

# Slug terreserve untuk vanity subdomain/host (Spec §18.2)
RESERVED_SLUGS = frozenset(
    {
        "www", "app", "admin", "api", "mail", "help", "status", "staging",
        "dev", "static", "assets", "support",
    }
)
