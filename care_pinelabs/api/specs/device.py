from pydantic import BaseModel


class PinelabsDeviceMetadataWriteSpec(BaseModel):
    store_id: str
    client_id: str



class PinelabsDeviceMetadataReadSpec(BaseModel):
    store_id: str
    client_id: str
