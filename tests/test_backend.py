from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
import tempfile
import unittest

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import crud
from app.db import Base
from app.models import EntryType, FinancialRecord, User, UserRole, UserStatus
from app.schemas import FinancialRecordCreate, FinancialRecordUpdate, UserCreate, UserUpdate
from app.security import ROLE_ORDER, require_role


class BackendTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(bind=self.engine)
        self.SessionLocal = sessionmaker(bind=self.engine, autoflush=False, autocommit=False)
        self.db = self.SessionLocal()

        self.admin = User(name="Admin", email="admin@example.com", role=UserRole.admin, status=UserStatus.active)
        self.analyst = User(name="Analyst", email="analyst@example.com", role=UserRole.analyst, status=UserStatus.active)
        self.viewer = User(name="Viewer", email="viewer@example.com", role=UserRole.viewer, status=UserStatus.active)
        self.db.add_all([self.admin, self.analyst, self.viewer])
        self.db.flush()

        self.db.add_all(
            [
                FinancialRecord(
                    amount=Decimal("1200.00"),
                    entry_type=EntryType.income,
                    category="Salary",
                    record_date=datetime(2026, 1, 5, tzinfo=timezone.utc),
                    notes="January salary",
                    created_by=self.admin.id,
                ),
                FinancialRecord(
                    amount=Decimal("250.00"),
                    entry_type=EntryType.expense,
                    category="Travel",
                    record_date=datetime(2026, 1, 8, tzinfo=timezone.utc),
                    notes="Client visit",
                    created_by=self.analyst.id,
                ),
                FinancialRecord(
                    amount=Decimal("900.00"),
                    entry_type=EntryType.expense,
                    category="Rent",
                    record_date=datetime(2026, 2, 1, tzinfo=timezone.utc),
                    notes="Office rent",
                    created_by=self.admin.id,
                ),
            ]
        )
        self.db.commit()

    def tearDown(self) -> None:
        self.db.close()
        Base.metadata.drop_all(bind=self.engine)
        self.engine.dispose()

    def test_role_hierarchy(self) -> None:
        self.assertLess(ROLE_ORDER[UserRole.viewer], ROLE_ORDER[UserRole.analyst])
        self.assertLess(ROLE_ORDER[UserRole.analyst], ROLE_ORDER[UserRole.admin])

    def test_require_role_blocks_low_privilege_users(self) -> None:
        dependency = require_role(UserRole.analyst)
        with self.assertRaises(HTTPException) as context:
            dependency(current_user=self.viewer)
        self.assertEqual(context.exception.status_code, 403)

    def test_create_user_and_duplicate_email(self) -> None:
        created = crud.create_user(
            self.db,
            UserCreate(name="New User", email="new@example.com", role=UserRole.viewer, status=UserStatus.active),
        )
        self.assertEqual(created.email, "new@example.com")

        with self.assertRaises(HTTPException) as context:
            crud.create_user(
                self.db,
                UserCreate(name="Another", email="new@example.com", role=UserRole.viewer, status=UserStatus.active),
            )
        self.assertEqual(context.exception.status_code, 409)

    def test_record_filtering_and_summary(self) -> None:
        records = crud.list_records(
            self.db,
            skip=0,
            limit=10,
            entry_type=EntryType.expense,
            category=None,
            start_date=None,
            end_date=None,
            search=None,
        )
        self.assertEqual(len(records), 2)
        self.assertTrue(all(record.entry_type == EntryType.expense for record in records))

        summary = crud.summary_payload(self.db, start_date=date(2026, 1, 1), end_date=date(2026, 1, 31))
        self.assertEqual(summary["total_income"], Decimal("1200.00"))
        self.assertEqual(summary["total_expenses"], Decimal("250.00"))
        self.assertEqual(summary["net_balance"], Decimal("950.00"))
        self.assertEqual(summary["record_count"], 2)
        self.assertEqual(summary["category_totals"]["Salary"], Decimal("1200.00"))

    def test_update_and_soft_delete_record(self) -> None:
        record = self.db.query(FinancialRecord).filter_by(category="Travel").one()
        updated = crud.update_record(
            self.db,
            record,
            FinancialRecordUpdate(notes="Updated travel note", category="Travel Ops"),
        )
        self.assertEqual(updated.notes, "Updated travel note")
        self.assertEqual(updated.category, "Travel Ops")

        deleted = crud.soft_delete_record(self.db, updated)
        self.assertTrue(deleted.is_deleted)
        with self.assertRaises(HTTPException) as context:
            crud.get_record_or_404(self.db, deleted.id)
        self.assertEqual(context.exception.status_code, 404)

    def test_update_user_status(self) -> None:
        updated = crud.update_user(self.db, self.viewer, UserUpdate(status=UserStatus.inactive))
        self.assertEqual(updated.status, UserStatus.inactive)


if __name__ == "__main__":
    unittest.main()
