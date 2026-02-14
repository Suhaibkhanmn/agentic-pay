"""
Seed script — populates the database with demo data so the dashboard
isn't empty on first load.

Usage:
    cd backend
    python seed.py

Creates:
  - 1 admin user (admin@agentpay.dev / admin123)
  - 1 approver user (approver@agentpay.dev / approver123)
  - 3 vendors (Microsoft, AWS, Shadyco — one blocked)
  - 5 policies covering all major rule types
  - 8 payment requests with different outcomes:
      auto-approved, requires-approval, blocked, completed, failed
  - Matching approval requests, transactions, and audit logs
"""

import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings
from app.core.security import get_password_hash
from app.db.base import Base
from app.models.approval import ApprovalRequest, ApprovalStatus
from app.models.audit_log import AuditLog
from app.models.payment_request import PaymentRequest, PaymentStatus
from app.models.policy import Policy, RuleType
from app.models.transaction import Transaction, TransactionStatus
from app.models.user import User, UserRole
from app.models.vendor import Vendor, VendorStatus

engine = create_engine(settings.SYNC_DATABASE_URL, echo=False)
SessionLocal = sessionmaker(bind=engine)

now = datetime.now(timezone.utc)


def seed():
    session = SessionLocal()
    try:
        # ── Users ──
        admin = User(
            id=uuid.uuid4(),
            email="admin@agentpay.dev",
            hashed_password=get_password_hash("admin123"),
            role=UserRole.ADMIN.value,
        )
        approver = User(
            id=uuid.uuid4(),
            email="approver@agentpay.dev",
            hashed_password=get_password_hash("approver123"),
            role=UserRole.APPROVER.value,
        )
        session.add_all([admin, approver])
        session.flush()
        print(f"  Users: admin@agentpay.dev (admin123), approver@agentpay.dev (approver123)")

        # ── Vendors ──
        microsoft = Vendor(
            id=uuid.uuid4(),
            name="Microsoft",
            category="software",
            status=VendorStatus.ACTIVE.value,
            daily_limit=Decimal("50000"),
            monthly_limit=Decimal("200000"),
        )
        aws = Vendor(
            id=uuid.uuid4(),
            name="Amazon Web Services",
            category="cloud",
            status=VendorStatus.ACTIVE.value,
            daily_limit=Decimal("100000"),
            monthly_limit=Decimal("500000"),
        )
        # Suspicious vendor — similar name to Microsoft (typo-squatting demo)
        shadyco = Vendor(
            id=uuid.uuid4(),
            name="Micros0ft Corp",
            category="software",
            status=VendorStatus.ACTIVE.value,
        )
        session.add_all([microsoft, aws, shadyco])
        session.flush()
        print(f"  Vendors: Microsoft, Amazon Web Services, Micros0ft Corp")

        # ── Policies ──
        policies = [
            Policy(
                name="Max Transaction Limit",
                rule_type=RuleType.MAX_TXN.value,
                parameters={"max_amount": 25000},
                priority=100,
                is_active=True,
            ),
            Policy(
                name="Approval Required > $1000",
                rule_type=RuleType.APPROVAL_THRESHOLD.value,
                parameters={"threshold": 1000},
                priority=90,
                is_active=True,
            ),
            Policy(
                name="Software Budget $50k/month",
                rule_type=RuleType.CATEGORY_BUDGET.value,
                parameters={"category": "software", "monthly_budget": 50000},
                priority=80,
                is_active=True,
            ),
            Policy(
                name="Velocity: max 5 payments/hour",
                rule_type=RuleType.VELOCITY.value,
                parameters={"max_count": 5, "window_minutes": 60},
                priority=70,
                is_active=True,
            ),
            Policy(
                name="Vendor Must Be Active",
                rule_type=RuleType.VENDOR_ALLOWLIST.value,
                parameters={},
                priority=60,
                is_active=True,
            ),
        ]
        session.add_all(policies)
        session.flush()
        print(f"  Policies: {len(policies)} rules created")

        # ── Payment Requests with diverse outcomes ──

        # 1. Small payment — auto-approved, completed
        p1 = _payment(session, admin, microsoft, Decimal("250.00"), "USD",
                       "Office 365 subscription", "software",
                       PaymentStatus.COMPLETED, days_ago=5)
        _transaction(session, p1, True, days_ago=5)
        _audit(session, p1, "PAYMENT_EVALUATED", "system", {
            "policy_verdict": "ALLOW_AUTOPAY", "final_verdict": "ALLOW_AUTOPAY",
            "escalated_by_agent": False, "triggered_rules": [],
        }, days_ago=5)
        _audit(session, p1, "PAYMENT_EXECUTED", "system:celery", {
            "provider": "mock", "success": True,
        }, days_ago=5)

        # 2. Medium payment — required approval, approved, completed
        p2 = _payment(session, admin, aws, Decimal("4500.00"), "USD",
                       "EC2 reserved instances", "cloud",
                       PaymentStatus.COMPLETED, days_ago=3)
        _approval(session, p2, ApprovalStatus.APPROVED, approver, days_ago=3)
        _transaction(session, p2, True, days_ago=3)
        _audit(session, p2, "PAYMENT_EVALUATED", "system", {
            "policy_verdict": "REQUIRE_APPROVAL", "final_verdict": "REQUIRE_APPROVAL",
            "escalated_by_agent": False,
            "triggered_rules": [{"rule_name": "Approval Required > $1000",
                                  "rule_type": "APPROVAL_THRESHOLD",
                                  "verdict": "REQUIRE_APPROVAL",
                                  "detail": "Amount 4500.00 exceeds approval threshold 1000"}],
        }, days_ago=3)
        _audit(session, p2, "APPROVAL_DECIDED", f"user:{approver.id}", {
            "action": "approve", "reason": "Standard AWS billing",
        }, days_ago=3)
        _audit(session, p2, "PAYMENT_EXECUTED", "system:celery", {
            "provider": "mock", "success": True,
        }, days_ago=3)

        # 3. Large payment — blocked by max txn limit
        p3 = _payment(session, admin, microsoft, Decimal("30000.00"), "USD",
                       "Enterprise Agreement renewal", "software",
                       PaymentStatus.BLOCKED, days_ago=2)
        _audit(session, p3, "PAYMENT_EVALUATED", "system", {
            "policy_verdict": "BLOCK", "final_verdict": "BLOCK",
            "escalated_by_agent": False,
            "triggered_rules": [{"rule_name": "Max Transaction Limit",
                                  "rule_type": "MAX_TXN",
                                  "verdict": "BLOCK",
                                  "detail": "Amount 30000.00 exceeds max 25000"}],
        }, days_ago=2)

        # 4. Payment to suspicious vendor — agent escalated
        p4 = _payment(session, admin, shadyco, Decimal("800.00"), "USD",
                       "Software license", "software",
                       PaymentStatus.REQUIRE_APPROVAL, days_ago=1)
        _approval(session, p4, ApprovalStatus.PENDING, None, days_ago=1)
        _audit(session, p4, "PAYMENT_EVALUATED", "system", {
            "policy_verdict": "ALLOW_AUTOPAY", "final_verdict": "REQUIRE_APPROVAL",
            "escalated_by_agent": True,
            "triggered_rules": [],
            "agent_assessment": {
                "risk_score": 78,
                "risk_explanation": "Vendor name 'Micros0ft Corp' is suspiciously similar to 'Microsoft'. Possible typo-squatting attempt.",
                "should_escalate": True,
                "suspicious_patterns": ["typo-squatting", "new_vendor"],
                "confidence": 0.85,
            },
            "risk_signals": [
                {"signal": "typo_squatting", "severity": "high",
                 "detail": "Vendor 'Micros0ft Corp' is suspiciously similar to existing vendor 'Microsoft' (similarity: 82%)"},
                {"signal": "first_payment", "severity": "medium",
                 "detail": "First-ever payment to vendor 'Micros0ft Corp'"},
            ],
            "risk_composite_score": 65,
        }, days_ago=1)

        # 5. Another completed payment for chart data
        p5 = _payment(session, admin, aws, Decimal("1200.00"), "USD",
                       "S3 storage fees", "cloud",
                       PaymentStatus.COMPLETED, days_ago=4)
        _approval(session, p5, ApprovalStatus.APPROVED, approver, days_ago=4)
        _transaction(session, p5, True, days_ago=4)
        _audit(session, p5, "PAYMENT_EVALUATED", "system", {
            "policy_verdict": "REQUIRE_APPROVAL", "final_verdict": "REQUIRE_APPROVAL",
            "escalated_by_agent": False,
            "triggered_rules": [{"rule_name": "Approval Required > $1000",
                                  "rule_type": "APPROVAL_THRESHOLD",
                                  "verdict": "REQUIRE_APPROVAL",
                                  "detail": "Amount 1200.00 exceeds approval threshold 1000"}],
        }, days_ago=4)
        _audit(session, p5, "PAYMENT_EXECUTED", "system:celery", {
            "provider": "mock", "success": True,
        }, days_ago=4)

        # 6. Small auto-pay, completed yesterday
        p6 = _payment(session, admin, microsoft, Decimal("99.00"), "USD",
                       "GitHub Copilot seats", "software",
                       PaymentStatus.COMPLETED, days_ago=1)
        _transaction(session, p6, True, days_ago=1)
        _audit(session, p6, "PAYMENT_EVALUATED", "system", {
            "policy_verdict": "ALLOW_AUTOPAY", "final_verdict": "ALLOW_AUTOPAY",
            "escalated_by_agent": False, "triggered_rules": [],
        }, days_ago=1)
        _audit(session, p6, "PAYMENT_EXECUTED", "system:celery", {
            "provider": "mock", "success": True,
        }, days_ago=1)

        # 7. Payment that was rejected by approver
        p7 = _payment(session, admin, aws, Decimal("8500.00"), "USD",
                       "GPU cluster for ML training", "cloud",
                       PaymentStatus.REJECTED, days_ago=2)
        _approval(session, p7, ApprovalStatus.REJECTED, approver, days_ago=2)
        _audit(session, p7, "PAYMENT_EVALUATED", "system", {
            "policy_verdict": "REQUIRE_APPROVAL", "final_verdict": "REQUIRE_APPROVAL",
            "escalated_by_agent": False,
            "triggered_rules": [{"rule_name": "Approval Required > $1000",
                                  "rule_type": "APPROVAL_THRESHOLD",
                                  "verdict": "REQUIRE_APPROVAL",
                                  "detail": "Amount 8500.00 exceeds approval threshold 1000"}],
        }, days_ago=2)
        _audit(session, p7, "APPROVAL_DECIDED", f"user:{approver.id}", {
            "action": "reject", "reason": "Not in this quarter's budget",
        }, days_ago=2)

        # 8. Today's small payment — auto-approved, completed
        p8 = _payment(session, admin, microsoft, Decimal("450.00"), "USD",
                       "Azure DevOps licenses", "software",
                       PaymentStatus.COMPLETED, days_ago=0)
        _transaction(session, p8, True, days_ago=0)
        _audit(session, p8, "PAYMENT_EVALUATED", "system", {
            "policy_verdict": "ALLOW_AUTOPAY", "final_verdict": "ALLOW_AUTOPAY",
            "escalated_by_agent": False, "triggered_rules": [],
        }, days_ago=0)
        _audit(session, p8, "PAYMENT_EXECUTED", "system:celery", {
            "provider": "mock", "success": True,
        }, days_ago=0)

        session.commit()
        print("\nSeed complete! Log in with admin@agentpay.dev / admin123")

    except Exception as e:
        session.rollback()
        print(f"Seed failed: {e}")
        raise
    finally:
        session.close()


