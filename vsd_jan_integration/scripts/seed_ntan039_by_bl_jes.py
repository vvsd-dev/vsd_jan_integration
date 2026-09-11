"""Create individual Journal Entries for N.TAN039/26MSC By-BL IFCV testing.

One JE per Costing Head so Desk observers can see each expense appear separately.
Amounts match 1 BL COST.xlsx totals for BL MEDUW3445865 (7 cars).
"""

from __future__ import annotations

import frappe
from frappe.utils import flt, today

IMPORT_FILE = "N.TAN039/26MSC"
COMPANY = "Jan International Limited"
CREDIT_ACCOUNT = "Cash - JIL"

# Excel BL totals (NEW COST FILE, 7 cars on MEDUW3445865)
# ICD / Shipping Line: Excel is USD (m3*13 / m3*94). Posted as those numbers so
# IFCV can push the same figures into Car Costing Japan lines (USD projected).
BY_BL_ENTRIES = [
	{
		"title": "IFCV TEST 1 — Clearing Container (By BL Equal)",
		"account": "Clearing Container - JIL",
		"costing_code": "clearing_container",
		"amount": 786450,  # 112350 * 7
		"distribution_method": "By BL Equal",
		"remark": "Excel fixed 112,350 x 7 cars",
	},
	{
		"title": "IFCV TEST 2 — TPA (By BL Equal)",
		"account": "TPA - JIL",
		"costing_code": "tpa",
		"amount": 988232,  # 141176 * 7
		"distribution_method": "By BL Equal",
		"remark": "Excel TPA 141,176 x 7 cars",
	},
	{
		"title": "IFCV TEST 3 — Wharfage (By BL Equal)",
		"account": "Wharfage - JIL",
		"costing_code": "wharfage",
		"amount": 5699643.936,  # sum of duty*7%
		"distribution_method": "By BL Equal",
		"remark": "Excel sum of wharfage (duty x 7%)",
	},
	{
		"title": "IFCV TEST 4 — ICD (By BL M3)",
		"account": "ICD - JIL",
		"costing_code": "icd",
		"amount": 1325.467,  # sum m3*13
		"distribution_method": "By BL M3",
		"remark": "Excel ICD USD total (m3 x 13)",
	},
	{
		"title": "IFCV TEST 5 — Shipping Line (By BL M3)",
		"account": "Shipping Line - JIL",
		"costing_code": "shipping_line",
		"amount": 9584.146,  # sum m3*94
		"distribution_method": "By BL M3",
		"remark": "Excel Shipping Line USD total (m3 x 94)",
	},
]


def _head_by_code(code):
	return frappe.db.get_value(
		"Costing",
		{"costing_code": code, "disabled": 0},
		["name", "account", "allocation_scope"],
		as_dict=True,
	)


def _existing_test_jes():
	return frappe.get_all(
		"Journal Entry",
		filters={"import_file": IMPORT_FILE, "user_remark": ["like", "IFCV TEST%"]},
		pluck="name",
	) or frappe.db.sql(
		"""
		SELECT name FROM `tabJournal Entry`
		WHERE import_file=%s AND title LIKE 'IFCV TEST%%'
		""",
		IMPORT_FILE,
		pluck=True,
	)


def cancel_previous_test_jes():
	names = frappe.get_all(
		"Journal Entry",
		filters={"import_file": IMPORT_FILE, "title": ["like", "IFCV TEST%"]},
		fields=["name", "docstatus"],
	)
	for row in names:
		doc = frappe.get_doc("Journal Entry", row.name)
		if doc.docstatus == 1:
			doc.cancel()
		frappe.delete_doc("Journal Entry", doc.name, force=1)
		print(f"removed old {row.name}")


def create_one_je(entry, posting_date=None):
	head = _head_by_code(entry["costing_code"])
	if not head:
		frappe.throw(f"Costing Head missing for {entry['costing_code']}")

	# Keep Costing Head.account aligned so IFCV auto-maps
	if head.account != entry["account"]:
		frappe.db.set_value("Costing", head.name, "account", entry["account"])

	amount = flt(entry["amount"])
	je = frappe.get_doc(
		{
			"doctype": "Journal Entry",
			"voucher_type": "Journal Entry",
			"company": COMPANY,
			"posting_date": posting_date or today(),
			"import_file": IMPORT_FILE,
			"title": entry["title"],
			"user_remark": entry["remark"],
			"accounts": [
				{
					"account": entry["account"],
					"debit_in_account_currency": amount,
					"debit": amount,
					"user_remark": entry["remark"],
				},
				{
					"account": CREDIT_ACCOUNT,
					"credit_in_account_currency": amount,
					"credit": amount,
					"user_remark": entry["remark"],
				},
			],
		}
	)
	je.insert(ignore_permissions=True)
	je.submit()
	return {
		"je": je.name,
		"title": entry["title"],
		"account": entry["account"],
		"amount": amount,
		"costing_head": head.name,
		"costing_code": entry["costing_code"],
		"distribution_method": entry["distribution_method"],
	}


def refresh_ifcv(ifcv_name=None):
	from vsd_jan_integration.vsd_jan_international_customization.doctype.import_file_cost_voucher.import_file_cost_voucher import (
		load_from_import_file,
	)

	if not ifcv_name:
		ifcv_name = frappe.db.get_value(
			"Import File Cost Voucher",
			{"import_file": IMPORT_FILE, "docstatus": 0},
			"name",
			order_by="modified desc",
		)
	if not ifcv_name:
		frappe.throw("No draft IFCV for N.TAN039/26MSC")

	doc = frappe.get_doc("Import File Cost Voucher", ifcv_name)
	payload = load_from_import_file(IMPORT_FILE)

	doc.set("vehicles", [])
	for v in payload["vehicles"]:
		doc.append("vehicles", v)

	doc.set("expenses", [])
	for e in payload["expenses"]:
		# Method comes from Costing.allocation_scope (Equal / M3 / Vehicle)
		doc.append(
			"expenses",
			{
				"expense_account": e["expense_account"],
				"description": e.get("description"),
				"amount": e["amount"],
				"source": e.get("source"),
				"costing_head": e.get("costing_head"),
				"distribution_method": e.get("distribution_method") or "By BL Equal",
			},
		)

	doc.save(ignore_permissions=True)
	frappe.db.commit()
	return {
		"ifcv": doc.name,
		"vehicles": len(doc.vehicles or []),
		"expenses": len(doc.expenses or []),
		"total_expense_amount": flt(doc.total_expense_amount),
		"total_allocated_amount": flt(doc.total_allocated_amount),
	}


def run_all(reset=True, refresh=True):
	"""Create all 5 test JEs, then refresh IFCV once."""
	if reset:
		cancel_previous_test_jes()
	created = []
	for entry in BY_BL_ENTRIES:
		row = create_one_je(entry)
		created.append(row)
		print(f"OK {row['je']} | {row['title']} | {row['amount']}")
	frappe.db.commit()
	info = refresh_ifcv() if refresh else {}
	return {"jes": created, "ifcv": info}


def run_step(index, reset_first=False):
	"""Create a single JE by 1-based index (1..5), refresh IFCV. For live browser demos."""
	if reset_first and index == 1:
		cancel_previous_test_jes()
	entry = BY_BL_ENTRIES[int(index) - 1]
	row = create_one_je(entry)
	frappe.db.commit()
	info = refresh_ifcv()
	print(f"STEP {index}: {row['je']} → IFCV {info['ifcv']} expenses={info['expenses']}")
	return {"je": row, "ifcv": info}


if __name__ == "__main__":
	run_all()
