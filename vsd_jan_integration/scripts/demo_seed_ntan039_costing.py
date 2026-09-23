# Copyright (c) 2026, VV Systems Developer LTD and contributors
# For license information, please see license.txt

"""
Demo seed: N.TAN039/26MSC (BL MEDUW3445865) costing journals + IFCV.

Recreates the same "1 BL COST.xlsx" actual JEs we used on go:
  - Per-car TRA Duty (By Vehicle)
  - Bulk Wharfage = Σ(TRA × 0.07)  (By Formula on Costing Head)
  - BL TPA Equal, ICD / Shipping Line (M3, USD→TZS)
  - Fixed-costing JEs (bond / service / driver / …)
  - Draft Import File Cost Voucher with allocations

Assumes Items for the 7 chassis already exist (from MKT / Mukechi import).
Does NOT wipe the whole site — only replaces this BL's ACTUAL|* JEs + draft IFCV.

---------------------------------------------------------
Run on demo (or any) site:

  bench --site <SITE> execute \\
    vsd_jan_integration.scripts.demo_seed_ntan039_costing.run

Optional kwargs:

  # keep existing ACTUAL JEs / IFCV and only fill missing
  bench --site <SITE> execute \\
    vsd_jan_integration.scripts.demo_seed_ntan039_costing.run \\
    --kwargs '{"reset": 0}'

---------------------------------------------------------
"""

from __future__ import annotations

import frappe
from frappe.utils import cint, flt, today

IMPORT_FILE = "N.TAN039/26MSC"
BL = "MEDUW3445865"
USD_TZS = 2700.0  # Excel EXCHANGE RATE used for ICD / Shipping USD→TZS

# From 1 BL COST.xlsx NEW COST FILE (exact)
CARS = [
	{
		"chassis": "ZRR70-0198971",
		"maker": "TOYOTA NOAH",
		"m3": 14.733,
		"tra_duty": 9600000,
		"wharfage": 672000,
		"tpa": 141176,
		"icd_usd": 191.529,
		"shipping_usd": 1384.902,
		"yen": 217000,
		"japan_cost_usd": 261,
	},
	{
		"chassis": "NSP140-9011378",
		"maker": "TOYOTA PORTE",
		"m3": 11.396,
		"tra_duty": 8600000,
		"wharfage": 602000,
		"tpa": 141176,
		"icd_usd": 148.148,
		"shipping_usd": 1071.224,
		"yen": 118000,
		"japan_cost_usd": 261,
	},
	{
		"chassis": "RT1-1006295",
		"maker": "HONDA CROSSROAD",
		"m3": 12.508,
		"tra_duty": 9423484.8,
		"wharfage": 659643.936,
		"tpa": 141176,
		"icd_usd": 162.604,
		"shipping_usd": 1175.752,
		"yen": 172000,
		"japan_cost_usd": 261,
	},
	{
		"chassis": "GRS180-0026901",
		"maker": "TOYOTA CROWN",
		"m3": 12.664,
		"tra_duty": 10000000,
		"wharfage": 700000,
		"tpa": 141176,
		"icd_usd": 164.632,
		"shipping_usd": 1190.416,
		"yen": 174000,
		"japan_cost_usd": 261,
	},
	{
		"chassis": "ANH20-8050726",
		"maker": "TOYOTA ALPHARD",
		"m3": 16.991,
		"tra_duty": 11600000,
		"wharfage": 812000,
		"tpa": 141176,
		"icd_usd": 220.883,
		"shipping_usd": 1597.154,
		"yen": 202000,
		"japan_cost_usd": 261,
	},
	{
		"chassis": "ANH15-0044728",
		"maker": "TOYOTA ALPHARD",
		"m3": 17.165,
		"tra_duty": 10700000,
		"wharfage": 749000,
		"tpa": 141176,
		"icd_usd": 223.145,
		"shipping_usd": 1613.51,
		"yen": 234000,
		"japan_cost_usd": 261,
	},
	{
		"chassis": "TRN215-0021658",
		"maker": "TOYOTA HILUX SURF",
		"m3": 16.502,
		"tra_duty": 21500000,
		"wharfage": 1505000,
		"tpa": 141176,
		"icd_usd": 214.526,
		"shipping_usd": 1551.188,
		"yen": 1257000,
		"japan_cost_usd": 261,
	},
]


