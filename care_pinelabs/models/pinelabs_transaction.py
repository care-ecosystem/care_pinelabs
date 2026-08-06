from django.db import models

from care.utils.models.base import BaseModel


class PinelabsTransactionStatus(models.TextChoices):
    """
    Transaction status lifecycle:
    started → in_progress → completed
    """

    STARTED = "started", "Started"  # Device blocked, calling Pine Labs
    IN_PROGRESS = "in_progress", "In Progress"  # Upload succeeded, waiting for customer
    COMPLETED = "completed", "Completed"  # Payment successful


class PinelabsTransaction(BaseModel):
    """
    Terminal transaction lock table.

    Enforces:
    1. One active transaction per terminal
    2. One active payment per invoice (when invoice provided)
    3. One active payment per account (when NO invoice)
    4. Unique transaction numbers (idempotency)

    Status lifecycle:
    - started: Device blocked, payment created, calling Pine Labs
    - in_progress: Upload succeeded, waiting for customer payment
    - completed: Payment successful

    Note: Inherits audit fields from BaseModel:
    - id, external_id
    - created_date, modified_date (replaces initiated_at, uploaded_at)
    - created_by, updated_by (replaces initiated_by)
    - deleted (soft delete support)
    """

    # Core relationships
    terminal = models.ForeignKey(
        "care_pinelabs.PinelabsPosTerminal",
        on_delete=models.PROTECT,
        related_name="transactions",
        db_index=True,
        help_text="Terminal processing this transaction",
    )

    account = models.ForeignKey(
        "emr.Account",
        on_delete=models.PROTECT,
        related_name="terminal_transactions",
        db_index=True,
        help_text="Account being charged",
    )

    payment_reconciliation = models.OneToOneField(
        "emr.PaymentReconciliation",
        on_delete=models.PROTECT,
        related_name="terminal_transaction",
        null=True,
        blank=True,
        db_index=True,
        help_text="Linked payment reconciliation record",
    )

    invoice = models.ForeignKey(
        "emr.Invoice",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="terminal_transactions",
        help_text="Optional invoice being paid",
    )

    # Transaction identifiers
    transaction_number = models.CharField(
        max_length=100,
        unique=True,
        db_index=True,
        help_text="Unique transaction number (format: A{account_id}-{invoice}-{seq})",
    )

    plutus_transaction_reference_id = models.CharField(
        max_length=100,
        null=True,
        blank=True,
        db_index=True,
        help_text="PTRID returned by Pine Labs",
    )

    # Status tracking
    status = models.CharField(
        max_length=20,
        choices=PinelabsTransactionStatus.choices,
        default=PinelabsTransactionStatus.STARTED,
        db_index=True,
        help_text="Current transaction status",
    )

    # Payment metadata
    payment_mode = models.CharField(
        max_length=10, help_text="Payment mode: 1=Card, 10=UPI, 11=Bharat QR"
    )

    class Meta:
        ordering = ["-created_date"]  # From BaseModel

        indexes = [
            models.Index(fields=["terminal", "status"]),
            models.Index(fields=["account", "status"]),
            models.Index(fields=["invoice", "status"]),
            models.Index(fields=["status", "created_date"]),  # Using BaseModel field
            models.Index(fields=["payment_reconciliation"]),
            models.Index(fields=["plutus_transaction_reference_id"]),
        ]

        constraints = [
            # CONSTRAINT 1: One active transaction per terminal
            models.UniqueConstraint(
                fields=["terminal"],
                condition=models.Q(
                    status__in=[
                        PinelabsTransactionStatus.STARTED,
                        PinelabsTransactionStatus.IN_PROGRESS,
                    ]
                ),
                name="unique_active_transaction_per_terminal",
                violation_error_message="Terminal already has an active transaction",
            ),
            # CONSTRAINT 2: One active payment per invoice (when invoice provided)
            models.UniqueConstraint(
                fields=["invoice"],
                condition=models.Q(
                    status__in=[
                        PinelabsTransactionStatus.STARTED,
                        PinelabsTransactionStatus.IN_PROGRESS,
                    ],
                    invoice__isnull=False,
                ),
                name="unique_active_payment_per_invoice",
                violation_error_message="Invoice already has an active payment in progress",
            ),
            # CONSTRAINT 3: One active payment per account (when NO invoice)
            models.UniqueConstraint(
                fields=["account"],
                condition=models.Q(
                    status__in=[
                        PinelabsTransactionStatus.STARTED,
                        PinelabsTransactionStatus.IN_PROGRESS,
                    ],
                    invoice__isnull=True,
                ),
                name="unique_active_payment_per_account",
                violation_error_message="Account already has an active payment in progress",
            ),
            # CONSTRAINT 4: Unique transaction number (idempotency)
            models.UniqueConstraint(
                fields=["transaction_number"],
                name="unique_transaction_number",
                violation_error_message="Transaction number already exists",
            ),
        ]

    def __str__(self):
        return f"{self.transaction_number} - {self.status}"

    # Helper methods

    def mark_uploaded(self, plutus_reference_id: str):
        """Mark as uploaded to Pine Labs and transition to in_progress."""
        self.plutus_transaction_reference_id = plutus_reference_id
        self.status = PinelabsTransactionStatus.IN_PROGRESS
        self.save(
            update_fields=[
                "plutus_transaction_reference_id",
                "status",
                "modified_date",
            ]
        )

    def mark_completed(self):
        """Mark transaction as successfully completed."""
        self.status = PinelabsTransactionStatus.COMPLETED
        self.save(update_fields=["status", "modified_date"])

    def is_active(self) -> bool:
        """Check if transaction is active (started or in_progress)."""
        return self.status in [
            PinelabsTransactionStatus.STARTED,
            PinelabsTransactionStatus.IN_PROGRESS,
        ]
