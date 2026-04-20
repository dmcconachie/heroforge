from enum import StrEnum


def combine(name: str, *sources: type[StrEnum]) -> type[StrEnum]:
    members: dict[str, str] = {}
    for src in sources:
        for m in src:
            members[m.name] = m.value
    return StrEnum(name, members)
