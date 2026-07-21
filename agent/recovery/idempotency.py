from __future__ import annotations

import hashlib
import secrets


class IdempotencyKeyGenerator:
    prefix = "idem"

    def generate(
        self,
        *,
        run_id: str,
        tool_name: str,
        action: str,
        input_summary: str,
        deterministic: bool = True,
    ) -> str:
        seed = "|".join([run_id, tool_name, action, input_summary])
        digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:24]
        suffix = digest if deterministic else f"{digest}-{secrets.token_hex(4)}"
        return f"{self.prefix}-{suffix}"

    def validate(self, key: str) -> bool:
        if not key.startswith(f"{self.prefix}-"):
            return False
        suffix = key.removeprefix(f"{self.prefix}-")
        parts = suffix.split("-")
        return all(parts) and all(_is_hex(part) for part in parts)


def _is_hex(value: str) -> bool:
    try:
        int(value, 16)
    except ValueError:
        return False
    return True
