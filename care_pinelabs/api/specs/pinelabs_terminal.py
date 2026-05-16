from datetime import datetime

from pydantic import UUID4, BaseModel, Field

from care_pinelabs.models.pinelabs_terminal import PinelabsTerminal


class PinelabsTerminalWriteSpec(BaseModel):
    facility_id: UUID4
    name: str = Field(max_length=255, min_length=1)
    client_id: str = Field(max_length=255, min_length=1)
    store_id: str = Field(max_length=255, min_length=1)
    is_active: bool = True


class PinelabsTerminalUpdateSpec(BaseModel):
    facility_id: UUID4 | None = None
    name: str | None = Field(default=None, max_length=255, min_length=1)
    client_id: str | None = Field(default=None, max_length=255, min_length=1)
    store_id: str | None = Field(default=None, max_length=255, min_length=1)
    is_active: bool | None = None


class PinelabsTerminalReadSpec(BaseModel):
    id: UUID4
    facility_id: UUID4
    name: str
    client_id: str
    store_id: str
    is_active: bool
    created_date: datetime | None
    modified_date: datetime | None

    @classmethod
    def from_instance(cls, instance: PinelabsTerminal) -> "PinelabsTerminalReadSpec":
        return cls(
            id=instance.external_id,
            facility_id=instance.facility.external_id,
            name=instance.name,
            client_id=instance.client_id,
            store_id=instance.store_id,
            is_active=instance.is_active,
            created_date=instance.created_date,
            modified_date=instance.modified_date,
        )
