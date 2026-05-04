from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta
from decimal import Decimal

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import Budget, BudgetPeriod, Debt, DebtDirection, DebtStatus, Transaction, TransactionType, User


@dataclass(frozen=True)
class SummaryDTO:
    total_income: Decimal
    total_expense: Decimal


@dataclass(frozen=True)
class CategoryTotalDTO:
    category: str
    total: Decimal


@dataclass(frozen=True)
class WeekRangeDTO:
    start_at: datetime
    end_at: datetime


async def create_user_if_not_exists(
    session: AsyncSession,
    telegram_id: int,
    username: str | None = None,
    first_name: str | None = None,
) -> User:
    user = await session.get(User, telegram_id)
    if user is None:
        user = User(id=telegram_id, username=username, first_name=first_name)
        session.add(user)
        await session.flush()
        return user

    changed = False
    if username and user.username != username:
        user.username = username
        changed = True
    if first_name and user.first_name != first_name:
        user.first_name = first_name
        changed = True
    if changed:
        await session.flush()
    return user


async def create_transaction(
    session: AsyncSession,
    user_id: int,
    amount: Decimal,
    transaction_type: str,
    category: str,
) -> Transaction:
    transaction = Transaction(
        user_id=user_id,
        amount=amount,
        type=TransactionType(transaction_type),
        category=category,
    )
    session.add(transaction)
    await session.flush()
    return transaction


def get_current_week_range(now: datetime | None = None) -> WeekRangeDTO:
    now = now or datetime.now()
    week_start_date = now.date() - timedelta(days=now.weekday())
    start_at = datetime.combine(week_start_date, time.min)
    end_at = start_at + timedelta(days=7)
    return WeekRangeDTO(start_at=start_at, end_at=end_at)


async def get_user_summary(session: AsyncSession, user_id: int) -> SummaryDTO:
    income_query = select(func.coalesce(func.sum(Transaction.amount), 0)).where(
        Transaction.user_id == user_id,
        Transaction.type == TransactionType.INCOME,
    )
    expense_query = select(func.coalesce(func.sum(Transaction.amount), 0)).where(
        Transaction.user_id == user_id,
        Transaction.type == TransactionType.EXPENSE,
    )
    total_income = await session.scalar(income_query)
    total_expense = await session.scalar(expense_query)
    return SummaryDTO(
        total_income=Decimal(total_income or 0),
        total_expense=Decimal(total_expense or 0),
    )


async def get_top_expense_categories(
    session: AsyncSession,
    user_id: int,
    limit: int = 5,
    start_at: datetime | None = None,
    end_at: datetime | None = None,
) -> list[CategoryTotalDTO]:
    query = (
        select(Transaction.category, func.sum(Transaction.amount).label("total"))
        .where(Transaction.user_id == user_id, Transaction.type == TransactionType.EXPENSE)
        .group_by(Transaction.category)
        .order_by(func.sum(Transaction.amount).desc())
        .limit(limit)
    )
    if start_at is not None:
        query = query.where(Transaction.created_at >= start_at)
    if end_at is not None:
        query = query.where(Transaction.created_at < end_at)

    result = await session.execute(query)
    return [CategoryTotalDTO(category=row[0], total=Decimal(row[1])) for row in result.all()]


async def get_month_transactions(
    session: AsyncSession,
    user_id: int,
    now: datetime | None = None,
) -> list[Transaction]:
    now = now or datetime.now()
    month_start = datetime.combine(now.date().replace(day=1), time.min)
    next_month = (month_start.replace(day=28) + timedelta(days=4)).replace(day=1)

    query = (
        select(Transaction)
        .where(
            Transaction.user_id == user_id,
            Transaction.created_at >= month_start,
            Transaction.created_at < next_month,
        )
        .order_by(Transaction.created_at.desc())
    )
    result = await session.scalars(query)
    return list(result.all())


async def get_daily_expenses(
    session: AsyncSession,
    user_id: int,
    now: datetime | None = None,
) -> list[Transaction]:
    now = now or datetime.now()
    day_start = datetime.combine(now.date(), time.min)
    day_end = day_start + timedelta(days=1)

    query = (
        select(Transaction)
        .where(
            Transaction.user_id == user_id,
            Transaction.type == TransactionType.EXPENSE,
            Transaction.created_at >= day_start,
            Transaction.created_at < day_end,
        )
        .order_by(Transaction.created_at.desc())
    )
    result = await session.scalars(query)
    return list(result.all())


async def get_expense_total_between(
    session: AsyncSession,
    user_id: int,
    start_at: datetime,
    end_at: datetime,
) -> Decimal:
    query = select(func.coalesce(func.sum(Transaction.amount), 0)).where(
        Transaction.user_id == user_id,
        Transaction.type == TransactionType.EXPENSE,
        Transaction.created_at >= start_at,
        Transaction.created_at < end_at,
    )
    return Decimal(await session.scalar(query) or 0)


