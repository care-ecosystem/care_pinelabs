from care.security.authorization import AuthorizationController
from care.security.authorization.base import AuthorizationHandler

from care_pinelabs.security.PinelabsPermissions import PinelabsPermissions


class PinelabsAccess(AuthorizationHandler):
    def can_manage_pinelabs_config(self, user, facility):
        return self.check_permission_in_facility_organization(
            [PinelabsPermissions.can_manage_pinelabs_config.name],
            user,
            facility=facility,
        )

    def can_perform_pinelabs_transaction(self, user, facility):
        return self.check_permission_in_facility_organization(
            [PinelabsPermissions.can_perform_pinelabs_transaction.name],
            user,
            facility=facility,
        )

    def can_read_pinelabs_transaction(self, user, facility):
        return self.check_permission_in_facility_organization(
            [PinelabsPermissions.can_read_pinelabs_transaction.name],
            user,
            facility=facility,
        )


AuthorizationController.register_internal_controller(PinelabsAccess)
