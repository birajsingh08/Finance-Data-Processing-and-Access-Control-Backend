from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

from fastapi import Depends, FastAPI, HTTPException, Query, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app import crud
from app.db import Base, SessionLocal, engine
from app.models import EntryType, FinancialRecord, User, UserRole, UserStatus
from app.schemas import (
    DashboardSummary,
    FinancialRecordCreate,
    FinancialRecordRead,
    FinancialRecordUpdate,
    UserCreate,
    UserRead,
    UserUpdate,
)
from app.security import get_current_user, get_db, require_role

app = FastAPI(title="Finance Dashboard Backend", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup() -> None:
    Base.metadata.create_all(bind=engine)
    seed_data()


def seed_data() -> None:
    db = SessionLocal()
    try:
        if db.query(User).count() > 0:
            return

        admin = User(name="Finance Admin", email="admin@example.com", role=UserRole.admin, status=UserStatus.active)
        analyst = User(name="Finance Analyst", email="analyst@example.com", role=UserRole.analyst, status=UserStatus.active)
        viewer = User(name="Finance Viewer", email="viewer@example.com", role=UserRole.viewer, status=UserStatus.active)
        db.add_all([admin, analyst, viewer])
        db.flush()

        sample_records = [
            {"amount": Decimal("12000.00"), "entry_type": EntryType.income, "category": "Salary", "record_date": datetime(2026, 1, 5, tzinfo=timezone.utc), "notes": "Monthly salary", "created_by": admin.id},
            {"amount": Decimal("1400.00"), "entry_type": EntryType.expense, "category": "Rent", "record_date": datetime(2026, 1, 1, tzinfo=timezone.utc), "notes": "Office rent", "created_by": admin.id},
            {"amount": Decimal("250.00"), "entry_type": EntryType.expense, "category": "Travel", "record_date": datetime(2026, 1, 8, tzinfo=timezone.utc), "notes": "Client visit", "created_by": analyst.id},
            {"amount": Decimal("4000.00"), "entry_type": EntryType.income, "category": "Consulting", "record_date": datetime(2026, 2, 12, tzinfo=timezone.utc), "notes": "Project milestone", "created_by": analyst.id},
        ]
        db.add_all([FinancialRecord(**record) for record in sample_records])
        db.commit()
    finally:
        db.close()


@app.exception_handler(HTTPException)
def http_exception_handler(_, exc: HTTPException):
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/")
def root() -> dict[str, str]:
    return {
        "name": "Finance Dashboard Backend",
        "status": "running",
        "health": "/health",
        "docs": "/docs",
    }


@app.post("/users", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def create_user(
    payload: UserCreate,
    _: User = Depends(require_role(UserRole.admin)),
    db: Session = Depends(get_db),
):
    return crud.create_user(db, payload)


@app.get("/users", response_model=list[UserRead])
def list_users(
    _: User = Depends(require_role(UserRole.admin)),
    db: Session = Depends(get_db),
):
    return db.query(User).order_by(User.id.asc()).all()


@app.get("/users/me", response_model=UserRead)
def read_me(current_user: User = Depends(get_current_user)):
    return current_user


@app.patch("/users/{user_id}", response_model=UserRead)
def update_user(
    user_id: int,
    payload: UserUpdate,
    _: User = Depends(require_role(UserRole.admin)),
    db: Session = Depends(get_db),
):
    user = crud.get_user_or_404(db, user_id)
    return crud.update_user(db, user, payload)


@app.post("/records", response_model=FinancialRecordRead, status_code=status.HTTP_201_CREATED)
def create_record(
    payload: FinancialRecordCreate,
    current_user: User = Depends(require_role(UserRole.admin)),
    db: Session = Depends(get_db),
):
    return crud.create_record(db, payload, created_by=current_user.id)


@app.get("/records", response_model=list[FinancialRecordRead])
def list_records(
    _: User = Depends(require_role(UserRole.analyst)),
    db: Session = Depends(get_db),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    entry_type: EntryType | None = None,
    category: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    search: str | None = None,
):
    records = crud.list_records(
        db,
        skip=skip,
        limit=limit,
        entry_type=entry_type,
        category=category,
        start_date=start_date,
        end_date=end_date,
        search=search.strip() if search else None,
    )
    return records


@app.get("/records/{record_id}", response_model=FinancialRecordRead)
def read_record(
    record_id: int,
    _: User = Depends(require_role(UserRole.analyst)),
    db: Session = Depends(get_db),
):
    return crud.get_record_or_404(db, record_id)


@app.patch("/records/{record_id}", response_model=FinancialRecordRead)
def update_record(
    record_id: int,
    payload: FinancialRecordUpdate,
    _: User = Depends(require_role(UserRole.admin)),
    db: Session = Depends(get_db),
):
    record = crud.get_record_or_404(db, record_id)
    return crud.update_record(db, record, payload)


@app.delete("/records/{record_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_record(
    record_id: int,
    _: User = Depends(require_role(UserRole.admin)),
    db: Session = Depends(get_db),
):
    record = crud.get_record_or_404(db, record_id)
    crud.soft_delete_record(db, record)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.get("/dashboard/summary", response_model=DashboardSummary)
def dashboard_summary(
    _: User = Depends(require_role(UserRole.analyst)),
    db: Session = Depends(get_db),
    start_date: date | None = None,
    end_date: date | None = None,
):
    summary = crud.summary_payload(db, start_date=start_date, end_date=end_date)
    return DashboardSummary(**summary)
