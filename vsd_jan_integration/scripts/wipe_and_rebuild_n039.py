"""Wipe costing/import test data on site, then rebuild clean N.TAN039/26MSC.

Focus: TRA per car + bulk Wharfage = Σ(TRA×0.07), IFCV By Formula split.
"""

from __future__ import annotations

import frappe
from frappe.utils import flt, today

IMPORT_FILE = "N.TAN039/26MSC"
BL = "MEDUW3445865"
CC = "Main - JIL"
COMPANY = None

# Excel 1 BL COST — TRA per chassis (Wharfage Expected = TRA × 0.07)
CARS = [
	{"chassis": "ZRR70-0198971", "maker": "TOYOTA NOAH", "m3": 14.733, "tra": 9600000, "yen": 217000},
	{"chassis": "NSP140-9011378", "maker": "TOYOTA PORTE", "m3": 11.396, "tra": 8600000, "yen": 118000},
	{"chassis": "RT1-1006295", "maker": "HONDA CROSSROAD", "m3": 12.508, "tra": 9423484.8, "yen": 172000},
	{"chassis": "GRS180-0026901", "maker": "TOYOTA CROWN", "m3": 12.664, "tra": 10000000, "yen": 174000},
	{"chassis": "ANH20-8050726", "maker": "TOYOTA ALPHARD", "m3": 16.991, "tra": 11600000, "yen": 202000},
	{"chassis": "ANH15-0044728", "maker": "TOYOTA ALPHARD", "m3": 17.165, "tra": 10700000, "yen": 234000},
	{"chassis": "TRN215-0021658", "maker": "TOYOTA HILUX SURF", "m3": 16.502, "tra": 21500000, "yen": 1257000},
]


def _company():
	global COMPANY
	if not COMPANY:
		COMPANY = frappe.db.get_single_value("Global Defaults", "default_company")
	return COMPANY


def _cancel_then_delete(doctype, names, label):
	n_cancel = n_del = 0
	for name in names:
		try:
			ds = frappe.db.get_value(doctype, name, "docstatus")
			if ds == 1:
				doc = frappe.get_doc(doctype, name)
				doc.flags.ignore_permissions = True
				doc.cancel()
				n_cancel += 1
			frappe.delete_doc(doctype, name, force=1, ignore_permissions=True)
			n_del += 1
		except Exception as e:
			print(f"  skip {doctype} {name}: {e}")
		if (n_del % 50) == 0 and n_del:
			frappe.db.commit()
	frappe.db.commit()
	print(f"{label}: cancelled={n_cancel} deleted={n_del}")


