"""Restructure N.TAN039 actuals per screenshot Actual column.

Keep By-Vehicle singles (TRA, Fixed By Vehicle heads, etc.) for accuracy checks.
For Actual By BL: cancel wrong per-car JEs, post one bulk JE, IFCV distributes.

- WHARFAGE Actual By BL → cancel per-car wharfage; post BL bulk
- CLEARING CONTAINER Actual By BL → cancel Fixed JEs (had clearing per car);
  recreate Fixed without clearing; post BL bulk clearing
- TPA / ICD / Shipping already BL bulk — keep
"""

from __future__ import annotations

import frappe
from frappe.utils import flt

from vsd_jan_integration.scripts.setup_n039_bl_cost import (
	CC,
	EXCEL,
	IMPORT_FILE,
	_make_je,
	_submit_je,
)
from vsd_jan_integration.vsd_jan_international_customization.doctype.import_file_cost_voucher.import_file_cost_voucher import (
	load_from_import_file,
)
from vsd_jan_integration.vsd_jan_international_customization.utils.mkt_fixed_costing import (
	ensure_fixed_costing_for_items,
)


def _cancel_je(name):
	if not name:
		return
	ds = frappe.db.get_value("Journal Entry", name, "docstatus")
	if ds == 1:
		frappe.get_doc("Journal Entry", name).cancel()
		frappe.db.commit()
		print("cancelled", name)
	elif ds == 0:
		frappe.delete_doc("Journal Entry", name, force=1, ignore_permissions=True)
		frappe.db.commit()
		print("deleted draft", name)


