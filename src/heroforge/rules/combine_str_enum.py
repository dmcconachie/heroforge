from enum import StrEnum
from typing import cast


def combine(name: str, *sources: type[StrEnum]) -> type[StrEnum]:
    members: dict[str, str] = {}
    for src in sources:
        for m in src:
            members[m.name] = m.value
    # StrEnum's functional API builds a class, but its call
    # signature describes value lookup, so the cast is the
    # only way to say which of the two this is.
    return cast("type[StrEnum]", StrEnum(name, members))
