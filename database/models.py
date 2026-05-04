from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import DateTime, Enum, ForeignKey, Index, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database.db import Base


class TransactionType(StrEnum):
    INCOME = "income"
    EXPENSE = "expense"


class DebtDirection(StrEnum):
    I_OWE = "i_owe"
    OWED_TO_ME = "owed_to_me"


class DebtStatus(StrEnum):
    ACTIVE = "active"
    PAID = "paid"


class BudgetPeriod(StrEnum):
    DAY = "day"
    MONTH = "month"
    CUSTOM = "custom"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=False)
    username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    first_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    transactions: Mapped[list["Transaction"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    budgets: Mapped[list["Budget"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    debts: Mapped[list["Debt"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    type: Mapped[TransactionType] = mapped_column(
        Enum(
            TransactionType,
            values_callable=lambda enum_class: [item.value for item in enum_class],
            native_enum=False,
        ),
        nullable=False,
    )
    category: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    user: Mapped[User] = relationship(back_populates="transactions")


class Budget(Base):
    __tablename__ = "budgets"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    limit_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    period_type: Mapped[BudgetPeriod] = mapped_column(
        Enum(
            BudgetPeriod,
            values_callable=lambda enum_class: [item.value for item in enum_class],
            native_enum=False,
        ),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    user: Mapped[User] = relationship(back_populates="budgets")


class Debt(Base):
    __tablename__ = "debts"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    person: Mapped[str] = mapped_column(String(255), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    direction: Mapped[DebtDirection] = mapped_column(
        Enum(
            DebtDirection,
            values_callable=lambda enum_class: [item.value for item in enum_class],
            native_enum=False,
        ),
        nullable=False,
    )
    status: Mapped[DebtStatus] = mapped_column(
        Enum(
            DebtStatus,
            values_callable=lambda enum_class: [item.value for item in enum_class],
            native_enum=False,
        ),
        default=DebtStatus.ACTIVE,
        nullable=False,
    )
    note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped[User] = relationship(back_populates="debts")


Index("ix_transactions_user_created_at", Transaction.user_id, Transaction.created_at.desc())
Index("ix_transactions_user_type_category", Transaction.user_id, Transaction.type, Transaction.category)
Index("ix_debts_user_status", Debt.user_id, Debt.status)
Index("ix_budgets_user_period", Budget.user_id, Budget.start_at, Budget.end_at)