# ── Helpers ──

def _payment(session: Session, user: User, vendor: Vendor,
             amount: Decimal, currency: str, desc: str, category: str,
             status: PaymentStatus, days_ago: int) -> PaymentRequest:
    p = PaymentRequest(
        id=uuid.uuid4(),
        vendor_id=vendor.id,
        amount=amount,
        currency=currency,
        description=desc,
        category=category,
        status=status.value,
        idempotency_key=f"seed-{uuid.uuid4().hex[:12]}",
        created_by=user.id,
        created_at=now - timedelta(days=days_ago, hours=2),
    )
    session.add(p)
    session.flush()
    return p


def _transaction(session: Session, payment: PaymentRequest,
                 success: bool, days_ago: int):
    t = Transaction(
        id=uuid.uuid4(),
        payment_request_id=payment.id,
        provider="MOCK",
        provider_txn_id=f"mock_{uuid.uuid4().hex[:12]}",
        amount=payment.amount,
        currency=payment.currency,
        status=TransactionStatus.SUCCESS.value if success else TransactionStatus.FAILED.value,
        raw_response={"id": f"mock_{uuid.uuid4().hex[:8]}", "status": "succeeded" if success else "failed"},
        created_at=now - timedelta(days=days_ago, hours=1),
    )
    session.add(t)


def _approval(session: Session, payment: PaymentRequest,
              status: ApprovalStatus, decider: User | None, days_ago: int):
    a = ApprovalRequest(
        id=uuid.uuid4(),
        payment_request_id=payment.id,
        status=status.value,
        decided_by=decider.id if decider else None,
        decided_at=(now - timedelta(days=days_ago, hours=1, minutes=30)) if decider else None,
        reason="Approved via seed" if status == ApprovalStatus.APPROVED else (
            "Not in this quarter's budget" if status == ApprovalStatus.REJECTED else None
        ),
        created_at=now - timedelta(days=days_ago, hours=2),
    )
    session.add(a)


def _audit(session: Session, payment: PaymentRequest,
           event_type: str, actor: str, detail: dict, days_ago: int):
    a = AuditLog(
        id=uuid.uuid4(),
        payment_request_id=payment.id,
        event_type=event_type,
        actor=actor,
        detail=detail,
        created_at=now - timedelta(days=days_ago, hours=1, minutes=45),
    )
    session.add(a)


if __name__ == "__main__":
    print("Seeding database...")
    seed()
