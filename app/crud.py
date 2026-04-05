from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timezone
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from app.models import EntryType, FinancialRecord, User, UserRole, UserStatus
from app.schemas import FinancialRecordCreate, FinancialRecordUpdate, UserCreate, UserUpdate


def create_user(db: Session, payload: UserCreate) -> User:
    existing = db.execute(select(User).where(User.email == payload.email)).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already exists")

    user = User(
        name=payload.name.strip(),
        email=str(payload.email).lower(),
        role=payload.role,
        status=payload.status,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def update_user(db: Session, user: User, payload: UserUpdate) -> User:
    if payload.name is not None:
        user.name = payload.name.strip()
    if payload.role is not None:
        user.role = payload.role
    if payload.status is not None:
        user.status = payload.status
    db.commit()
    db.refresh(user)
    return user


def create_record(db: Session, payload: FinancialRecordCreate, created_by: int) -> FinancialRecord:
    record = FinancialRecord(
        amount=payload.amount,
        entry_type=payload.entry_type,
        category=payload.category,
        record_date=datetime.combine(payload.record_date, datetime.min.time(), tzinfo=timezone.utc),
        notes=payload.notes,
        created_by=created_by,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def update_record(db: Session, record: FinancialRecord, payload: FinancialRecordUpdate) -> FinancialRecord:
    if payload.amount is not None:
        record.amount = payload.amount
    if payload.entry_type is not None:
        record.entry_type = payload.entry_type
    if payload.category is not None:
        record.category = payload.category
    if payload.record_date is not None:
        record.record_date = datetime.combine(payload.record_date, datetime.min.time(), tzinfo=timezone.utc)
    if payload.notes is not None:
        record.notes = payload.notes
    db.commit()
    db.refresh(record)
    return record


def soft_delete_record(db: Session, record: FinancialRecord) -> FinancialRecord:
    record.is_deleted = True
    db.commit()
    db.refresh(record)
    return record


def get_record_or_404(db: Session, record_id: int) -> FinancialRecord:
    record = db.get(FinancialRecord, record_id)
    if record is None or record.is_deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Record not found")
    return record


def get_user_or_404(db: Session, user_id: int) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user


def list_records(
    db: Session,
    *,
    skip: int,
    limit: int,
    entry_type: EntryType | None,
    category: str | None,
    start_date: date | None,
    end_date: date | None,
    search: str | None,
) -> list[FinancialRecord]:
    conditions = [FinancialRecord.is_deleted.is_(False)]
    if entry_type is not None:
        conditions.append(FinancialRecord.entry_type == entry_type)
    if category is not None:
        conditions.append(func.lower(FinancialRecord.category) == category.lower())
    if start_date is not None:
        conditions.append(FinancialRecord.record_date >= datetime.combine(start_date, datetime.min.time(), tzinfo=timezone.utc))
    if end_date is not None:
        conditions.append(FinancialRecord.record_date <= datetime.combine(end_date, datetime.max.time(), tzinfo=timezone.utc))
    if search is not None:
        like_value = f"%{search.lower()}%"
        conditions.append(
            func.lower(FinancialRecord.notes).like(like_value)
            | func.lower(FinancialRecord.category).like(like_value)
        )

    statement = (
        select(FinancialRecord)
        .where(and_(*conditions))
        .order_by(FinancialRecord.record_date.desc(), FinancialRecord.id.desc())
        .offset(skip)
        .limit(limit)
    )
    return list(db.execute(statement).scalars().all())


def summary_payload(db: Session, *, start_date: date | None, end_date: date | None) -> dict:
    conditions = [FinancialRecord.is_deleted.is_(False)]
    if start_date is not None:
        conditions.append(FinancialRecord.record_date >= datetime.combine(start_date, datetime.min.time(), tzinfo=timezone.utc))
    if end_date is not None:
        conditions.append(FinancialRecord.record_date <= datetime.combine(end_date, datetime.max.time(), tzinfo=timezone.utc))

    base_query = select(FinancialRecord).where(and_(*conditions))
    records = list(db.execute(base_query.order_by(FinancialRecord.record_date.desc(), FinancialRecord.id.desc())).scalars().all())

    total_income = Decimal("0.00")
    total_expenses = Decimal("0.00")
    category_totals: dict[str, Decimal] = defaultdict(lambda: Decimal("0.00"))
    monthly_totals: dict[str, dict[str, Decimal]] = defaultdict(lambda: {"income": Decimal("0.00"), "expense": Decimal("0.00")})

    for record in records:
        amount = Decimal(record.amount)
        category_totals[record.category] += amount
        month_key = record.record_date.strftime("%Y-%m")
        monthly_totals[month_key][record.entry_type.value] += amount
        if record.entry_type == EntryType.income:
            total_income += amount
        else:
            total_expenses += amount

    recent_activity = records[:5]
    monthly_trends = [
        {
            "month": month,
            "income": values["income"],
            "expense": values["expense"],
            "net": values["income"] - values["expense"],
        }
        for month, values in sorted(monthly_totals.items())
    ]

    return {
        "total_income": total_income,
        "total_expenses": total_expenses,
        "net_balance": total_income - total_expenses,
        "record_count": len(records),
        "category_totals": dict(category_totals),
        "recent_activity": recent_activity,
        "monthly_trends": monthly_trends,
    }