async def list_active_budgets(
    session: AsyncSession,
    user_id: int,
    now: datetime | None = None,
    limit: int = 10,
) -> list[Budget]:
    now = now or datetime.now()
    query = (
        select(Budget)
        .where(Budget.user_id == user_id, Budget.end_at > now)
        .order_by(Budget.start_at.asc(), Budget.id.desc())
        .limit(limit)
    )
    result = await session.scalars(query)
    return list(result.all())


async def get_budget_by_period(
    session: AsyncSession,
    user_id: int,
    period_type: str,
    start_at: datetime,
    end_at: datetime,
) -> Budget | None:
    query = select(Budget).where(
        Budget.user_id == user_id,
        Budget.period_type == BudgetPeriod(period_type),
        Budget.start_at == start_at,
        Budget.end_at == end_at,
    )
    return await session.scalar(query)


async def upsert_budget(
    session: AsyncSession,
    user_id: int,
    amount: Decimal,
    period_type: str,
    title: str,
    start_at: datetime,
    end_at: datetime,
) -> Budget:
    budget = await get_budget_by_period(session, user_id, period_type, start_at, end_at)
    if budget is None:
        budget = Budget(
            user_id=user_id,
            limit_amount=amount,
            period_type=BudgetPeriod(period_type),
            title=title,
            start_at=start_at,
            end_at=end_at,
        )
        session.add(budget)
    else:
        budget.limit_amount = amount
        budget.title = title
    await session.flush()
    return budget


async def delete_budget(session: AsyncSession, user_id: int, budget_id: int) -> bool:
    result = await session.execute(delete(Budget).where(Budget.user_id == user_id, Budget.id == budget_id))
    return bool(result.rowcount)


async def list_transactions(
    session: AsyncSession,
    user_id: int,
    limit: int = 10,
    offset: int = 0,
) -> list[Transaction]:
    query = (
        select(Transaction)
        .where(Transaction.user_id == user_id)
        .order_by(Transaction.created_at.desc(), Transaction.id.desc())
        .limit(limit)
        .offset(offset)
    )
    result = await session.scalars(query)
    return list(result.all())


async def count_transactions(session: AsyncSession, user_id: int) -> int:
    query = select(func.count(Transaction.id)).where(Transaction.user_id == user_id)
    return int(await session.scalar(query) or 0)


async def delete_user_transactions(session: AsyncSession, user_id: int) -> None:
    await session.execute(delete(Transaction).where(Transaction.user_id == user_id))


async def create_debt(
    session: AsyncSession,
    user_id: int,
    person: str,
    amount: Decimal,
    direction: str,
    note: str | None = None,
) -> Debt:
    debt = Debt(
        user_id=user_id,
        person=person,
        amount=amount,
        direction=DebtDirection(direction),
        note=note,
    )
    session.add(debt)
    await session.flush()
    return debt


async def list_active_debts(session: AsyncSession, user_id: int, limit: int = 20) -> list[Debt]:
    query = (
        select(Debt)
        .where(Debt.user_id == user_id, Debt.status == DebtStatus.ACTIVE)
        .order_by(Debt.created_at.desc(), Debt.id.desc())
        .limit(limit)
    )
    result = await session.scalars(query)
    return list(result.all())


async def get_debt(session: AsyncSession, user_id: int, debt_id: int) -> Debt | None:
    query = select(Debt).where(Debt.id == debt_id, Debt.user_id == user_id)
    return await session.scalar(query)


async def mark_debt_paid(session: AsyncSession, user_id: int, debt_id: int) -> bool:
    query = (
        update(Debt)
        .where(Debt.id == debt_id, Debt.user_id == user_id, Debt.status == DebtStatus.ACTIVE)
        .values(status=DebtStatus.PAID, closed_at=datetime.now())
    )
    result = await session.execute(query)
    return bool(result.rowcount)


async def get_debt_summary(session: AsyncSession, user_id: int) -> tuple[Decimal, Decimal]:
    i_owe_query = select(func.coalesce(func.sum(Debt.amount), 0)).where(
        Debt.user_id == user_id,
        Debt.status == DebtStatus.ACTIVE,
        Debt.direction == DebtDirection.I_OWE,
    )
    owed_to_me_query = select(func.coalesce(func.sum(Debt.amount), 0)).where(
        Debt.user_id == user_id,
        Debt.status == DebtStatus.ACTIVE,
        Debt.direction == DebtDirection.OWED_TO_ME,
    )
    i_owe = Decimal(await session.scalar(i_owe_query) or 0)
    owed_to_me = Decimal(await session.scalar(owed_to_me_query) or 0)
    return i_owe, owed_to_me