def wipe_all():
	frappe.flags.ignore_permissions = True
	print("=== WIPE START ===")

	# IFCV (draft)
	ifcvs = frappe.get_all("Import File Cost Voucher", pluck="name")
	_cancel_then_delete("Import File Cost Voucher", ifcvs, "IFCV")

	# LCV if any
	if frappe.db.exists("DocType", "Landed Cost Voucher"):
		lcvs = frappe.get_all("Landed Cost Voucher", pluck="name")
		_cancel_then_delete("Landed Cost Voucher", lcvs, "LCV")

	# Journal Entries — cancel submitted, delete all
	jes = frappe.get_all("Journal Entry", fields=["name", "docstatus"], order_by="docstatus desc, modified desc")
	# submitted first
	_cancel_then_delete(
		"Journal Entry",
		[r.name for r in jes if r.docstatus == 1],
		"JE submitted",
	)
	# drafts + cancelled
	remaining = frappe.get_all("Journal Entry", pluck="name")
	_cancel_then_delete("Journal Entry", remaining, "JE rest")

	# Purchase Invoices (all draft on this site)
	pis = frappe.get_all("Purchase Invoice", pluck="name")
	_cancel_then_delete("Purchase Invoice", pis, "PI")

	# Car Costing — all draft; wipe parent + child tables
	ccs = frappe.db.count("Car Costing")
	if ccs:
		meta = frappe.get_meta("Car Costing")
		for df in meta.get_table_fields():
			frappe.db.sql(f"DELETE FROM `tab{df.options}`")
		frappe.db.sql("DELETE FROM `tabCar Costing`")
		frappe.db.commit()
		print(f"CC: deleted={ccs}")

	# Import Files
	ifs = frappe.get_all("Import File", pluck="name")
	_cancel_then_delete("Import File", ifs, "Import File")

	# Vehicle Items (chassis / BL set) — SQL after child cleanup
	items = frappe.db.sql(
		"""
		SELECT name FROM `tabItem`
		WHERE IFNULL(custom_chassis_no,'') != ''
		   OR IFNULL(custom_bl,'') != ''
		""",
		pluck=True,
	)
	n = 0
	if items:
		# common child / link tables
		for tbl, col in (
			("tabItem Price", "item_code"),
			("tabBin", "item_code"),
			("tabItem Reorder", "parent"),
			("tabItem Default", "parent"),
			("tabItem Barcode", "parent"),
			("tabItem Supplier", "parent"),
			("tabUOM Conversion Detail", "parent"),
			("tabItem Variant Attribute", "parent"),
			("tabItem Costing Line", "parent"),
		):
			if frappe.db.table_exists(tbl.replace("tab", "", 1) if False else tbl):
				pass
			# table_exists expects doctype name without tab sometimes — use raw
			try:
				frappe.db.sql(
					f"DELETE FROM `{tbl}` WHERE `{col}` IN (SELECT name FROM `tabItem` WHERE IFNULL(custom_chassis_no,'')!='' OR IFNULL(custom_bl,'')!='')"
				)
			except Exception:
				pass
		# Item costing custom children if present
		for child in ("Item Costing Line",):
			if frappe.db.exists("DocType", child):
				frappe.db.sql(f"DELETE FROM `tab{child}` WHERE parent IN %s", (tuple(items),))
		# delete items via SQL for speed (force)
		frappe.db.sql(
			"""
			DELETE FROM `tabItem`
			WHERE IFNULL(custom_chassis_no,'') != ''
			   OR IFNULL(custom_bl,'') != ''
			"""
		)
		# clean Version / Dynamic Link leftovers lightly
		n = len(items)
		frappe.db.commit()
	print(f"Item: deleted={n}")

	# Reset recent Item Excel Importers to Pending (optional undo)
	for iei in frappe.get_all("Item Excel Importer", pluck="name"):
		frappe.db.set_value(
			"Item Excel Importer",
			iei,
			{
				"import_status": "Pending",
				"import_log": "",
				"failed_records": "",
				"processed_cars": 0,
				"processed_invoices": 0,
			},
			update_modified=False,
		)
	frappe.db.commit()
	print("Item Excel Importers reset to Pending")

	print("=== WIPE DONE ===")
	print(
		"counts:",
		frappe.db.count("Import File Cost Voucher"),
		frappe.db.count("Journal Entry"),
		frappe.db.count("Purchase Invoice"),
		frappe.db.count("Car Costing"),
		frappe.db.count("Import File"),
		frappe.db.sql("SELECT COUNT(*) FROM `tabItem` WHERE IFNULL(custom_chassis_no,'')!=''")[0][0],
	)


def _ensure_item(car):
	code = f"{car['maker']} - {car['chassis']}"
	if frappe.db.exists("Item", code):
		frappe.db.set_value(
			"Item",
			code,
			{
				"custom_chassis_no": car["chassis"],
				"custom_bl": BL,
				"custom_m3": car["m3"],
				"custom_price": car["yen"],
				"custom_maker": car["maker"],
				"disabled": 0,
			},
			update_modified=False,
		)
		return code

	# minimal vehicle item
	item_group = frappe.db.get_value("Item Group", {"name": ["like", "%Vehicle%"]}, "name") or "All Item Groups"
	doc = frappe.get_doc(
		{
			"doctype": "Item",
			"item_code": code,
			"item_name": code,
			"item_group": item_group,
			"stock_uom": "Nos",
			"is_stock_item": 1,
			"include_item_in_manufacturing": 0,
			"custom_chassis_no": car["chassis"],
			"custom_bl": BL,
			"custom_m3": car["m3"],
			"custom_price": car["yen"],
			"custom_maker": car["maker"],
		}
	)
	doc.flags.ignore_permissions = True
	doc.flags.ignore_mandatory = True
	doc.insert(ignore_permissions=True)
	frappe.db.commit()
	return code


def _ensure_import_file():
	if frappe.db.exists("Import File", IMPORT_FILE):
		frappe.db.set_value(
			"Import File",
			IMPORT_FILE,
			{"bl_number": BL, "supplier_invoice_no": IMPORT_FILE, "import_file_number": IMPORT_FILE},
			update_modified=False,
		)
		frappe.db.commit()
		return IMPORT_FILE
	doc = frappe.get_doc(
		{
			"doctype": "Import File",
			"import_file_number": IMPORT_FILE,
			"bl_number": BL,
			"supplier_invoice_no": IMPORT_FILE,
			"invoice_currency": "JPY",
		}
	)
	doc.flags.ignore_permissions = True
	doc.flags.ignore_mandatory = True
	doc.insert(ignore_permissions=True)
	frappe.db.commit()
	print("Import File", doc.name)
	return doc.name


