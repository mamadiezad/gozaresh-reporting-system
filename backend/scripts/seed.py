#!/usr/bin/env python3
"""Seed the database with demo users, reports and a partially-run workflow.

Usage:
    python scripts/seed.py            # create demo data
    python scripts/seed.py --reset    # drop everything first
"""

from __future__ import annotations

import argparse
import asyncio
import random
import sys
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select

from app.core.config import settings
from app.core.database import Base, engine, session_scope
from app.core.security import hash_password
from app.core.signing import ensure_keypair
from app.models.enums import (
    InstallmentStatus,
    ReportStatus,
    ReportType,
    UserRole,
)
from app.models.report import Installment, Report
from app.models.user import User
from app.services import alerts as alerts_service
from app.services import fx, workflow
from app.services.calculator import calculate

DEMO_PASSWORD = "DemoPass!2024"

DEMO_USERS = [
    ("alice", "alice@gozaresh-demo.com", "علی رضایی", UserRole.REQUESTER),
    ("bob", "bob@gozaresh-demo.com", "بهرام مالکی", UserRole.FINANCE_MANAGER),
    ("carol", "carol@gozaresh-demo.com", "کارولین بازرس", UserRole.INSPECTOR),
    ("dave", "dave@gozaresh-demo.com", "داوود مدیری", UserRole.CEO),
    ("erin", "erin@gozaresh-demo.com", "الهام حسابرس", UserRole.AUDITOR),
    ("root", "root@gozaresh-demo.com", "مدیر سیستم", UserRole.ADMIN),
    ("svc-integration", "svc@gozaresh-demo.com", "Service Account", UserRole.ADMIN),
]

DEMO_REPORTS = [
    (
        "تأمین سرمایه در گردش زنجیره تولید",
        ReportType.LOAN,
        "12500000000",
        "IRR",
        "23.5",
        24,
        "خزانه‌داری",
        "شرکت صنایع آریا",
    ),
    (
        "خرید تجهیزات خط تولید — واردات",
        ReportType.INVESTMENT,
        "480000",
        "EUR",
        "6.75",
        36,
        "عملیات",
        "Siemens AG",
    ),
    (
        "تسویه فاکتور پیمانکار فاز ۲",
        ReportType.INVOICE,
        "3400000000",
        "IRR",
        "0",
        3,
        "پروژه‌ها",
        "مهندسی پارس",
    ),
    (
        "اعتبار اسنادی واردات مواد اولیه",
        ReportType.SETTLEMENT,
        "260000",
        "USD",
        "8.25",
        12,
        "بازرگانی",
        "Global Trading LLC",
    ),
    (
        "هزینه‌های عملیاتی سه‌ماهه سوم",
        ReportType.EXPENSE,
        "1850000000",
        "IRR",
        "0",
        6,
        "اداری",
        "متفرقه",
    ),
    (
        "تسهیلات توسعه شعب منطقه‌ای",
        ReportType.LOAN,
        "45000000000",
        "IRR",
        "21",
        48,
        "توسعه",
        "بانک ملت",
    ),
    (
        "قرارداد نگهداری سامانه‌ها",
        ReportType.INSTALLMENT,
        "95000",
        "AED",
        "5.5",
        12,
        "فناوری اطلاعات",
        "Gulf IT Services",
    ),
    (
        "سرمایه‌گذاری در صندوق درآمد ثابت",
        ReportType.INVESTMENT,
        "8200000000",
        "IRR",
        "27",
        12,
        "خزانه‌داری",
        "صندوق سرمایه‌گذاری آگاه",
    ),
]


def reset_schema() -> None:
    print("⚠️  dropping all tables…")
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


