from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class PoolRule:
    """
    A rule that can match a pool code (e.g. 7103, 7700, 5500, 5700, 3100, 3500).
    If direct_host is set, we can return it; otherwise we return default_host.
    """
    default_host: str
    direct_host: Optional[str] = None
    path_prefix: str = ""  # e.g. "/v3"


# ---- Rules derived from documentation https://wiki.yandex.ru/b/biznes-processyh/texnicheskajapod/kurs-podgotovki-specialista-texnicheskojj-podderzh/oznakomlenie-s-texnicheskojj-chastju-servisa/----
# Notes:
# - "includes all XXYY" means match prefix.
# - For pools where no direct host was stated, we return default_host.
# - For /v3 pools, we insert the path into the returned base URL.

RULES_EXACT: dict[int, PoolRule] = {
    1101: PoolRule(default_host="https://api.green-api.com"),
    1102: PoolRule(default_host="https://api.green-api.com"),
    1103: PoolRule(default_host="https://api.greenapi.com", direct_host="https://1103.api.green-api.com"),
    2204: PoolRule(default_host="https://api.greenapi.com"),
    7103: PoolRule(default_host="https://api.greenapi.com", direct_host="https://7103.api.greenapi.com"),
    9903: PoolRule(default_host="https://api.p03.green-api.com", direct_host="https://9903.api.green-api.com"),
    9906: PoolRule(default_host="https://api.green-api.com", direct_host="https://9906.api.green-api.com"),
}

# Prefix rules (includes all XXYY)
# We interpret "55XX" as any pool where first two digits are 55, etc.
RULES_PREFIX: list[tuple[str, PoolRule]] = [
    ("99", PoolRule(default_host="https://api.p03.green-api.com")),  # 99XX
    ("33", PoolRule(default_host="https://api.green-api.com")),     # 33XX
    ("55", PoolRule(default_host="https://api.green-api.com")),     # 55XX
    ("57", PoolRule(default_host="https://api.green-api.com", direct_host="https://5700.api.green-api.com")),  # 57XX
    ("77", PoolRule(default_host="https://api.greenapi.com", direct_host="https://7700.api.greenapi.com")),    # 77XX
    ("31", PoolRule(default_host="https://api.green-api.com", direct_host="https://3100.api.green-api.com", path_prefix="/v3")),  # 31XX
    ("35", PoolRule(default_host="https://api.green-api.com", direct_host="https://3500.api.green-api.com", path_prefix="/v3")),  # 35XX
]


def pool_from_instance_id(id_instance: str) -> int:
    """
    Extract the pool code from an idInstance like 7107348018 -> 7107
    """
    s = str(id_instance).strip()
    if len(s) < 4 or not s[:4].isdigit():
        raise ValueError(f"Invalid idInstance '{id_instance}'. Expected at least 4 leading digits.")
    return int(s[:4])


def resolve_api_url(id_instance: str, prefer_direct: bool = True) -> str:
    """
    Resolve best API base URL for this instance.
    Returns base like:
      https://7103.api.greenapi.com
      https://api.greenapi.com
      https://api.green-api.com/v3
      https://3100.api.green-api.com/v3
    """
    pool = pool_from_instance_id(id_instance)
    pool_str = f"{pool:04d}"

    # 1) Exact match first
    rule = RULES_EXACT.get(pool)

    # 2) If no exact rule, try prefix rules (e.g. 55XX, 77XX, 31XX, 99XX)
    if rule is None:
        for prefix, pr in RULES_PREFIX:
            if pool_str.startswith(prefix):
                rule = pr
                break

    # 3) If still unknown, fall back to the most common default from docs
    if rule is None:
        rule = PoolRule(default_host="https://api.greenapi.com")

    # Choose host
    host = rule.direct_host if (prefer_direct and rule.direct_host) else rule.default_host

    # Apply /v3 if needed
    if rule.path_prefix and not host.endswith(rule.path_prefix):
        host = host.rstrip("/") + rule.path_prefix

    return host