def _ensure_pi(item_codes):
	existing = frappe.db.get_value("Purchase Invoice", {"import_file": IMPORT_FILE, "docstatus": 0}, "name")
	if existing:
		frappe.delete_doc("Purchase Invoice", existing, force=1, ignore_permissions=True)
		frappe.db.commit()

	supplier = frappe.db.get_value("Supplier", {}, "name", order_by="creation asc")
	if not supplier:
		s = frappe.get_doc({"doctype": "Supplier", "supplier_name": "MKT Test Supplier", "supplier_group": "All Supplier Groups"})
		s.insert(ignore_permissions=True)
		supplier = s.name

	pi = frappe.new_doc("Purchase Invoice")
	pi.company = _company()
	pi.supplier = supplier
	pi.posting_date = today()
	pi.currency = "JPY"
	if hasattr(pi, "import_file"):
		pi.import_file = IMPORT_FILE
	pi.bill_no = IMPORT_FILE
	pi.set_posting_time = 1

	expense = frappe.db.get_value(
		"Account",
		{"account_type": "Stock", "company": _company(), "is_group": 0},
		"name",
	) or frappe.db.get_value("Company", _company(), "default_inventory_account")

	for car, code in zip(CARS, item_codes):
		pi.append(
			"items",
			{
				"item_code": code,
				"qty": 1,
				"rate": car["yen"],
				"expense_account": expense,
			},
		)
	pi.flags.ignore_permissions = True
	pi.flags.ignore_mandatory = True
	pi.insert(ignore_permissions=True)
	frappe.db.commit()
	print("PI", pi.name, "items", len(pi.items))
	return pi.name


def _make_submit_je(cheque, remark, lines, item_code=None, chassis=None):
	existing = frappe.db.get_value(
		"Journal Entry", {"cheque_no": cheque, "docstatus": ["!=", 2]}, "name"
	)
	if existing:
		ds = frappe.db.get_value("Journal Entry", existing, "docstatus")
		if ds == 1:
			return existing
		frappe.delete_doc("Journal Entry", existing, force=1, ignore_permissions=True)

	doc = frappe.new_doc("Journal Entry")
	doc.voucher_type = "Journal Entry"
	doc.company = _company()
	doc.posting_date = today()
	doc.cheque_no = cheque
	doc.cheque_date = today()
	doc.user_remark = remark
	doc.title = remark[:140]
	if frappe.db.has_column("Journal Entry", "import_file"):
		doc.import_file = IMPORT_FILE
	if item_code and frappe.db.has_column("Journal Entry", "custom_item"):
		doc.custom_item = item_code
	if chassis and frappe.db.has_column("Journal Entry", "custom_chassis_no"):
		doc.custom_chassis_no = chassis
	for line in lines:
		row = dict(line)
		row.setdefault("cost_center", CC)
		doc.append("accounts", row)
	doc.total_debit = sum(flt(r.debit) for r in doc.accounts)
	doc.total_credit = sum(flt(r.credit) for r in doc.accounts)
	doc.difference = abs(doc.total_debit - doc.total_credit)
	doc.flags.ignore_mandatory = True
	doc.flags.ignore_permissions = True
	doc.flags.ignore_links = True
	doc.insert(ignore_permissions=True)
	doc.submit()
	frappe.db.commit()
	return doc.name


