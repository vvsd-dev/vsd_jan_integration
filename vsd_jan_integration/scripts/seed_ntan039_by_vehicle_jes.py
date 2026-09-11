"""Per-car By-Vehicle Journal Entries for N.TAN039/26MSC IFCV testing.

Screenshot Actual=By Vehicle heads get one JE per car so users can map via
Actions → Distribute Manually.

Also remaps Inspection → Inspection JPY, Japan Cost → JPN Expense JPY.
"""

from __future__ import annotations

import frappe
from frappe.utils import flt, today

IMPORT_FILE = "N.TAN039/26MSC"
COMPANY = "Jan International Limited"
CREDIT_TZS = "Cash - JIL"
CREDIT_JPY = "Creditors JPY - JIL"
JPY_RATE = 16.66  # matches ACC-JV-2026-01963

# Excel projected amounts used as practical per-car actuals
EXCEL = {
	"ZRR70-0198971": {"tra_duty": 9600000, "yen": 217000},
	"NSP140-9011378": {"tra_duty": 8600000, "yen": 118000},
	"RT1-1006295": {"tra_duty": 9423484.8, "yen": 172000},
	"GRS180-0026901": {"tra_duty": 10000000, "yen": 174000},
	"ANH20-8050726": {"tra_duty": 11600000, "yen": 202000},
	"ANH15-0044728": {"tra_duty": 10700000, "yen": 234000},
	"TRN215-0021658": {"tra_duty": 21500000, "yen": 1257000},
}

# Fixed By Vehicle (screenshot Actual) — same amount each car
FIXED_TZS = {
	"ex_bond": ("Ex-Bond - JIL", 139314),
	"service": ("Car Service - JIL", 50000),
	"driver_port_to_yard": ("Driver Port to Yard - JIL", 35000),
	"bond_insurance": ("Bond Insurance - JIL", 50000),
}

# Japan By Vehicle — Excel USD projected, posted in JPY for live account mapping
# 170 USD ≈ demo; use equal split of real JV totals for realism
INSPECTION_JPY_EACH = 26640  # 186480 / 7
JPN_EXPENSE_JPY_EACH = 21428.571429  # 150000 / 7


def map_inspection_and_japan_cost_accounts():
	"""Point Costing Heads at live MKT JE accounts from the screenshot."""
	pairs = [
		("inspection", "Inspection JPY - JIL"),
		("japan_cost", "JPN Expense JPY - JIL"),
	]
	for code, account in pairs:
		if not frappe.db.exists("Costing", code):
			continue
		if frappe.db.exists("Account", account):
			frappe.db.set_value("Costing", code, "account", account)
			frappe.db.set_value("Costing", code, "allocation_scope", "By Vehicle")
			print(f"mapped {code} → {account}")


def unlink_combined_japan_je():
	"""Avoid double-count: combined JAN JAPAN JV replaced by per-car JEs."""
	name = "ACC-JV-2026-01963"
	if frappe.db.exists("Journal Entry", name):
		cur = frappe.db.get_value("Journal Entry", name, "import_file")
		if cur == IMPORT_FILE:
			frappe.db.set_value("Journal Entry", name, "import_file", "")
			print(f"unlinked {name} from {IMPORT_FILE}")


def cancel_previous_by_vehicle_jes():
	names = frappe.get_all(
		"Journal Entry",
		filters={"import_file": IMPORT_FILE, "title": ["like", "IFCV BY-VEHICLE%"]},
		fields=["name", "docstatus"],
	)
	for row in names:
		doc = frappe.get_doc("Journal Entry", row.name)
		if doc.docstatus == 1:
			doc.cancel()
		frappe.delete_doc("Journal Entry", doc.name, force=1)
		print(f"removed {row.name}")


def _cars():
	imp = frappe.get_doc("Import File", IMPORT_FILE)
	return frappe.get_all(
		"Item",
		filters={"custom_bl": imp.bl_number, "disabled": 0},
		fields=["name", "custom_chassis_no"],
		order_by="name asc",
	)


def _create_tzs_je(title, account, amount, remark, item=None):
	amount = flt(amount)
	je = frappe.get_doc(
		{
			"doctype": "Journal Entry",
			"voucher_type": "Journal Entry",
			"company": COMPANY,
			"posting_date": today(),
			"import_file": IMPORT_FILE,
			"title": title,
			"user_remark": remark,
			"accounts": [
				{
					"account": account,
					"debit_in_account_currency": amount,
					"debit": amount,
					"user_remark": remark,
				},
				{
					"account": CREDIT_TZS,
					"credit_in_account_currency": amount,
					"credit": amount,
					"user_remark": remark,
				},
			],
		}
	)
	if item and je.meta.has_field("custom_item"):
		je.custom_item = item
		if je.meta.has_field("custom_chassis_no"):
			je.custom_chassis_no = frappe.db.get_value("Item", item, "custom_chassis_no")
	je.insert(ignore_permissions=True)
	je.submit()
	return je.name


