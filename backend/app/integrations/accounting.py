"""Accounting/ERP exchange: standard JSON + XML documents over REST or file drop."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from xml.etree import ElementTree as ET

from app.core.config import settings
from app.integrations.base import BaseConnector, IntegrationError
from app.models.enums import IntegrationSystem
from app.models.report import Report
from app.utils.money import D, money_context, q, to_minor_units


# --------------------------------------------------------------------------
# Document builders
# --------------------------------------------------------------------------
def build_voucher(report: Report) -> dict[str, Any]:
    """Double-entry journal voucher — debits must equal credits."""
    amount = to_minor_units(report.total_payable or report.principal, report.currency)
    principal = to_minor_units(report.principal, report.currency)
    with money_context():
        interest = q(D(amount) - D(principal))

    lines = [
        {
            "account": "1310",
            "description": "Receivable / principal",
            "debit": str(principal),
            "credit": "0",
        },
    ]
    if interest > 0:
        lines.append(
            {
                "account": "1320",
                "description": "Accrued interest",
                "debit": str(interest),
                "credit": "0",
            }
        )
    lines.append(
        {
            "account": "2110",
            "description": f"Payable — {report.counterparty or 'counterparty'}",
            "debit": "0",
            "credit": str(amount),
        }
    )

    return {
        "voucher": {
            "number": report.reference,
            "date": (report.completed_at or report.created_at).date().isoformat(),
            "currency": report.currency,
            "base_currency": report.base_currency,
            "fx_rate": str(report.fx_rate) if report.fx_rate else "1",
            "description": report.title,
            "department": report.department,
            "source_system": "gozaresh",
            "lines": lines,
            "totals": {
                "debit": str(to_minor_units(sum(D(line["debit"]) for line in lines), report.currency)),
                "credit": str(to_minor_units(sum(D(line["credit"]) for line in lines), report.currency)),
            },
        },
        "generated_at": datetime.now(UTC).isoformat(),
    }


def voucher_to_xml(voucher: dict[str, Any]) -> str:
    """Serialise the voucher to the standard XML interchange format."""
    v = voucher["voucher"]
    root = ET.Element("AccountingVoucher", attrib={"xmlns": "urn:gozaresh:accounting:1.0"})
    header = ET.SubElement(root, "Header")
    for tag in (
        "number",
        "date",
        "currency",
        "base_currency",
        "fx_rate",
        "description",
        "department",
        "source_system",
    ):
        ET.SubElement(
            header,
            tag.replace("_", "").capitalize() if "_" not in tag else "".join(p.capitalize() for p in tag.split("_")),
        ).text = str(v.get(tag, ""))

    lines_el = ET.SubElement(root, "Lines")
    for index, line in enumerate(v["lines"], start=1):
        line_el = ET.SubElement(lines_el, "Line", attrib={"no": str(index)})
        ET.SubElement(line_el, "Account").text = line["account"]
        ET.SubElement(line_el, "Description").text = line["description"]
        ET.SubElement(line_el, "Debit").text = line["debit"]
        ET.SubElement(line_el, "Credit").text = line["credit"]

    totals_el = ET.SubElement(root, "Totals")
    ET.SubElement(totals_el, "Debit").text = v["totals"]["debit"]
    ET.SubElement(totals_el, "Credit").text = v["totals"]["credit"]

    ET.indent(root, space="  ")
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(root, encoding="unicode")


def parse_voucher_xml(xml_text: str) -> dict[str, Any]:
    """Inbound parser so partner ERPs can push documents back to us."""
    root = ET.fromstring(xml_text)
    ns = {"g": "urn:gozaresh:accounting:1.0"}

    def find(path: str) -> str:
        node = root.find(path, ns)
        return node.text or "" if node is not None else ""

    lines = []
    for line_el in root.findall("g:Lines/g:Line", ns):
        lines.append(
            {
                "account": (line_el.findtext("g:Account", default="", namespaces=ns)),
                "description": (line_el.findtext("g:Description", default="", namespaces=ns)),
                "debit": (line_el.findtext("g:Debit", default="0", namespaces=ns)),
                "credit": (line_el.findtext("g:Credit", default="0", namespaces=ns)),
            }
        )
    return {
        "number": find("g:Header/g:Number"),
        "date": find("g:Header/g:Date"),
        "currency": find("g:Header/g:Currency"),
        "description": find("g:Header/g:Description"),
        "lines": lines,
    }


def validate_balanced(voucher: dict[str, Any]) -> bool:
    lines = voucher["voucher"]["lines"] if "voucher" in voucher else voucher["lines"]
    debit: Decimal = sum((D(line["debit"]) for line in lines), Decimal(0))
    credit: Decimal = sum((D(line["credit"]) for line in lines), Decimal(0))
    return debit == credit


# --------------------------------------------------------------------------
# Connector
# --------------------------------------------------------------------------
class AccountingConnector(BaseConnector):
    system = IntegrationSystem.ACCOUNTING

    async def _perform(self, operation: str, payload: dict[str, Any]) -> dict[str, Any]:
        if operation == "push_voucher":
            if not validate_balanced(payload):
                raise IntegrationError("Voucher is not balanced (debit != credit)", retryable=False)
            if self.sandbox:
                return {
                    "sandbox": True,
                    "reference": payload["voucher"]["number"],
                    "status": "POSTED",
                    "ledger_id": f"LDG-{payload['voucher']['number']}",
                    "posted_at": datetime.now(UTC).isoformat(),
                }
            return await self._http_post(f"{settings.BANK_GATEWAY_URL}/../accounting/vouchers", payload)
        raise IntegrationError(f"Unknown accounting operation {operation!r}", retryable=False)

    async def push_report(self, report: Report) -> dict[str, Any]:
        voucher = build_voucher(report)
        _, response = await self.execute("push_voucher", voucher, report_id=report.id)
        return response
