# Copyright (c) 2026, VV Systems Developer LTD and contributors
# For license information, please see license.txt

"""Seed Costing from Tax Expense Accounts + named Payables for ALL Costings.

Excel / Car Costing sense:
- Tanzania Expected → TZS
- Japan Expected → USD (Excel sheet), even when the GL account is JPY
- IFCV still reads JE/PI amounts in account currency; Actuals are converted to Costing.currency

Also creates missing expense accounts and named Payable GLs for every active Costing.
"""

from __future__ import annotations

import re

import frappe
from frappe.utils import flt


# Prefer updating these existing Costing codes when tax_name / account matches
ACCOUNT_ALIASES = {
	"JPN Expense JPY - JIL": "japan_cost",
	"Inspection JPY - JIL": "inspection",
	"Forwarding JPY - JIL": "forwarding",
}
NAME_ALIASES = {
	"jpn expense": "japan_cost",
	"inspection": "inspection",
	"forwarding": "forwarding",
}

# Excel Car Costing Japan lines are USD (not account currency)
EXCEL_JAPAN_USD_CODES = {
	"japan_cost",
	"inspection",
	"icd",
	"shipping_line",
	"forwarding",
	"thc",
	"freight",
	"vanning",
	"transportation",
	"freight_other",
	"cont_other_value",
	"inv_other_charges",
	"repair_cost",
	"car_expense",
}


def _slug(label: str) -> str:
	s = re.sub(r"[^a-zA-Z0-9]+", "_", (label or "").strip().lower()).strip("_")
	return s[:140] or "tax_costing"


def _company() -> str | None:
	company = frappe.defaults.get_user_default("Company") or frappe.db.get_single_value(
		"Global Defaults", "default_company"
	)
	if not company:
		companies = frappe.get_all("Company", pluck="name")
		company = companies[0] if companies else None
	return company


def _ensure_payable_account(company: str, tax_name: str, currency: str) -> str | None:
	"""Create/get Liability Payable named like the costing, e.g. 'THC Payable - JIL'."""
	if not company or not tax_name:
		return None
	abbr = frappe.db.get_value("Company", company, "abbr") or ""
	label = f"{tax_name} Payable".replace("  ", " ").strip()
	if label.lower().endswith("payable payable"):
		label = label[: -len(" Payable")]
	account_name = f"{label} - {abbr}" if abbr else label

	existing = frappe.db.get_value("Account", {"name": account_name, "company": company}, "name")
	if existing:
		return existing

	parent = (
		frappe.db.get_value(
			"Account",
			{"company": company, "account_type": "Payable", "is_group": 1},
			"name",
			order_by="lft asc",
		)
		or frappe.db.get_value(
			"Account",
			{"company": company, "root_type": "Liability", "is_group": 1},
			"name",
			order_by="lft asc",
		)
	)
	if not parent:
		return frappe.db.get_value("Company", company, "default_payable_account")

	try:
		acc = frappe.new_doc("Account")
		acc.account_name = label
		acc.company = company
		acc.parent_account = parent
		acc.is_group = 0
		acc.root_type = "Liability"
		acc.account_type = "Payable"
		acc.account_currency = currency or frappe.db.get_value("Company", company, "default_currency") or "TZS"
		acc.insert(ignore_permissions=True)
		return acc.name
	except Exception:
		frappe.log_error(title=f"Create payable {account_name}", message=frappe.get_traceback())
		return frappe.db.get_value("Account", {"name": account_name, "company": company}, "name")


def _ensure_expense_account(company: str, tax_name: str, currency: str, account: str | None) -> str | None:
	if account and frappe.db.exists("Account", account):
		return account

	abbr = frappe.db.get_value("Company", company, "abbr") or ""
	currency = currency or "JPY"
	label = f"{tax_name} {currency}".strip()
	account_name = f"{label} - {abbr}" if abbr else label
	if frappe.db.exists("Account", account_name):
		return account_name

	parent = (
		frappe.db.get_value(
			"Account",
			{"company": company, "account_name": ["like", "%Japan%"], "is_group": 1, "root_type": "Expense"},
			"name",
			order_by="lft asc",
		)
		or frappe.db.get_value(
			"Account",
			{"company": company, "root_type": "Expense", "is_group": 1},
			"name",
			order_by="lft desc",
		)
	)
	if not parent:
		return account

	try:
		acc = frappe.new_doc("Account")
		acc.account_name = label
		acc.company = company
		acc.parent_account = parent
		acc.is_group = 0
		acc.root_type = "Expense"
		acc.account_type = "Expense Account"
		acc.account_currency = currency
		acc.insert(ignore_permissions=True)
		return acc.name
	except Exception:
		frappe.log_error(title=f"Create expense {account_name}", message=frappe.get_traceback())
		return frappe.db.get_value("Account", {"name": account_name, "company": company}, "name") or account


