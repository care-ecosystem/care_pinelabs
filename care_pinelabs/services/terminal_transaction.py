from django.db import IntegrityError, transaction
from rest_framework.exceptions import ValidationError

from care_pinelabs.models.terminal_transaction import (
    PinelabsTerminalTransaction,
    TerminalTransactionStatus,
)


def acquire_terminal_lock(
    terminal,
    account,
    transaction_number: str,
    payment_mode: str,
    invoice=None,
):
    """
    Acquire exclusive lock on terminal for transaction.

    Creates terminal transaction with "started" status.

    This enforces:
    1. One active transaction per terminal
    2. One active payment per invoice (if invoice provided)
    3. One active payment per account (if no invoice)
    4. Unique transaction number (idempotency)

    Args:
        terminal: PinelabsTerminal instance
        account: Account instance
        transaction_number: Generated transaction number
        payment_mode: Payment mode (1=Card, 10=UPI, 11=Bharat QR)
        invoice: Invoice instance (optional)

    Returns:
        PinelabsTerminalTransaction instance with status="started"

    Raises:
        ValidationError: If any constraint violated (terminal busy, invoice busy, etc.)

    Note:
        created_by will be set automatically by BaseModel from request context
    """
    try:
        with transaction.atomic():
            # Create lock record with "started" status
            # This will fail with IntegrityError if any constraint violated
            lock = PinelabsTerminalTransaction.objects.create(
                terminal=terminal,
                account=account,
                invoice=invoice,
                transaction_number=transaction_number,
                payment_mode=payment_mode,
                status=TerminalTransactionStatus.STARTED,  # Device blocked
            )
            return lock

    except IntegrityError as e:
        error_str = str(e).lower()

        # Constraint 1: Terminal already has active transaction
        if "unique_active_transaction_per_terminal" in error_str:
            blocking = PinelabsTerminalTransaction.objects.filter(
                terminal=terminal,
                status__in=[
                    TerminalTransactionStatus.STARTED,
                    TerminalTransactionStatus.IN_PROGRESS,
                ],
            ).first()

            if blocking:
                raise ValidationError(
                    f"Terminal {terminal.name} is busy with transaction {blocking.transaction_number}. "
                    f"Started {blocking.created_date.strftime('%Y-%m-%d %H:%M:%S')}. "
                    f"Please wait for completion or cancel the existing transaction."
                )
            else:
                raise ValidationError(
                    f"Terminal {terminal.name} is currently busy. Please try again."
                )

        # Constraint 2: Invoice already has active payment
        elif "unique_active_payment_per_invoice" in error_str:
            if invoice:
                blocking = PinelabsTerminalTransaction.objects.filter(
                    invoice=invoice,
                    status__in=[
                        TerminalTransactionStatus.STARTED,
                        TerminalTransactionStatus.IN_PROGRESS,
                    ],
                ).first()

                if blocking:
                    raise ValidationError(
                        f"Invoice {invoice.number} already has an active payment in progress "
                        f"(transaction {blocking.transaction_number} on terminal {blocking.terminal.name}). "
                        f"Please wait for it to complete or cancel it first."
                    )
                else:
                    raise ValidationError(
                        f"Invoice {invoice.number} already has an active payment in progress."
                    )
            else:
                raise ValidationError(
                    "Invoice already has an active payment in progress."
                )

        # Constraint 3: Account already has active payment (when no invoice)
        elif "unique_active_payment_per_account" in error_str:
            blocking = PinelabsTerminalTransaction.objects.filter(
                account=account,
                invoice__isnull=True,
                status__in=[
                    TerminalTransactionStatus.STARTED,
                    TerminalTransactionStatus.IN_PROGRESS,
                ],
            ).first()

            if blocking:
                raise ValidationError(
                    f"Account {account.id} already has an active payment in progress "
                    f"(transaction {blocking.transaction_number} on terminal {blocking.terminal.name}). "
                    f"Please wait for it to complete or cancel it first."
                )
            else:
                raise ValidationError(
                    f"Account {account.id} already has an active payment in progress."
                )

        # Constraint 4: Transaction number already exists (idempotency)
        elif "unique_transaction_number" in error_str:
            existing = PinelabsTerminalTransaction.objects.get(
                transaction_number=transaction_number
            )
            raise ValidationError(
                f"Transaction {transaction_number} already exists with status {existing.status}. "
                f"This may be a duplicate request."
            )

        # Unknown integrity error
        raise


def get_active_terminal_transaction(terminal):
    """
    Get active transaction for terminal, if any.

    Args:
        terminal: PinelabsTerminal instance

    Returns:
        PinelabsTerminalTransaction or None
    """
    return PinelabsTerminalTransaction.objects.filter(
        terminal=terminal,
        status__in=[
            TerminalTransactionStatus.STARTED,
            TerminalTransactionStatus.IN_PROGRESS,
        ],
    ).first()
