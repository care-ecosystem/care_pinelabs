# Manual migration to ensure fresh deployment compatibility
#
# Context: In fresh deployments, migrations may fail because:
# 1. Migration 0001 creates PinelabsPosTerminal but the table may not exist when 0002 runs
# 2. Migration 0002 creates PinelabsTransaction and references PinelabsPosTerminal
#
# This migration ensures all required tables exist for forward compatibility.
# For existing deployments that already applied 0001-0004, this is a no-op.
# For fresh deployments, this ensures all tables exist before use.

from django.db import migrations


def ensure_all_tables_exist(apps, schema_editor):
    """
    Ensure all care_pinelabs tables exist.

    For fresh deployments where migration optimization may skip table creation,
    this ensures the final state matches what the models expect.
    """
    with schema_editor.connection.cursor() as cursor:
        # Check and create PinelabsPosTerminal table if missing
        cursor.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_schema = 'public'
                AND table_name = 'care_pinelabs_pinelabsposterminal'
            );
        """)
        if not cursor.fetchone()[0]:
            # Table doesn't exist, create it
            PinelabsPosTerminal = apps.get_model('care_pinelabs', 'PinelabsPosTerminal')
            try:
                schema_editor.create_model(PinelabsPosTerminal)
            except Exception:
                # Table might have been created by another process
                pass

        # Check and create PinelabsTransaction table if missing
        cursor.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_schema = 'public'
                AND table_name = 'care_pinelabs_pinelabstransaction'
            );
        """)
        if not cursor.fetchone()[0]:
            # Table doesn't exist, create it
            PinelabsTransaction = apps.get_model('care_pinelabs', 'PinelabsTransaction')
            try:
                schema_editor.create_model(PinelabsTransaction)
            except Exception:
                # Table might have been created by another process
                pass

        # Check and create PinelabsConfig table if missing
        cursor.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_schema = 'public'
                AND table_name = 'care_pinelabs_pinelabsconfig'
            );
        """)
        if not cursor.fetchone()[0]:
            PinelabsConfig = apps.get_model('care_pinelabs', 'PinelabsConfig')
            try:
                schema_editor.create_model(PinelabsConfig)
            except Exception:
                pass

        # Check and create PinelabsPaymentMethodMapping table if missing
        cursor.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_schema = 'public'
                AND table_name = 'care_pinelabs_pinelabspaymentmethodmapping'
            );
        """)
        if not cursor.fetchone()[0]:
            PinelabsPaymentMethodMapping = apps.get_model('care_pinelabs', 'PinelabsPaymentMethodMapping')
            try:
                schema_editor.create_model(PinelabsPaymentMethodMapping)
            except Exception:
                pass


class Migration(migrations.Migration):

    dependencies = [
        ('care_pinelabs', '0004_alter_pinelabspaymentmethodmapping_pinelabs_method_and_more'),
    ]

    operations = [
        migrations.RunPython(
            ensure_all_tables_exist,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