def _account_currency(account: str, fallback: str | None = None) -> str:
	if account:
		cur = frappe.db.get_value("Account", account, "account_currency")
		if cur:
			return cur
	return fallback or "TZS"


def _resolve_costing_name(tax_name: str, account: str) -> str:
	if account in ACCOUNT_ALIASES:
		return ACCOUNT_ALIASES[account]
	alias = NAME_ALIASES.get((tax_name or "").strip().lower())
	if alias:
		return alias
	return _slug(tax_name)


def _excel_currency(code: str, region: str, account_currency: str) -> str:
	"""Car Costing / Excel: Japan Expected = USD; Tanzania = TZS."""
	if code in EXCEL_JAPAN_USD_CODES or region == "Japan":
		return "USD"
	return account_currency or "TZS"


def _link_payable(company: str, costing_name: str, currency: str, current: str | None) -> str | None:
	pay = current or ""
	needs = (not pay) or pay.startswith("Creditors")
	if not needs:
		return current
	label = (costing_name or "").strip()
	if not label:
		return current
	new_pay = _ensure_payable_account(company, label, currency or "TZS")
	return new_pay or current


def execute():
	company = _company()
	if not company:
		return

	# 1) Sync Tax Expense Accounts → Costing (+ payables)
	tax_rows = []
	if frappe.db.exists("DocType", "Company Tax Account"):
		tax_rows = frappe.get_all(
			"Company Tax Account",
			filters={"parent": company, "parenttype": "Company"},
			fields=["tax_name", "account", "account_currency", "idx"],
			order_by="idx asc",
		)

	display_base = 200
	for i, row in enumerate(tax_rows or []):
		tax_name = (row.tax_name or "").strip()
		if not tax_name:
			continue
		acc_currency = (row.account_currency or "").strip() or "JPY"
		account = _ensure_expense_account(company, tax_name, acc_currency, (row.account or "").strip() or None)
		if not account or not frappe.db.exists("Account", account):
			frappe.log_error(
				title=f"Tax Costing skip {tax_name}",
				message=f"Expense account missing for tax row {tax_name!r} ({row.account!r})",
			)
			continue

		acc_currency = _account_currency(account, acc_currency)
		code = _resolve_costing_name(tax_name, account)
		by_account = frappe.db.get_value("Costing", {"account": account}, "name")
		if by_account:
			code = by_account

		region = "Japan" if acc_currency == "JPY" else "Tanzania"
		currency = _excel_currency(code, region, acc_currency)

		payable_label = tax_name
		if frappe.db.exists("Costing", code):
			existing_name = frappe.db.get_value("Costing", code, "costing_name")
			if existing_name:
				payable_label = existing_name.title()
		payable = _ensure_payable_account(company, payable_label, acc_currency)

		by_vehicle_labels = {"inspection", "jpn expense", "repair cost", "car expense"}
		scope = "By Vehicle" if tax_name.strip().lower() in by_vehicle_labels else "By BL Equal"

		payload = {
			"account": account,
			"payable_account": payable,
			"currency": currency,
			"region": region,
			"allocation_scope": scope,
			"disabled": 0,
			"display_order": display_base + i,
		}

		if code in ("japan_cost", "inspection", "forwarding") and frappe.db.exists("Costing", code):
			existing_mode = frappe.db.get_value("Costing", code, "entry_mode")
			if existing_mode:
				payload["entry_mode"] = existing_mode
		else:
			payload["entry_mode"] = "Variable"
			if not frappe.db.exists("Costing", code):
				payload["costing_name"] = tax_name.upper()

		if frappe.db.exists("Costing", code):
			frappe.db.set_value("Costing", code, payload, update_modified=False)
		else:
			doc = frappe.get_doc(
				{
					"doctype": "Costing",
					"costing_code": code,
					"costing_name": tax_name.upper(),
					"region": region,
					"entry_mode": "Variable",
					**payload,
				}
			)
			doc.insert(ignore_permissions=True)

	# 2) Japan Excel sense: all Japan-region Costings → USD; link payables on every Costing
	for c in frappe.get_all(
		"Costing",
		filters={"disabled": 0},
		fields=["name", "region", "currency", "account", "costing_name", "payable_account"],
	):
		if c.region == "Japan":
			if c.currency != "USD":
				frappe.db.set_value("Costing", c.name, "currency", "USD", update_modified=False)
			pay_currency = _account_currency(c.account, "JPY")
		else:
			acc_cur = _account_currency(c.account, c.currency or "TZS")
			if c.account and c.currency != acc_cur:
				frappe.db.set_value("Costing", c.name, "currency", acc_cur, update_modified=False)
			pay_currency = acc_cur

		new_pay = _link_payable(company, c.costing_name, pay_currency, c.payable_account)
		if new_pay and new_pay != c.payable_account:
			frappe.db.set_value("Costing", c.name, "payable_account", new_pay, update_modified=False)

	# 3) Fold Custom Field property setters into the Custom Field itself
	_fold_custom_field_property_setters()
	_ensure_demo_exchange_rates()

	frappe.clear_cache(doctype="Costing")
	frappe.clear_cache(doctype="Item")

	if frappe.db.exists("DocType", "Car Costing"):
		frappe.db.sql("UPDATE `tabCar Costing` SET docstatus = 0 WHERE docstatus = 1")

	frappe.db.commit()


