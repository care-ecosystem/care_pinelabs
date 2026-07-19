from django.utils import timezone


def generate_transaction_number(account, invoice=None):
    """
    Generate transaction number following the format:
    - With invoice: A{account_id}-{invoice_number}-{000+sequence}
    - Without invoice: A{account_id}-PAY{YYMMDD}-{000+sequence}

    Sequence is global counter (not date-based for invoice payments).

    Examples:
        With invoice:    A123-INV00456-001
        Without invoice: A123-PAY260718-001

    Args:
        account: Account instance
        invoice: Invoice instance (optional)

    Returns:
        str: Generated transaction number
    """
    from care_pinelabs.models.terminal_transaction import PinelabsTerminalTransaction

    account_prefix = f"A{account.id}"

    if invoice:
        # Format: A{account_id}-{invoice_number}-{sequence}
        # Remove '#' from invoice number (e.g., "#INV-134-26" -> "INV-134-26")
        invoice_number = str(invoice.number).replace("#", "")

        # Count ALL previous attempts for this account+invoice (global counter)
        sequence = (
            PinelabsTerminalTransaction.objects.filter(
                account=account, invoice=invoice
            ).count()
            + 1
        )

        # Zero-pad to 3 digits: 001, 002, etc.
        sequence_str = str(sequence).zfill(3)

        return f"{account_prefix}-{invoice_number}-{sequence_str}"

    else:
        # Format: A{account_id}-PAY{YYMMDD}-{sequence}
        now = timezone.now()
        date_str = now.strftime("%y%m%d")  # 260718

        # Count today's payments for this account
        sequence = (
            PinelabsTerminalTransaction.objects.filter(
                account=account,
                invoice__isnull=True,
                created_date__date=now.date(),
            ).count()
            + 1
        )

        # Zero-pad to 3 digits
        sequence_str = str(sequence).zfill(3)

        return f"{account_prefix}-PAY{date_str}-{sequence_str}"