def _create_jpy_je(title, account, amount_jpy, remark, item=None):
	amount_jpy = flt(amount_jpy)
	amount_tzs = flt(amount_jpy * JPY_RATE)
	je = frappe.get_doc(
		{
			"doctype": "Journal Entry",
			"voucher_type": "Journal Entry",
			"company": COMPANY,
			"posting_date": today(),
			"import_file": IMPORT_FILE,
			"title": title,
			"user_remark": remark,
			"multi_currency": 1,
			"accounts": [
				{
					"account": account,
					"account_currency": "JPY",
					"exchange_rate": JPY_RATE,
					"debit_in_account_currency": amount_jpy,
					"debit": amount_tzs,
					"user_remark": remark,
				},
				{
					"account": CREDIT_JPY,
					"account_currency": "JPY",
					"exchange_rate": JPY_RATE,
					"credit_in_account_currency": amount_jpy,
					"credit": amount_tzs,
					"party_type": "Supplier",
					"party": "JAN JAPAN",
					"user_remark": remark,
				},
			],
		}
	)
	if item and je.meta.has_field("custom_item"):
		je.custom_item = item
		if je.meta.has_field("custom_chassis_no"):
			je.custom_chassis_no = frappe.db.get_value("Item", item, "custom_chassis_no")
	je.insert(ignore_permissions=True)
	je.submit()
	return je.name


def create_per_car_jes():
	created = []
	for car in _cars():
		chassis = car.custom_chassis_no
		item = car.name
		excel = EXCEL.get(chassis) or {}
		remark_base = f"{chassis} | {item}"

		# TRA Duty (variable per car)
		if excel.get("tra_duty"):
			title = f"IFCV BY-VEHICLE TRA Duty | {chassis}"
			name = _create_tzs_je(title, "TRA Duty - JIL", excel["tra_duty"], remark_base, item=item)
			created.append(name)
			print("OK", name, title)

		for code, (account, amount) in FIXED_TZS.items():
			title = f"IFCV BY-VEHICLE {code} | {chassis}"
			name = _create_tzs_je(title, account, amount, remark_base, item=item)
			created.append(name)
			print("OK", name, title)

		# Inspection (MKT → Inspection Costing Head)
		title = f"IFCV BY-VEHICLE Inspection | {chassis}"
		name = _create_jpy_je(title, "Inspection JPY - JIL", INSPECTION_JPY_EACH, remark_base, item=item)
		created.append(name)
		print("OK", name, title)

		# JPN Expense → Japan Cost
		title = f"IFCV BY-VEHICLE Japan Cost | {chassis}"
		name = _create_jpy_je(title, "JPN Expense JPY - JIL", JPN_EXPENSE_JPY_EACH, remark_base, item=item)
		created.append(name)
		print("OK", name, title)

	return created


def refresh_ifcv():
	from vsd_jan_integration.vsd_jan_international_customization.doctype.import_file_cost_voucher.import_file_cost_voucher import (
		load_from_import_file,
	)

	ifcv_name = frappe.db.get_value(
		"Import File Cost Voucher",
		{"import_file": IMPORT_FILE, "docstatus": 0},
		"name",
		order_by="modified desc",
	)
	if not ifcv_name:
		frappe.throw("No draft IFCV")

	doc = frappe.get_doc("Import File Cost Voucher", ifcv_name)
	payload = load_from_import_file(IMPORT_FILE)

	doc.set("vehicles", [])
	for v in payload["vehicles"]:
		doc.append("vehicles", v)

	doc.set("expenses", [])
	for e in payload["expenses"]:
		# Method comes from Costing.allocation_scope
		doc.append(
			"expenses",
			{
				"expense_account": e["expense_account"],
				"description": e.get("description"),
				"amount": e["amount"],
				"source": e.get("source"),
				"costing_head": e.get("costing_head"),
				"costing_code": e.get("costing_code"),
				"distribution_method": e.get("distribution_method") or "By BL Equal",
				"linked_item": e.get("linked_item"),
				"remarks": e.get("description"),
			},
		)

	doc.save(ignore_permissions=True)
	frappe.db.commit()
	manual = sum(1 for r in doc.expenses if r.distribution_method == "By Vehicle Manual")
	print(
		f"IFCV {doc.name}: vehicles={len(doc.vehicles)} expenses={len(doc.expenses)} "
		f"by_vehicle_manual={manual} total={flt(doc.total_expense_amount)}"
	)
	return doc.name


def run(reset=True):
	map_inspection_and_japan_cost_accounts()
	unlink_combined_japan_je()
	if reset:
		cancel_previous_by_vehicle_jes()
	jes = create_per_car_jes()
	frappe.db.commit()
	ifcv = refresh_ifcv()
	return {"jes": jes, "count": len(jes), "ifcv": ifcv}


if __name__ == "__main__":
	run()
