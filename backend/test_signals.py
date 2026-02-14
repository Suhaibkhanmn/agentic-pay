"""Check payment detail for risk signals."""
import httpx
import json

r = httpx.post(
    "http://localhost:8000/api/v1/auth/login",
    data={"username": "admin@agentpay.dev", "password": "admin123"},
)
token = r.json()["access_token"]
c = httpx.Client(
    follow_redirects=True,
    headers={"Authorization": f"Bearer {token}"},
    timeout=30,
)

# List recent payments
payments = c.get("http://localhost:8000/api/v1/payments?limit=3").json()
for p in payments:
    print(f"ID: {p['id'][:8]}... | ${p['amount']} | {p['status']}")

# Get the most recent payment detail
if payments:
    pid = payments[0]["id"]
    detail = c.get(f"http://localhost:8000/api/v1/payments/{pid}").json()

    print(f"\n=== Payment Detail: {pid[:8]}... ===")
    print(f"Amount: ${detail['amount']} {detail['currency']}")
    print(f"Status: {detail['status']}")
    print(f"Category: {detail.get('category')}")

    orch = detail.get("orchestrator_result", {})
    if orch:
        print(f"\nPolicy verdict: {orch.get('policy_verdict')}")
        print(f"Final verdict: {orch.get('final_verdict')}")
        print(f"Escalated by agent: {orch.get('escalated_by_agent')}")

        rr = orch.get("risk_report", {})
        if rr:
            print(f"\nComposite score: {rr.get('composite_score')}/100")
            signals = rr.get("signals", [])
            print(f"Signals ({len(signals)}):")
            for s in signals:
                print(f"  [{s['severity'].upper()}] {s['signal']}: {s['detail']}")

            vc = rr.get("vendor_context")
            if vc:
                print(f"\nVendor Context:")
                print(f"  Name: {vc['name']} | Age: {vc['age_days']}d")
                print(f"  Payments: {vc['total_payments']} | Avg: ${vc.get('avg_amount')}")
                print(f"  Dominant cat: {vc.get('dominant_category')} ({vc.get('dominance_pct')})")
                print(f"  Recent: {len(vc.get('recent_payments', []))} entries")

        aa = orch.get("agent_assessment", {})
        if aa:
            print(f"\nAgent Assessment:")
            print(f"  Risk: {aa['risk_score']}/100 | Escalate: {aa['should_escalate']}")
            print(f"  Explanation: {aa['risk_explanation']}")
            print(f"  Patterns: {aa.get('suspicious_patterns', [])}")