def _company():
	return frappe.db.get_single_value("Global Defaults", "default_company")


def _cost_center():
	company = _company()
	cc = frappe.db.get_value("Company", company, "cost_center")
	if cc:
		return cc
	return frappe.db.get_value("Cost Center", {"company": company, "is_group": 0}, "name")


def _abbr():
	return frappe.db.get_value("Company", _company(), "abbr") or "JIL"


def _accounts_for(code: str):
	"""Resolve expense + payable from Costing Head, with sensible fallbacks."""
	row = frappe.db.get_value(
		"Costing",
		{"costing_code": code, "disabled": 0},
		["account", "payable_account", "costing_name"],
		as_dict=True,
	)
	abbr = _abbr()
	fallbacks = {
		"tra_duty": (f"TRA Duty - {abbr}", f"Tra Duty Payable - {abbr}"),
		"wharfage": (f"Wharfage - {abbr}", f"Wharfage Payable - {abbr}"),
		"tpa": (f"TPA - {abbr}", f"Tpa Payable - {abbr}"),
		"icd": (f"ICD - {abbr}", f"Icd Payable - {abbr}"),
		"shipping_line": (f"Shipping Line - {abbr}", f"Shipping Line Payable - {abbr}"),
	}
	exp_fb, pay_fb = fallbacks.get(code, (None, None))
	exp = (row.account if row else None) or exp_fb
	pay = (row.payable_account if row else None) or pay_fb
	if not exp or not frappe.db.exists("Account", exp):
		frappe.throw(f"Missing expense Account for costing_code={code} (tried {exp})")
	if not pay or not frappe.db.exists("Account", pay):
		# last resort: company default payable
		pay = frappe.db.get_value("Company", _company(), "default_payable_account")
	return exp, pay


def _item_for_chassis(chassis: str):
	name = frappe.db.get_value("Item", {"custom_chassis_no": chassis, "disabled": 0}, "name")
	if name:
		return name
	# fallback: item_code contains chassis
	return frappe.db.get_value("Item", {"name": ["like", f"%{chassis}%"], "disabled": 0}, "name")