def _fold_custom_field_property_setters():
	"""Move Custom Field property setters onto Custom Field rows; delete those PS."""
	targets = [
		("Item", "custom_chassis_no", "in_list_view", 1),
		("Item", "custom_chassis_no", "in_standard_filter", 1),
	]
	for dt, fieldname, prop, value in targets:
		cf_name = frappe.db.get_value("Custom Field", {"dt": dt, "fieldname": fieldname}, "name")
		if cf_name:
			frappe.db.set_value("Custom Field", cf_name, prop, value, update_modified=False)
		ps_name = f"{dt}-{fieldname}-{prop}"
		if frappe.db.exists("Property Setter", ps_name):
			frappe.delete_doc("Property Setter", ps_name, ignore_permissions=True, force=True)


def _ensure_currency_exchange(from_currency, to_currency, rate):
	"""Ensure a buying Currency Exchange exists (idempotent)."""
	if not from_currency or not to_currency or from_currency == to_currency or not rate:
		return
	existing = frappe.db.get_value(
		"Currency Exchange",
		{"from_currency": from_currency, "to_currency": to_currency, "for_buying": 1},
		["name", "exchange_rate"],
		as_dict=True,
	)
	if existing:
		return
	try:
		ce = frappe.new_doc("Currency Exchange")
		ce.from_currency = from_currency
		ce.to_currency = to_currency
		ce.exchange_rate = rate
		ce.for_buying = 1
		ce.for_selling = 1
		ce.date = frappe.utils.getdate("2024-01-01")
		ce.insert(ignore_permissions=True)
	except Exception:
		frappe.log_error(title=f"Currency Exchange {from_currency}->{to_currency}", message=frappe.get_traceback())


def _ensure_demo_exchange_rates():
	"""Ensure USD↔TZS / USD↔JPY exist so Car Costing can auto-pick (Excel sense)."""
	# Prefer deriving USD→TZS from existing JPY→TZS × USD→JPY if available
	jpy_tzs = frappe.db.get_value(
		"Currency Exchange",
		{"from_currency": "JPY", "to_currency": "TZS", "for_buying": 1},
		"exchange_rate",
		order_by="date desc",
	)
	# Excel sample defaults when nothing exists yet
	usd_jpy = 155.0
	usd_tzs = flt(jpy_tzs) * usd_jpy if flt(jpy_tzs) else 2700.0
	_ensure_currency_exchange("USD", "JPY", usd_jpy)
	_ensure_currency_exchange("USD", "TZS", usd_tzs)
	if flt(jpy_tzs):
		_ensure_currency_exchange("JPY", "USD", flt(1.0 / usd_jpy))