def run():
	# 1) Costing scopes per screenshot Actual
	frappe.db.set_value("Costing", "wharfage", "allocation_scope", "By BL Equal", update_modified=False)
	frappe.db.set_value(
		"Costing", "clearing_container", "allocation_scope", "By BL Equal", update_modified=False
	)
	frappe.db.set_value("Costing", "tpa", "allocation_scope", "By BL Equal", update_modified=False)
	frappe.db.set_value("Costing", "icd", "allocation_scope", "By BL M3", update_modified=False)
	frappe.db.set_value(
		"Costing", "shipping_line", "allocation_scope", "By BL M3", update_modified=False
	)
	frappe.db.commit()
	print("scopes: wharfage/clearing/tpa=By BL Equal; icd/shipping=By BL M3")

	# Cars on this IF
	items = frappe.db.sql(
		"""
		SELECT DISTINCT pii.item_code, i.custom_chassis_no
		FROM `tabPurchase Invoice Item` pii
		INNER JOIN `tabPurchase Invoice` pi ON pi.name=pii.parent
		INNER JOIN `tabItem` i ON i.name=pii.item_code
		WHERE pi.import_file=%s AND pi.docstatus < 2
		""",
		IMPORT_FILE,
		as_dict=True,
	)
	codes = [r.item_code for r in items]
	print("cars", len(codes))

	# 2) Cancel per-car WHARFAGE (keep TRA singles!)
	for chassis in EXCEL:
		cheque = f"ACTUAL|WHARFAGE|{chassis}"[:140]
		name = frappe.db.get_value("Journal Entry", {"cheque_no": cheque, "docstatus": 1}, "name")
		if not name:
			name = frappe.db.get_value("Journal Entry", {"cheque_no": cheque, "docstatus": 0}, "name")
		_cancel_je(name)

	# 3) Cancel Fixed JEs for these cars (will recreate without clearing)
	for code in codes:
		cheque = f"FIXED|{code}"[:140]
		name = frappe.db.get_value("Journal Entry", {"cheque_no": cheque, "docstatus": 1}, "name")
		if not name:
			# hashed FCJV names — find by custom_item + remark
			name = frappe.db.sql(
				"""
				SELECT name FROM `tabJournal Entry`
				WHERE docstatus=1 AND custom_item=%s
				  AND (cheque_no LIKE 'FIXED|%%' OR user_remark LIKE 'FIXED COSTING%%')
				ORDER BY modified DESC LIMIT 1
				""",
				code,
			)
			name = name[0][0] if name else None
		_cancel_je(name)

	# Also cancel any cancelled leftover drafts with same cheque? ensure will recreate.

	# 4) Recreate Fixed (By Vehicle actuals only — no clearing)
	res = ensure_fixed_costing_for_items(codes, auto_submit_jv=False, import_file=IMPORT_FILE)
	print("fixed recreated", len(res["journal_entries"]), "err", res["errors"])
	for je in res["journal_entries"]:
		frappe.db.sql(
			"UPDATE `tabJournal Entry Account` SET cost_center=%s WHERE parent=%s AND IFNULL(cost_center,'')=''",
			(CC, je),
		)
		# verify no Clearing Container lines
		has_clear = frappe.db.sql(
			"""
			SELECT 1 FROM `tabJournal Entry Account`
			WHERE parent=%s AND account LIKE 'Clearing Container%%' LIMIT 1
			""",
			je,
		)
		if has_clear:
			print("WARN still has clearing on", je)
		_submit_je(je)
		print(" submitted FIXED", je)

	# 5) Bulk WHARFAGE (sum Excel)
	wharf_total = sum(flt(x["wharfage"]) for x in EXCEL.values())
	_make_je(
		f"ACTUAL|WHARFAGE|{IMPORT_FILE}"[:140],
		f"ACTUAL WHARFAGE | {IMPORT_FILE} | BL bulk (Excel sum)",
		[
			{
				"account": "Wharfage - JIL",
				"debit_in_account_currency": wharf_total,
				"debit": wharf_total,
				"account_currency": "TZS",
				"exchange_rate": 1,
				"user_remark": "WHARFAGE",
				"cost_center": CC,
			},
			{
				"account": "Wharfage Payable - JIL",
				"credit_in_account_currency": wharf_total,
				"credit": wharf_total,
				"account_currency": "TZS",
				"exchange_rate": 1,
				"user_remark": "WHARFAGE payable",
				"cost_center": CC,
			},
		],
	)
	wname = frappe.db.get_value(
		"Journal Entry", {"cheque_no": f"ACTUAL|WHARFAGE|{IMPORT_FILE}"[:140]}, "name"
	)
	_submit_je(wname)
	print("BL wharfage", wharf_total, wname)

	# 6) Bulk CLEARING (112350 x 7)
	clear_amt = 112350.0 * len(codes)
	_make_je(
		f"ACTUAL|CLEARING|{IMPORT_FILE}"[:140],
		f"ACTUAL CLEARING CONTAINER | {IMPORT_FILE} | BL bulk",
		[
			{
				"account": "Clearing Container - JIL",
				"debit_in_account_currency": clear_amt,
				"debit": clear_amt,
				"account_currency": "TZS",
				"exchange_rate": 1,
				"user_remark": "CLEARING CONTAINER",
				"cost_center": CC,
			},
			{
				"account": "Clearing Container Payable - JIL",
				"credit_in_account_currency": clear_amt,
				"credit": clear_amt,
				"account_currency": "TZS",
				"exchange_rate": 1,
				"user_remark": "CLEARING payable",
				"cost_center": CC,
			},
		],
	)
	# ensure payable exists
	if not frappe.db.exists("Account", "Clearing Container Payable - JIL"):
		from vsd_jan_integration.patches.seed_costing_from_tax_accounts import (
			_company,
			_ensure_payable_account,
		)

		_ensure_payable_account(_company(), "Clearing Container", "TZS")
		# rewrite credit account if create used different name
		pay = frappe.db.get_value("Costing", "clearing_container", "payable_account")
		if pay:
			frappe.db.sql(
				"""
				UPDATE `tabJournal Entry Account` jea
				INNER JOIN `tabJournal Entry` je ON je.name=jea.parent
				SET jea.account=%s
				WHERE je.cheque_no=%s AND jea.credit > 0
				""",
				(pay, f"ACTUAL|CLEARING|{IMPORT_FILE}"[:140]),
			)

	cname = frappe.db.get_value(
		"Journal Entry", {"cheque_no": f"ACTUAL|CLEARING|{IMPORT_FILE}"[:140]}, "name"
	)
	# if payable missing on insert, fix and submit
	pay = frappe.db.get_value("Costing", "clearing_container", "payable_account") or (
		"Clearing Container Payable - JIL"
	)
	if cname:
		frappe.db.sql(
			"""
			UPDATE `tabJournal Entry Account`
			SET account=%s WHERE parent=%s AND credit > 0
			""",
			(pay, cname),
		)
		frappe.db.commit()
		_submit_je(cname)
		print("BL clearing", clear_amt, cname)

	# 7) Reload IFCV with chassis fix
	existing = frappe.db.get_value(
		"Import File Cost Voucher", {"import_file": IMPORT_FILE, "docstatus": 0}, "name"
	)
	data = load_from_import_file(IMPORT_FILE)
	doc = frappe.get_doc("Import File Cost Voucher", existing) if existing else frappe.new_doc(
		"Import File Cost Voucher"
	)
	if not existing:
		doc.import_file = IMPORT_FILE
	doc.set("vehicles", [])
	doc.set("expenses", [])
	doc.set("allocations", [])
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

	# Force redistribute (save triggers validate → distribute)
	doc.reload()
	doc._distribute_allocations(keep_manual=False)
	doc.total_expense_amount = sum(flt(r.amount) for r in (doc.expenses or []))
	doc.total_allocated_amount = sum(flt(r.amount) for r in (doc.allocations or []))
	doc.save(ignore_permissions=True)
	frappe.db.commit()

	# Spot-check
	null_ch = sum(1 for a in doc.allocations if not a.chassis_no)
	clear_exp = [e for e in doc.expenses if (e.costing_head or "") == "clearing_container"]
	wharf_exp = [e for e in doc.expenses if (e.costing_head or "") == "wharfage"]
	print(
		"IFCV",
		doc.name,
		"exp",
		len(doc.expenses),
		"alloc",
		len(doc.allocations),
		"null_chassis",
		null_ch,
		"clearing_rows",
		len(clear_exp),
		clear_exp[0].distribution_method if clear_exp else None,
		clear_exp[0].amount if clear_exp else None,
		"wharf_rows",
		len(wharf_exp),
		wharf_exp[0].distribution_method if wharf_exp else None,
		wharf_exp[0].amount if wharf_exp else None,
	)
	# sample allocation
	for a in doc.allocations[:5]:
		print(" alloc sample", a.chassis_no, a.costing_head, a.amount)
	return doc.name