def _ensure_import_file():
	if frappe.db.exists("Import File", IMPORT_FILE):
		frappe.db.set_value(
			"Import File",
			IMPORT_FILE,
			{
				"bl_number": BL,
				"supplier_invoice_no": IMPORT_FILE,
				"import_file_number": IMPORT_FILE,
			},
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
	print("created Import File", doc.name)
	return doc.name


def _configure_costing_heads():
	"""Wharfage By Formula = TRA × 7% (demo expectation)."""
	if frappe.db.exists("Costing", "wharfage"):
		frappe.db.set_value("Costing", "wharfage", "allocation_scope", "By Formula", update_modified=False)
		frappe.db.set_value(
			"Costing",
			"wharfage",
			"formula",
			"{line.tra_duty} * 0.07",
			update_modified=False,
		)
	if frappe.db.exists("Costing", "tra_duty"):
		frappe.db.set_value("Costing", "tra_duty", "allocation_scope", "By Vehicle", update_modified=False)
	frappe.db.commit()


def _cancel_delete_je(name: str):
	try:
		ds = frappe.db.get_value("Journal Entry", name, "docstatus")
		if ds == 1:
			doc = frappe.get_doc("Journal Entry", name)
			doc.flags.ignore_permissions = True
			doc.cancel()
		frappe.delete_doc("Journal Entry", name, force=1, ignore_permissions=True)
		frappe.db.commit()
	except Exception as e:
		print(f"  skip JE {name}: {e}")


def reset_bl_docs():
	"""Remove prior ACTUAL|* / IFCV-TEST JEs and draft IFCVs for this Import File only."""
	print("=== RESET BL DOCS (N.TAN039 only) ===")
	names = set(
		frappe.db.sql(
			"""
			SELECT name FROM `tabJournal Entry`
			WHERE docstatus < 2 AND (
				IFNULL(import_file,'') = %s
				OR cheque_no LIKE %s
				OR cheque_no LIKE %s
				OR cheque_no LIKE %s
				OR cheque_no LIKE %s
				OR cheque_no LIKE %s
				OR title LIKE %s
				OR title LIKE %s
				OR title LIKE %s
			)
			""",
			(
				IMPORT_FILE,
				f"ACTUAL|%|{IMPORT_FILE}%",
				f"ACTUAL|WHARFAGE|{IMPORT_FILE}%",
				f"ACTUAL|TPA|{IMPORT_FILE}%",
				f"ACTUAL|ICD|{IMPORT_FILE}%",
				f"ACTUAL|SHIPPING|{IMPORT_FILE}%",
				f"%{IMPORT_FILE}%",
				"IFCV TEST%",
				"IFCV BY-VEHICLE%",
			),
			pluck=True,
		)
		or []
	)
	# Per-car TRA cheque nos
	for car in CARS:
		extra = frappe.db.get_value(
			"Journal Entry",
			{"cheque_no": f"ACTUAL|TRA|{car['chassis']}", "docstatus": ["<", 2]},
			"name",
		)
		if extra:
			names.add(extra)
		# fixed costing JEs tied to this item (if any)
		item = _item_for_chassis(car["chassis"])
		if item:
			for je in frappe.get_all(
				"Journal Entry",
				filters={"cheque_no": ["like", f"FIXED|{item}%"], "docstatus": ["<", 2]},
				pluck="name",
			) or []:
				names.add(je)
			for je in frappe.get_all(
				"Journal Entry",
				filters={"custom_item": item, "docstatus": ["<", 2], "user_remark": ["like", "FIXED COSTING%"]},
				pluck="name",
			) or []:
				names.add(je)

	print(f"JEs to remove: {len(names)}")
	for name in sorted(names):
		_cancel_delete_je(name)

	ifcvs = frappe.get_all(
		"Import File Cost Voucher",
		filters={"import_file": IMPORT_FILE},
		pluck="name",
	)
	for name in ifcvs:
		try:
			ds = frappe.db.get_value("Import File Cost Voucher", name, "docstatus")
			if ds == 1:
				doc = frappe.get_doc("Import File Cost Voucher", name)
				doc.flags.ignore_permissions = True
				doc.cancel()
			frappe.delete_doc("Import File Cost Voucher", name, force=1, ignore_permissions=True)
			print("removed IFCV", name)
		except Exception as e:
			print(f"  skip IFCV {name}: {e}")
	frappe.db.commit()


def _make_submit_je(cheque: str, remark: str, lines: list, item_code=None, chassis=None):
	existing = frappe.db.get_value(
		"Journal Entry", {"cheque_no": cheque, "docstatus": ["!=", 2]}, "name"
	)
	if existing:
		ds = frappe.db.get_value("Journal Entry", existing, "docstatus")
		if ds == 1:
			return existing, False
		frappe.delete_doc("Journal Entry", existing, force=1, ignore_permissions=True)

	cc = _cost_center()
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
		row.setdefault("cost_center", cc)
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
	return doc.name, True


def _pair(code: str, amount: float, remark_tag: str):
	exp, pay = _accounts_for(code)
	amt = flt(amount)
	return [
		{
			"account": exp,
			"debit_in_account_currency": amt,
			"debit": amt,
			"account_currency": "TZS",
			"exchange_rate": 1,
			"user_remark": remark_tag,
		},
		{
			"account": pay,
			"credit_in_account_currency": amt,
			"credit": amt,
			"account_currency": "TZS",
			"exchange_rate": 1,
			"user_remark": f"{remark_tag} payable",
		},
	]


def stamp_items(cars_resolved: list):
	for c in cars_resolved:
		frappe.db.set_value(
			"Item",
			c.item_code,
			{
				"custom_bl": BL,
				"custom_m3": c.excel["m3"],
				"custom_price": c.excel["yen"],
			},
			update_modified=False,
		)
	frappe.db.commit()
	print(f"stamped BL+M3+yen on {len(cars_resolved)} items")


def create_actual_jes(cars_resolved: list):
	created = []

	# Per-car TRA
	for c in cars_resolved:
		amt = flt(c.excel["tra_duty"])
		cheque = f"ACTUAL|TRA|{c.chassis}"[:140]
		name, _ = _make_submit_je(
			cheque,
			f"ACTUAL TRA DUTY | {c.chassis} | {IMPORT_FILE}",
			_pair("tra_duty", amt, "TRA DUTY"),
			item_code=c.item_code,
			chassis=c.chassis,
		)
		created.append(name)
		print(" TRA", c.chassis, amt, "→", name)

	# Bulk Wharfage = Σ(TRA × 0.07) — matches By Formula head
	wharf_total = sum(flt(c.excel["tra_duty"]) * 0.07 for c in cars_resolved)
	name, _ = _make_submit_je(
		f"ACTUAL|WHARFAGE|{IMPORT_FILE}"[:140],
		f"ACTUAL WHARFAGE | {IMPORT_FILE} | BL bulk Σ(TRA×0.07)={wharf_total}",
		_pair("wharfage", wharf_total, "WHARFAGE"),
	)
	created.append(name)
	print(" WHARFAGE bulk", wharf_total, "→", name)

	# BL TPA (equal total)
	tpa_total = sum(flt(c.excel["tpa"]) for c in cars_resolved)
	name, _ = _make_submit_je(
		f"ACTUAL|TPA|{IMPORT_FILE}"[:140],
		f"ACTUAL TPA | {IMPORT_FILE}",
		_pair("tpa", tpa_total, "TPA"),
	)
	created.append(name)
	print(" TPA", tpa_total, "→", name)

	# ICD / Shipping — Excel USD × USD_TZS posted in TZS
	icd_usd = sum(flt(c.excel["icd_usd"]) for c in cars_resolved)
	icd_tzs = flt(icd_usd) * USD_TZS
	name, _ = _make_submit_je(
		f"ACTUAL|ICD|{IMPORT_FILE}"[:140],
		f"ACTUAL ICD | {IMPORT_FILE} (USD {icd_usd} @ {USD_TZS})",
		_pair("icd", icd_tzs, "ICD"),
	)
	created.append(name)
	print(" ICD", icd_tzs, f"(USD {icd_usd})", "→", name)

	ship_usd = sum(flt(c.excel["shipping_usd"]) for c in cars_resolved)
	ship_tzs = flt(ship_usd) * USD_TZS
	name, _ = _make_submit_je(
		f"ACTUAL|SHIPPING|{IMPORT_FILE}"[:140],
		f"ACTUAL SHIPPING LINE | {IMPORT_FILE} (USD {ship_usd} @ {USD_TZS})",
		_pair("shipping_line", ship_tzs, "SHIPPING"),
	)
	created.append(name)
	print(" SHIPPING", ship_tzs, f"(USD {ship_usd})", "→", name)

	return created


def create_fixed_jes(item_codes: list):
	from vsd_jan_integration.vsd_jan_international_customization.utils.mkt_fixed_costing import (
		ensure_fixed_costing_for_items,
	)

	cc = _cost_center()
	res = ensure_fixed_costing_for_items(item_codes, auto_submit_jv=False, import_file=IMPORT_FILE)
	print("fixed JEs created", len(res.get("journal_entries") or []), "errors", res.get("errors"))
	submitted = []
	for je in res.get("journal_entries") or []:
		frappe.db.sql(
			"UPDATE `tabJournal Entry Account` SET cost_center=%s WHERE parent=%s AND IFNULL(cost_center,'')=''",
			(cc, je),
		)
		if frappe.db.has_column("Journal Entry", "import_file"):
			frappe.db.set_value("Journal Entry", je, "import_file", IMPORT_FILE, update_modified=False)
		ds = frappe.db.get_value("Journal Entry", je, "docstatus")
		if ds == 0:
			doc = frappe.get_doc("Journal Entry", je)
			doc.flags.ignore_permissions = True
			doc.submit()
			frappe.db.commit()
		submitted.append(je)
		print(" FIXED", je)
	return submitted


def create_ifcv():
	from vsd_jan_integration.vsd_jan_international_customization.doctype.import_file_cost_voucher.import_file_cost_voucher import (
		load_from_import_file,
	)

	data = load_from_import_file(IMPORT_FILE)
	existing = frappe.db.get_value(
		"Import File Cost Voucher",
		{"import_file": IMPORT_FILE, "docstatus": 0},
		"name",
	)
	if existing:
		doc = frappe.get_doc("Import File Cost Voucher", existing)
		doc.set("vehicles", [])
		doc.set("expenses", [])
		doc.set("allocations", [])
	else:
		doc = frappe.new_doc("Import File Cost Voucher")
		doc.import_file = IMPORT_FILE

	for v in data.get("vehicles") or []:
		doc.append("vehicles", v)
	for e in data.get("expenses") or []:
		doc.append("expenses", e)

	if hasattr(doc, "_distribute_allocations"):
		doc._distribute_allocations(keep_manual=False)

	doc.total_expense_amount = sum(flt(r.amount) for r in (doc.expenses or []))
	doc.total_allocated_amount = sum(flt(r.amount) for r in (doc.allocations or []))
	doc.flags.ignore_permissions = True
	if existing:
		doc.save(ignore_permissions=True)
	else:
		doc.insert(ignore_permissions=True)
	frappe.db.commit()
	return doc.name, len(doc.vehicles or []), len(doc.expenses or []), len(doc.allocations or [])


def run(reset=1):
	"""Entry point for bench execute.

	reset=1 (default): cancel/delete prior ACTUAL JEs + draft IFCV for this BL, then recreate.
	reset=0: skip wipe; create missing only (submitted ACTUAL cheque_nos are kept).
	"""
	frappe.set_user("Administrator")
	frappe.flags.ignore_permissions = True

	print("=== DEMO SEED N.TAN039/26MSC COSTING ===")
	print("company:", _company(), "cost center:", _cost_center())

	_configure_costing_heads()
	_ensure_import_file()

	if cint(reset):
		reset_bl_docs()

	# Resolve items
	cars_resolved = []
	missing = []
	for car in CARS:
		item = _item_for_chassis(car["chassis"])
		if not item:
			missing.append(car["chassis"])
			continue
		cars_resolved.append(
			frappe._dict(item_code=item, chassis=car["chassis"], excel=car, maker=car["maker"])
		)

	if missing:
		frappe.throw(
			"Missing Items for chassis (import MKT/Mukechi first):\n- " + "\n- ".join(missing)
		)

	print(f"cars matched {len(cars_resolved)}/{len(CARS)}")
	stamp_items(cars_resolved)

	actual = create_actual_jes(cars_resolved)
	fixed = create_fixed_jes([c.item_code for c in cars_resolved])
	ifcv_name, n_veh, n_exp, n_alloc = create_ifcv()

	print("\n===== DONE =====")
	print("Import File:", IMPORT_FILE, "BL:", BL)
	print("ACTUAL JEs:", len(actual))
	print("FIXED JEs:", len(fixed))
	print(f"IFCV: {ifcv_name}  vehicles={n_veh} expenses={n_exp} allocations={n_alloc}")
	print(f"Open: /app/import-file-cost-voucher/{ifcv_name}")
	print("View by Vehicle → Noah ZRR70-0198971 for TRA / Wharfage check")
	return {
		"import_file": IMPORT_FILE,
		"ifcv": ifcv_name,
		"actual_jes": actual,
		"fixed_jes": fixed,
		"vehicles": n_veh,
		"expenses": n_exp,
		"allocations": n_alloc,
	}


# Alias used by older docs
execute = run