def rebuild_n039():
	print("=== REBUILD N.TAN039 ===")
	# ensure wharfage By Formula
	frappe.db.set_value("Costing", "wharfage", "allocation_scope", "By Formula", update_modified=False)
	frappe.db.set_value("Costing", "wharfage", "formula", "{line.tra_duty} * 0.07", update_modified=False)
	frappe.db.commit()

	_ensure_import_file()
	# stamp IF fields
	if frappe.db.exists("Import File", IMPORT_FILE):
		frappe.db.set_value(
			"Import File",
			IMPORT_FILE,
			{"bl_number": BL, "supplier_invoice_no": IMPORT_FILE},
			update_modified=False,
		)

	item_codes = []
	for car in CARS:
		code = _ensure_item(car)
		item_codes.append(code)
		print("Item", code, "m3", car["m3"], "tra", car["tra"])

	_ensure_pi(item_codes)

	# TRA per car (By Vehicle)
	tra_acc = "TRA Duty - JIL"
	tra_pay = frappe.db.get_value("Costing", "tra_duty", "payable_account") or "Tra Duty Payable - JIL"
	for car, code in zip(CARS, item_codes):
		amt = flt(car["tra"])
		_make_submit_je(
			f"ACTUAL|TRA|{car['chassis']}"[:140],
			f"ACTUAL TRA DUTY | {car['chassis']} | {IMPORT_FILE}",
			[
				{
					"account": tra_acc,
					"debit_in_account_currency": amt,
					"debit": amt,
					"account_currency": "TZS",
					"exchange_rate": 1,
				},
				{
					"account": tra_pay,
					"credit_in_account_currency": amt,
					"credit": amt,
					"account_currency": "TZS",
					"exchange_rate": 1,
				},
			],
			item_code=code,
			chassis=car["chassis"],
		)
		print(" TRA", car["chassis"], amt)

	# Bulk Wharfage = Σ(TRA × 0.07)
	wharf_total = sum(flt(c["tra"]) * 0.07 for c in CARS)
	print(f"Wharfage BL bulk = Σ(TRA×0.07) = {wharf_total}")
	wharf_acc = "Wharfage - JIL"
	wharf_pay = frappe.db.get_value("Costing", "wharfage", "payable_account") or "Wharfage Payable - JIL"
	_make_submit_je(
		f"ACTUAL|WHARFAGE|{IMPORT_FILE}"[:140],
		f"ACTUAL WHARFAGE | {IMPORT_FILE} | BL bulk Σ(TRA×0.07)={wharf_total}",
		[
			{
				"account": wharf_acc,
				"debit_in_account_currency": wharf_total,
				"debit": wharf_total,
				"account_currency": "TZS",
				"exchange_rate": 1,
			},
			{
				"account": wharf_pay,
				"credit_in_account_currency": wharf_total,
				"credit": wharf_total,
				"account_currency": "TZS",
				"exchange_rate": 1,
			},
		],
	)

	# IFCV
	from vsd_jan_integration.vsd_jan_international_customization.doctype.import_file_cost_voucher.import_file_cost_voucher import (
		load_from_import_file,
	)

	data = load_from_import_file(IMPORT_FILE)
	doc = frappe.new_doc("Import File Cost Voucher")
	doc.import_file = IMPORT_FILE
	for v in data["vehicles"]:
		doc.append("vehicles", v)
	for e in data["expenses"]:
		doc.append("expenses", e)
	doc._distribute_allocations(keep_manual=False)
	doc.total_expense_amount = sum(flt(r.amount) for r in (doc.expenses or []))
	doc.total_allocated_amount = sum(flt(r.amount) for r in (doc.allocations or []))
	doc.flags.ignore_permissions = True
	doc.insert(ignore_permissions=True)
	frappe.db.commit()

	print("\n=== IFCV", doc.name, "vehicles", len(doc.vehicles), "exp", len(doc.expenses), "alloc", len(doc.allocations))
	wharf_exp = next((e for e in doc.expenses if (e.costing_head or "") == "wharfage"), None)
	print(
		"Wharfage expense:",
		wharf_exp.distribution_method if wharf_exp else None,
		"amount",
		flt(wharf_exp.amount) if wharf_exp else None,
		"expect_bulk",
		wharf_total,
	)

	print("\nchassis | TRA | Wharfage | TRA×0.07 | OK?")
	ok_all = True
	for car in CARS:
		tra_a = next(
			(a for a in doc.allocations if a.chassis_no == car["chassis"] and a.costing_head == "tra_duty"),
			None,
		)
		wh_a = next(
			(a for a in doc.allocations if a.chassis_no == car["chassis"] and a.costing_head == "wharfage"),
			None,
		)
		tra_amt = flt(tra_a.amount) if tra_a else 0
		wh_amt = flt(wh_a.amount) if wh_a else 0
		expect = flt(car["tra"]) * 0.07
		ok = abs(wh_amt - expect) < 1 and abs(tra_amt - car["tra"]) < 1
		ok_all = ok_all and ok
		print(
			car["chassis"],
			"|",
			tra_amt,
			"|",
			round(wh_amt, 2),
			"|",
			round(expect, 2),
			"|",
			"OK" if ok else "DIFF",
		)
	print("ALL OK" if ok_all else "HAS DIFFS")
	return doc.name


def run():
	wipe_all()
	return rebuild_n039()