async def seed() -> None:
    Base.metadata.create_all(bind=engine)

    with session_scope() as db:
        if db.execute(select(User).limit(1)).scalar_one_or_none():
            print("ℹ️  data already present — run with --reset to start clean")
            return

        # ---- users -------------------------------------------------
        users: dict[str, User] = {}
        for username, email, full_name, role in DEMO_USERS:
            key_id = f"user-{username}"
            user = User(
                username=username,
                email=email,
                full_name=full_name,
                hashed_password=hash_password(DEMO_PASSWORD),
                role=role,
                is_active=True,
                signing_key_id=key_id,
                public_key_pem=ensure_keypair(key_id),
            )
            db.add(user)
            users[username] = user
        db.flush()
        print(f"✅ {len(users)} users created (password: {DEMO_PASSWORD})")

        # ---- reports ------------------------------------------------
        created: list[Report] = []
        for index, (
            title,
            rtype,
            principal,
            currency,
            rate,
            months,
            dept,
            party,
        ) in enumerate(DEMO_REPORTS):
            start = date.today() - timedelta(days=random.randint(5, 120))
            fx_rate = fx_source = None
            if currency != settings.BASE_CURRENCY:
                quote = await fx.get_rate(currency, settings.BASE_CURRENCY, db)
                fx_rate, fx_source = quote.rate, quote.source

            result = calculate(
                principal=principal,
                annual_rate_percent=rate,
                term_months=months,
                currency=currency,
                start_date=start,
                fx_rate=fx_rate,
                base_currency=settings.BASE_CURRENCY,
                fx_source=fx_source,
            )

            report = Report(
                reference=workflow.generate_reference(),
                title=title,
                description=f"گزارش نمونه برای {party}",
                report_type=rtype,
                status=ReportStatus.DRAFT,
                principal=Decimal(principal),
                currency=currency,
                base_currency=settings.BASE_CURRENCY,
                fx_rate=fx_rate,
                fx_source=fx_source,
                amount_in_base=result.amount_in_base or result.total_payable,
                annual_rate=Decimal(rate) / 100,
                term_months=months,
                total_interest=result.total_interest,
                total_payable=result.total_payable,
                monthly_installment=result.periodic_payment,
                effective_annual_rate=result.effective_annual_rate,
                calc_duration_ms=result.duration_ms,
                start_date=start,
                department=dept,
                counterparty=party,
                created_by_id=users["alice"].id,
                created_at=datetime.now(UTC) - timedelta(days=random.randint(1, 300)),
            )
            db.add(report)
            db.flush()

            for row in result.schedule:
                overdue = row.due_date < date.today() and index % 3 == 0
                db.add(
                    Installment(
                        report_id=report.id,
                        number=row.number,
                        due_date=row.due_date,
                        amount=row.amount,
                        principal_component=row.principal_component,
                        interest_component=row.interest_component,
                        remaining_balance=row.remaining_balance,
                        status=InstallmentStatus.SCHEDULED
                        if overdue
                        else (InstallmentStatus.PAID if row.due_date < date.today() else InstallmentStatus.SCHEDULED),
                        paid_amount=row.amount if (row.due_date < date.today() and not overdue) else Decimal(0),
                        paid_at=datetime.now(UTC) if (row.due_date < date.today() and not overdue) else None,
                    )
                )

            workflow.initialise_workflow(db, report)
            report.content_hash = workflow.report_content_hash(report)
            created.append(report)
        db.flush()
        print(f"✅ {len(created)} reports created with installment schedules")

        # ---- drive some through the workflow --------------------------
        # 0,1 -> fully approved | 2 -> rejected at inspector | 3 -> awaiting CEO
        # 4 -> awaiting inspector | 5 -> awaiting finance | 6,7 -> stay draft
        plans = [
            (0, ["bob", "carol", "dave"], True),
            (1, ["bob", "carol", "dave"], True),
            (2, ["bob", "carol"], False),
            (3, ["bob", "carol"], True),
            (4, ["bob"], True),
            (5, [], True),
        ]
        for index, approvers, approve in plans:
            report = created[index]
            await workflow.submit(db, report, users["alice"])
            for position, username in enumerate(approvers):
                last = position == len(approvers) - 1
                decision = workflow.Decision(
                    approved=approve or not last,
                    comment="مطابق مقررات داخلی تأیید شد" if (approve or not last) else "مدارک پشتیبان ناقص است",
                )
                await workflow.act(db, report, users[username], decision)
        print("✅ workflow states populated (approved / rejected / pending)")

        # ---- alerts ---------------------------------------------------
        for report in created:
            alerts_service.check_transaction_range(db, report)
        summary = await alerts_service.run_full_scan(db)
        print(f"✅ alerts generated: {summary}")

    print("\n🎉 Seed complete.\n")
    print("   Demo accounts (all share the same password):")
    for username, _, full_name, role in DEMO_USERS[:6]:
        print(f"     {username:<16} {role:<16} {full_name}")
    print(f"\n   Password: {DEMO_PASSWORD}")
    print("   API docs: http://localhost:8000/docs")
    print("   Dashboard: http://localhost:3000\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed the Gozaresh demo database")
    parser.add_argument("--reset", action="store_true", help="drop all tables first")
    args = parser.parse_args()

    if args.reset:
        reset_schema()
    asyncio.run(seed())


if __name__ == "__main__":
    main()
