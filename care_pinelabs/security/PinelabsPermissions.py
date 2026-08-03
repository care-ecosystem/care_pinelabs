import enum

from care.security.permissions.constants import Permission, PermissionContext
from care.security.roles.role import ADMIN_ROLE, FACILITY_ADMIN_ROLE


class PinelabsPermissions(enum.Enum):
    can_manage_pinelabs_config = Permission(
        "Can Manage Pinelabs Config In Facility",
        "",
        PermissionContext.FACILITY,
        [FACILITY_ADMIN_ROLE, ADMIN_ROLE],
    )
