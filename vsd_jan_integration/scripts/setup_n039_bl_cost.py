"""Wire N.TAN039/26MSC from 1 BL COST.xlsx for IFCV comparison (draft IFCV, submitted JEs)."""

from __future__ import annotations

import frappe
from frappe.utils import flt, today

IMPORT_FILE = "N.TAN039/26MSC"
CC = "Main - JIL"
USD_TZS = 2700.0  # Excel EXCHANGE RATE

# From 1 BL COST.xlsx NEW COST FILE (exact)
EXCEL = {
	"ZRR70-0198971": {
		"m3": 14.733,
		"tra_duty": 9600000,
		"wharfage": 672000,
		"tpa": 141176,
		"icd_usd": 191.529,
		"shipping_usd": 1384.902,
		"yen": 217000,
		"japan_cost_usd": 261,
	},
	"NSP140-9011378": {
		"m3": 11.396,
		"tra_duty": 8600000,
		"wharfage": 602000,
		"tpa": 141176,
		"icd_usd": 148.148,
		"shipping_usd": 1071.224,
		"yen": 118000,
		"japan_cost_usd": 261,
	},
	"RT1-1006295": {
		"m3": 12.508,
		"tra_duty": 9423484.8,
		"wharfage": 659643.936,
		"tpa": 141176,
		"icd_usd": 162.604,
		"shipping_usd": 1175.752,
		"yen": 172000,
		"japan_cost_usd": 261,
	},
	"GRS180-0026901": {
		"m3": 12.664,
		"tra_duty": 10000000,
		"wharfage": 700000,
		"tpa": 141176,
		"icd_usd": 164.632,
		"shipping_usd": 1190.416,
		"yen": 174000,
		"japan_cost_usd": 261,
	},
	"ANH20-8050726": {
		"m3": 16.991,
		"tra_duty": 11600000,
		"wharfage": 812000,
		"tpa": 141176,
		"icd_usd": 220.883,
		"shipping_usd": 1597.154,
		"yen": 202000,
		"japan_cost_usd": 261,
	},
	"ANH15-0044728": {
		"m3": 17.165,
		"tra_duty": 10700000,
		"wharfage": 749000,
		"tpa": 141176,
		"icd_usd": 223.145,
		"shipping_usd": 1613.51,
		"yen": 234000,
		"japan_cost_usd": 261,
	},
	"TRN215-0021658": {
		"m3": 16.502,
		"tra_duty": 21500000,
		"wharfage": 1505000,
		"tpa": 141176,
		"icd_usd": 214.526,
		"shipping_usd": 1551.188,
		"yen": 1257000,
		"japan_cost_usd": 261,
	},
}


def _item_for_chassis(chassis):
	return frappe.db.get_value("Item", {"custom_chassis_no": chassis}, "name")


def _ensure_payable(label, currency="TZS"):
	from vsd_jan_integration.patches.seed_costing_from_tax_accounts import (
		_company,
		_ensure_payable_account,
	)

	company = _company()
	return _ensure_payable_account(company, label, currency)


def _submit_je(name):
	doc = frappe.get_doc("Journal Entry", name)
	if doc.docstatus == 1:
		return name, False
	for row in doc.accounts:
		if not row.cost_center:
			row.cost_center = CC
	debit = sum(flt(r.debit) for r in doc.accounts)
	credit = sum(flt(r.credit) for r in doc.accounts)
	if debit and not flt(doc.total_debit):
		doc.total_debit = debit
		doc.total_credit = credit
		doc.difference = abs(debit - credit)
	doc.flags.ignore_permissions = True
	doc.submit()
	frappe.db.commit()
	return name, True


def _make_je(cheque_no, remark, lines, multi_currency=0, item_code=None, chassis=None):
	"""lines: list of dicts account/debit/credit/currency/rate/cost_center/user_remark"""
	existing = frappe.db.get_value(
		"Journal Entry", {"cheque_no": cheque_no, "docstatus": ["!=", 2]}, "name"
	)
	if existing:
		ds = frappe.db.get_value("Journal Entry", existing, "docstatus")
		if ds == 1:
			return existing, False
		# rewrite draft
		doc = frappe.get_doc("Journal Entry", existing)
		doc.accounts = []
	else:
		doc = frappe.new_doc("Journal Entry")
		doc.voucher_type = "Journal Entry"
		doc.company = frappe.db.get_single_value("Global Defaults", "default_company")
		doc.posting_date = today()
		doc.cheque_no = cheque_no
		doc.cheque_date = today()

	doc.user_remark = remark
	doc.title = remark[:140]
	doc.multi_currency = multi_currency
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
	if existing:
		doc.save(ignore_permissions=True)
	else:
		doc.insert(ignore_permissions=True)
	frappe.db.commit()
	return doc.name, True


