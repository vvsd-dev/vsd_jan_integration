"""Replace BL-level Wharfage JE with per-car By Vehicle JEs; reload IFCV."""

from __future__ import annotations

import frappe
from frappe.utils import flt, today

from vsd_jan_integration.scripts.setup_n039_bl_cost import EXCEL, IMPORT_FILE, CC, _make_je, _submit_je
from vsd_jan_integration.vsd_jan_international_customization.doctype.import_file_cost_voucher.import_file_cost_voucher import (
	load_from_import_file,
)


def run():
	# Ensure Costing scope
	frappe.db.set_value("Costing", "wharfage", "allocation_scope", "By Vehicle", update_modified=False)

	# Cancel BL wharfage JE if submitted
	bl_je = frappe.db.get_value(
		"Journal Entry",
		{"cheque_no": f"ACTUAL|WHARFAGE|{IMPORT_FILE}", "docstatus": 1},
		"name",
	)
	if bl_je:
		doc = frappe.get_doc("Journal Entry", bl_je)
		doc.cancel()
		frappe.db.commit()
		print("cancelled BL wharfage", bl_je)

	exp, pay = "Wharfage - JIL", "Wharfage Payable - JIL"
	for chassis, x in EXCEL.items():
		item = frappe.db.get_value("Item", {"custom_chassis_no": chassis}, "name")
		amt = flt(x["wharfage"])
		cheque = f"ACTUAL|WHARFAGE|{chassis}"[:140]
		_make_je(
			cheque,
			f"ACTUAL WHARFAGE | {chassis} | {IMPORT_FILE}",
			[
				{
					"account": exp,
					"debit_in_account_currency": amt,
					"debit": amt,
					"account_currency": "TZS",
					"exchange_rate": 1,
					"user_remark": "WHARFAGE",
					"cost_center": CC,
				},
				{
					"account": pay,
					"credit_in_account_currency": amt,
					"credit": amt,
					"account_currency": "TZS",
					"exchange_rate": 1,
					"user_remark": "WHARFAGE payable",
					"cost_center": CC,
				},
			],
			item_code=item,
			chassis=chassis,
		)
		name = frappe.db.get_value("Journal Entry", {"cheque_no": cheque}, "name")
		_submit_je(name)
		print("WHARFAGE", chassis, amt, name)

	# Reload IFCV draft
	existing = frappe.db.get_value(
		"Import File Cost Voucher", {"import_file": IMPORT_FILE, "docstatus": 0}, "name"
	)
	data = load_from_import_file(IMPORT_FILE)
	if existing:
		doc = frappe.get_doc("Import File Cost Voucher", existing)
		doc.set("vehicles", [])
		doc.set("expenses", [])
		doc.set("allocations", [])
	else:
		doc = frappe.new_doc("Import File Cost Voucher")
		doc.import_file = IMPORT_FILE

	for v in data["vehicles"]:
		doc.append("vehicles", v)
	for e in data["expenses"]:
		doc.append("expenses", e)
	doc.flags.ignore_permissions = True
	if existing:
		doc.save(ignore_permissions=True)
	else:
		doc.insert(ignore_permissions=True)
	frappe.db.commit()
	print("reloaded", doc.name, "exp", len(doc.expenses), "alloc", len(doc.allocations or []))
	return doc.name
