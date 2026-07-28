"""Feature #2 — three-stage approval chain with digital signatures."""

from __future__ import annotations


class TestStageOrdering:
    def test_new_report_has_three_pending_stages(self, sample_report):
        stages = [s["stage"] for s in sample_report["steps"]]
        assert stages == ["finance_manager", "inspector", "ceo"]
        assert all(s["status"] == "pending" for s in sample_report["steps"])
        assert sample_report["status"] == "draft"

    def test_submit_moves_to_finance_stage(self, client, auth, sample_report):
        response = client.post(f"/api/v1/reports/{sample_report['id']}/submit", headers=auth("requester"))
        assert response.status_code == 200
        assert response.json()["status"] == "pending_finance"
        assert response.json()["submitted_at"] is not None

    def test_inspector_cannot_jump_the_queue(self, client, auth, sample_report):
        client.post(f"/api/v1/reports/{sample_report['id']}/submit", headers=auth("requester"))
        response = client.post(
            f"/api/v1/reports/{sample_report['id']}/decision",
            json={"approved": True, "comment": "looks fine"},
            headers=auth("inspector"),
        )
        assert response.status_code == 409
        assert "requires role finance_manager" in response.json()["detail"]

    def test_full_happy_path(self, client, auth, sample_report):
        rid = sample_report["id"]
        client.post(f"/api/v1/reports/{rid}/submit", headers=auth("requester"))

        for role, expected in [
            ("finance_manager", "pending_inspector"),
            ("inspector", "pending_ceo"),
            ("ceo", "approved"),
        ]:
            decision = client.post(
                f"/api/v1/reports/{rid}/decision",
                json={"approved": True, "comment": f"approved by {role}"},
                headers=auth(role),
            )
            assert decision.status_code == 200, decision.text
            assert decision.json()["status"] == "approved"
            state = client.get(f"/api/v1/reports/{rid}", headers=auth("requester")).json()
            assert state["status"] == expected

        final = client.get(f"/api/v1/reports/{rid}", headers=auth("requester")).json()
        assert final["completed_at"] is not None

    def test_rejection_stops_the_chain(self, client, auth, sample_report):
        rid = sample_report["id"]
        client.post(f"/api/v1/reports/{rid}/submit", headers=auth("requester"))
        response = client.post(
            f"/api/v1/reports/{rid}/decision",
            json={"approved": False, "comment": "insufficient documentation"},
            headers=auth("finance_manager"),
        )
        assert response.status_code == 200
        detail = client.get(f"/api/v1/reports/{rid}", headers=auth("requester")).json()
        assert detail["status"] == "rejected"
        assert [s["status"] for s in detail["steps"]] == [
            "rejected",
            "skipped",
            "skipped",
        ]

    def test_cannot_submit_twice(self, client, auth, sample_report):
        rid = sample_report["id"]
        client.post(f"/api/v1/reports/{rid}/submit", headers=auth("requester"))
        second = client.post(f"/api/v1/reports/{rid}/submit", headers=auth("requester"))
        assert second.status_code == 409

    def test_only_creator_submits(self, client, auth, sample_report):
        response = client.post(f"/api/v1/reports/{sample_report['id']}/submit", headers=auth("inspector"))
        assert response.status_code == 403


class TestDigitalSignatures:
    def test_each_approval_is_signed(self, client, auth, sample_report):
        rid = sample_report["id"]
        client.post(f"/api/v1/reports/{rid}/submit", headers=auth("requester"))
        for role in ("finance_manager", "inspector", "ceo"):
            client.post(
                f"/api/v1/reports/{rid}/decision",
                json={"approved": True, "comment": "ok"},
                headers=auth(role),
            )

        verification = client.get(f"/api/v1/reports/{rid}/signatures", headers=auth("auditor")).json()
        assert verification["all_valid"] is True
        assert len(verification["steps"]) == 3
        for step in verification["steps"]:
            assert step["signed"] is True
            assert step["valid"] is True
            assert step["key_fingerprint"]

    def test_signature_breaks_when_report_is_tampered(self, client, auth, sample_report, engine):
        from sqlalchemy.orm import sessionmaker

        from app.models.report import Report

        rid = sample_report["id"]
        client.post(f"/api/v1/reports/{rid}/submit", headers=auth("requester"))
        client.post(
            f"/api/v1/reports/{rid}/decision",
            json={"approved": True, "comment": "ok"},
            headers=auth("finance_manager"),
        )

        before = client.get(f"/api/v1/reports/{rid}/signatures", headers=auth("auditor")).json()
        assert before["all_valid"] is True

        Session = sessionmaker(bind=engine, future=True)
        with Session() as session:  # simulate a rogue DBA editing the amount
            report = session.get(Report, rid)
            report.principal = report.principal * 2
            session.commit()

        after = client.get(f"/api/v1/reports/{rid}/signatures", headers=auth("auditor")).json()
        assert after["all_valid"] is False
        assert after["content_unchanged"] is False
        assert "tampering" in after["steps"][0]["reason"]


class TestInbox:
    def test_inbox_shows_only_your_stage(self, client, auth, sample_report):
        rid = sample_report["id"]
        client.post(f"/api/v1/reports/{rid}/submit", headers=auth("requester"))

        finance_inbox = client.get("/api/v1/reports/inbox", headers=auth("finance_manager")).json()
        assert [r["id"] for r in finance_inbox] == [rid]
        assert client.get("/api/v1/reports/inbox", headers=auth("ceo")).json() == []

        client.post(
            f"/api/v1/reports/{rid}/decision",
            json={"approved": True, "comment": ""},
            headers=auth("finance_manager"),
        )
        assert client.get("/api/v1/reports/inbox", headers=auth("finance_manager")).json() == []
        assert [r["id"] for r in client.get("/api/v1/reports/inbox", headers=auth("inspector")).json()] == [rid]

    def test_workflow_state_endpoint(self, client, auth, sample_report):
        rid = sample_report["id"]
        client.post(f"/api/v1/reports/{rid}/submit", headers=auth("requester"))
        state = client.get(f"/api/v1/reports/{rid}/workflow", headers=auth("finance_manager")).json()
        assert state["current_stage"] == "finance_manager"
        assert state["you_can_act"] is True
        assert len(state["stages"]) == 3


class TestSignaturePersistence:
    """Regression: signatures must verify against reloaded rows, not just the
    in-memory objects. Decimal scale normalisation on flush previously changed
    the content hash and invalidated every stored signature."""

    def test_signatures_valid_after_session_reload(self, client, auth, sample_report, engine):
        from sqlalchemy.orm import sessionmaker

        from app.models.report import Report
        from app.services import workflow

        rid = sample_report["id"]
        client.post(f"/api/v1/reports/{rid}/submit", headers=auth("requester"))
        for role in ("finance_manager", "inspector", "ceo"):
            client.post(
                f"/api/v1/reports/{rid}/decision",
                json={"approved": True, "comment": "ok"},
                headers=auth(role),
            )

        # brand-new session: nothing is cached from the request that signed it
        Session = sessionmaker(bind=engine, future=True)
        with Session() as session:
            report = session.get(Report, rid)
            result = workflow.verify_report_signatures(session, report)

        assert result["content_unchanged"] is True
        assert result["all_valid"] is True
        assert all(step["valid"] for step in result["steps"])