def execute():
	imp = frappe.get_doc("Import File", IMPORT_FILE)
	bl = (imp.bl_number or "").strip() or (imp.supplier_invoice_no or "").strip()
	print("Import File", IMPORT_FILE, "BL", bl)

	# Map chassis -> item
	cars = []
	rows = frappe.db.sql(
		"""
		SELECT pii.item_code, pii.rate, i.custom_chassis_no
		FROM `tabPurchase Invoice Item` pii
		INNER JOIN `tabPurchase Invoice` pi ON pi.name=pii.parent
		INNER JOIN `tabItem` i ON i.name=pii.item_code
		WHERE pi.import_file=%s
		""",
		IMPORT_FILE,
		as_dict=True,
	)
	for r in rows:
		ch = (r.custom_chassis_no or "").strip()
		if ch not in EXCEL:
			print("WARN no excel for", ch, r.item_code)
			continue
		cars.append(frappe._dict({**r, "excel": EXCEL[ch], "chassis": ch}))

	print("cars matched", len(cars))

	# 1) Stamp BL + M3 on Item
	for c in cars:
		frappe.db.set_value(
			"Item",
			c.item_code,
			{"custom_bl": bl, "custom_m3": c.excel["m3"]},
			update_modified=False,
		)
	frappe.db.commit()
	print("stamped BL+M3")

	# 2) Car Costing expected
	from vsd_jan_integration.vsd_jan_international_customization.doctype.car_costing.car_costing import (
		load_from_item,
	)
	from vsd_jan_integration.vsd_jan_international_customization.utils.costing_engine import (
		recalculate_car_costing,
	)

	cc_names = []
	for c in cars:
		x = c.excel
		name = load_from_item(item=c.item_code, import_file=IMPORT_FILE)
		doc = frappe.get_doc("Car Costing", name)
		doc.m3 = x["m3"]
		doc.import_file = IMPORT_FILE
		# set projected on known lines
		proj = {
			"tra_duty": x["tra_duty"],
			"tpa": x["tpa"],
			"wharfage": x["wharfage"],
			"icd": x["icd_usd"],
			"shipping_line": x["shipping_usd"],
			"japan_cost": x["japan_cost_usd"],
		}
		for table in ("tz_costing_lines", "japan_costing_lines"):
			for row in doc.get(table) or []:
				code = (row.costing_code or "").strip()
				if code in proj:
					row.projected_amount = proj[code]
		recalculate_car_costing(doc)
		doc.flags.ignore_permissions = True
		doc.save(ignore_permissions=True)
		# push m3 to item again
		frappe.db.set_value("Item", c.item_code, "custom_m3", x["m3"], update_modified=False)
		cc_names.append(doc.name)
		print("CC", doc.name, c.chassis, "m3", doc.m3)
	frappe.db.commit()

	# 3) Fixed Costing JEs
	from vsd_jan_integration.vsd_jan_international_customization.utils.mkt_fixed_costing import (
		ensure_fixed_costing_for_items,
	)

	codes = [c.item_code for c in cars]
	res = ensure_fixed_costing_for_items(codes, auto_submit_jv=False, import_file=IMPORT_FILE)
	print("fixed batch", len(res["journal_entries"]), "err", res["errors"])
	for je in res["journal_entries"]:
		# ensure cost center
		frappe.db.sql(
			"UPDATE `tabJournal Entry Account` SET cost_center=%s WHERE parent=%s AND IFNULL(cost_center,'')=''",
			(CC, je),
		)
		_submit_je(je)
		print(" submitted FIXED", je)

	# 4) MKT expense JE
	mkt = frappe.db.get_value("Journal Entry", {"cheque_no": "N.TAN039/26MSC", "docstatus": ["<", 2]}, "name")
	if mkt:
		frappe.db.sql(
			"UPDATE `tabJournal Entry Account` SET cost_center=%s WHERE parent=%s AND IFNULL(cost_center,'')=''",
			(CC, mkt),
		)
		# fix totals
		doc = frappe.get_doc("Journal Entry", mkt)
		debit = sum(flt(r.debit) for r in doc.accounts)
		credit = sum(flt(r.credit) for r in doc.accounts)
		if debit and not flt(doc.total_debit):
			frappe.db.set_value(
				"Journal Entry",
				mkt,
				{"total_debit": debit, "total_credit": credit, "difference": abs(debit - credit)},
				update_modified=False,
			)
		if frappe.db.has_column("Journal Entry", "import_file"):
			frappe.db.set_value("Journal Entry", mkt, "import_file", IMPORT_FILE, update_modified=False)
		_submit_je(mkt)
		print(" submitted MKT", mkt, "debit", debit)

	# 5) Post variable actual JEs from Excel (company currency TZS accounts)
	# Align payables currency with expense (TZS)
	for label in ("TRA Duty", "TPA", "Wharfage", "ICD", "Shipping Line"):
		_ensure_payable(label, "TZS")

	acc = {
		"tra_duty": ("TRA Duty - JIL", "Tra Duty Payable - JIL"),
		"tpa": ("TPA - JIL", "Tpa Payable - JIL"),
		"wharfage": ("Wharfage - JIL", "Wharfage Payable - JIL"),
		"icd": ("ICD - JIL", "Icd Payable - JIL"),
		"shipping_line": ("Shipping Line - JIL", "Shipping Line Payable - JIL"),
	}

	# Per-car TRA DUTY (By Vehicle)
	for c in cars:
		x = c.excel
		amt = flt(x["tra_duty"])
		exp, pay = acc["tra_duty"]
		cheque = f"ACTUAL|TRA|{c.chassis}"[:140]
		_make_je(
			cheque,
			f"ACTUAL TRA DUTY | {c.chassis} | {IMPORT_FILE}",
			[
				{
					"account": exp,
					"debit_in_account_currency": amt,
					"debit": amt,
					"account_currency": "TZS",
					"exchange_rate": 1,
					"user_remark": "TRA DUTY",
				},
				{
					"account": pay,
					"credit_in_account_currency": amt,
					"credit": amt,
					"account_currency": "TZS",
					"exchange_rate": 1,
					"user_remark": "TRA DUTY payable",
				},
			],
			item_code=c.item_code,
			chassis=c.chassis,
		)
		_submit_je(frappe.db.get_value("Journal Entry", {"cheque_no": cheque}, "name"))
		print(" TRA", c.chassis, amt)

	# BL-level aggregates for TPA / Wharfage / ICD / Shipping (sum of cars)
	def bl_post(code, excel_key, usd=False):
		total = 0.0
		usd_total = 0.0
		for c in cars:
			if usd:
				usd_total += flt(c.excel[excel_key])
			else:
				total += flt(c.excel[excel_key])
		if usd:
			total = flt(usd_total) * USD_TZS
		exp, pay = acc[code]
		cheque = f"ACTUAL|{code.upper()}|{IMPORT_FILE}"[:140]
		remark_extra = f" (USD {usd_total} @ {USD_TZS})" if usd else ""
		_make_je(
			cheque,
			f"ACTUAL {code.upper()} | {IMPORT_FILE}{remark_extra}",
			[
				{
					"account": exp,
					"debit_in_account_currency": total,
					"debit": total,
					"account_currency": "TZS",
					"exchange_rate": 1,
					"user_remark": code.upper(),
				},
				{
					"account": pay,
					"credit_in_account_currency": total,
					"credit": total,
					"account_currency": "TZS",
					"exchange_rate": 1,
					"user_remark": f"{code} payable",
				},
			],
		)
		_submit_je(frappe.db.get_value("Journal Entry", {"cheque_no": cheque}, "name"))
		print(" BL", code, total, "usd" if usd else "tzs", usd_total if usd else "")

	bl_post("tpa", "tpa", usd=False)
	bl_post("wharfage", "wharfage", usd=False)  # Actual By BL (screenshot)
	bl_post("icd", "icd_usd", usd=True)
	bl_post("shipping_line", "shipping_usd", usd=True)

	# 6) IFCV
	from vsd_jan_integration.vsd_jan_international_customization.doctype.import_file_cost_voucher.import_file_cost_voucher import (
		load_from_import_file,
	)

	data = load_from_import_file(IMPORT_FILE)
	existing = frappe.db.get_value(
		"Import File Cost Voucher", {"import_file": IMPORT_FILE, "docstatus": 0}, "name"
	)
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
	print("IFCV", doc.name, "veh", len(doc.vehicles), "exp", len(doc.expenses), "alloc", len(doc.allocations or []))

	# 7) Comparison report
	print("\n===== COMPARISON vs Excel =====")
	print("Vehicle | Excel M3 | IFCV M3 | Excel Yen | Purchase Price | Excel TRA | notes")
	for c in cars:
		x = c.excel
		vrow = next((v for v in doc.vehicles if v.item == c.item_code), None)
		print(
			c.chassis,
			"|",
			x["m3"],
			"|",
			flt(vrow.m3) if vrow else None,
			"|",
			x["yen"],
			"|",
			flt(vrow.purchase_price) if vrow else None,
			"|",
			x["tra_duty"],
		)

	# Sum allocations by costing for TRA
	tra_alloc = {}
	for a in doc.allocations or []:
		key = (a.item or "", (a.costing_head or a.account or "")[:40])
		tra_alloc[key] = tra_alloc.get(key, 0) + flt(a.amount)

	print("\nSample allocations (first 15):")
	for i, a in enumerate(doc.allocations or []):
		if i >= 15:
			break
		print(a.chassis_no, a.costing_head or a.account, a.currency, a.amount)

	print("\nDONE", doc.name)
	return doc.name
