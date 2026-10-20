# Copyright (c) 2026, VV Systems Developer LTD and contributors
# For license information, please see license.txt

"""Jan Sale Report — SALE REPORT NEW 2024 2025.xlsx columns for sold vehicles.

Only rows with a submitted Sales Invoice for that vehicle appear.
Sale price / VAT 18% / selling-side formula fills use that SI figure only
(shared helpers with Jan BL Costing — never Car Costing Expected).

Duty = TRA DUTY (same Item Actual → IFCV → JE resolution as Jan BL Costing).
Expense = Total EXP (sum of all Costing heads after FX, same as BL Costing).
Purchase Price = car purchase (PI / Item custom_price) — was the Excel "YEN" column.
Total Cost = Expense + Purchase Price.

Currency filter TZS / YEN / USD converts every money column via Currency Exchange
on the sale (SI) date — same mechanism as costing_report.
"""

from __future__ import annotations

from typing import Any

import frappe
from frappe import _
from frappe.utils import date_diff, flt, getdate

from vsd_jan_integration.api import costing_report as cr

DISPLAY_CURRENCIES = cr.DISPLAY_CURRENCIES
CURRENCY_MAP = cr.CURRENCY_MAP
SELLING_NATIVE_CURRENCY = cr.SELLING_NATIVE_CURRENCY
PURCHASE_FALLBACK_CURRENCY = cr.PURCHASE_FALLBACK_CURRENCY

TRA_DUTY_CODES = ("tra_duty", "TRA DUTY", "tra duty")


def get_filters():
	return [
		{
			"fieldname": "currency",
			"label": _("Currency"),
			"fieldtype": "Select",
			"options": "\n".join(DISPLAY_CURRENCIES),
			"default": "TZS",
			"reqd": 1,
		},
		{
			"fieldname": "import_file",
			"label": _("Import File"),
			"fieldtype": "Link",
			"options": "Import File",
		},
		{
			"fieldname": "from_date",
			"label": _("From Date"),
			"fieldtype": "Date",
		},
		{
			"fieldname": "to_date",
			"label": _("To Date"),
			"fieldtype": "Date",
		},
		{
			"fieldname": "chassis",
			"label": _("Chassis"),
			"fieldtype": "Data",
		},
		{
			"fieldname": "customer",
			"label": _("Buyer"),
			"fieldtype": "Link",
			"options": "Customer",
		},
	]


def _money_col(label: str, fieldname: str, width: int = 120) -> dict:
	return cr._money_col(label, fieldname, width)


def get_columns(display_currency="TZS"):
	"""Sale Report Excel columns (FX via Currency filter — no multi-ccy aggregates)."""
	ccy = display_currency or "TZS"
	_iso = CURRENCY_MAP.get(ccy, ccy)
	cols = [
		{"label": "DAY", "fieldname": "day", "fieldtype": "Int", "width": 60},
		{"label": "STOCK", "fieldname": "stock", "fieldtype": "Data", "width": 100},
		{"label": "Chassis No.", "fieldname": "chassis", "fieldtype": "Data", "width": 150},
		{"label": "MAKE", "fieldname": "make", "fieldtype": "Data", "width": 120},
		{"label": "Description", "fieldname": "description", "fieldtype": "Data", "width": 120},
		{"label": "Model", "fieldname": "model", "fieldtype": "Data", "width": 90},
		{"label": "Color", "fieldname": "color", "fieldtype": "Data", "width": 90},
		{"label": "Mileage", "fieldname": "mileage", "fieldtype": "Float", "width": 90},
		{"label": "SOLD", "fieldname": "sold", "fieldtype": "Data", "width": 90},
		{"label": "YARD DATE", "fieldname": "yard_date", "fieldtype": "Date", "width": 110},
		{"label": "TODAY", "fieldname": "sale_date", "fieldtype": "Date", "width": 110},
		{"label": "Buyer Name", "fieldname": "buyer_name", "fieldtype": "Data", "width": 160},
		{"label": "Contact #", "fieldname": "contact", "fieldtype": "Data", "width": 120},
		{"label": "DAYS", "fieldname": "days", "fieldtype": "Int", "width": 70},
		{
			"label": _("Currency"),
			"fieldname": "currency",
			"fieldtype": "Link",
			"options": "Currency",
			"hidden": 1,
			"width": 80,
		},
		_money_col(_("SALE PRICE"), "sale_price", 130),
		_money_col(_("Duty"), "duty", 120),
		_money_col(_("Expense"), "expense", 120),
		# Was "YEN" in Excel — this is the car Purchase Price (PI / Item custom_price)
		_money_col(_("Purchase Price"), "purchase_price", 130),
		_money_col(_("LOCAL EXP"), "local_exp", 110),
		_money_col(_("VAT 18 %"), "vat_18", 110),
		_money_col(_("VAT 20 %"), "vat_20", 110),
		_money_col(_("REAL PRICE"), "real_price", 120),
		# Total Cost = Expense (Total EXP) + Purchase Price (car price)
		_money_col(_("Total Cost"), "total_cost", 130),
		{"label": "M3", "fieldname": "m3", "fieldtype": "Float", "width": 70},
		{"label": "Item", "fieldname": "item", "fieldtype": "Link", "options": "Item", "width": 220},
		{
			"label": "Sales Invoice",
			"fieldname": "sales_invoice",
			"fieldtype": "Link",
			"options": "Sales Invoice",
			"width": 140,
		},
	]
	for col in cols:
		if col.get("fieldtype") == "Currency":
			col["currency"] = _iso
	return cols


def _tra_duty_code(heads: list[dict]) -> str | None:
	by_code = {h["costing_code"]: h for h in heads}
	for code in TRA_DUTY_CODES:
		if code in by_code:
			return code
	for h in heads:
		name = (h.get("costing_name") or "").strip().lower()
		code = (h.get("costing_code") or "").strip().lower()
		if name == "tra duty" or code == "tra_duty":
			return h["costing_code"]
	return None


def _load_submitted_sales(filters: frappe._dict) -> list[dict]:
	"""Latest submitted SI line per vehicle item (one row per sold car)."""
	clauses = ["si.docstatus = 1", "IFNULL(sii.item_code, '') != ''"]
	params: dict[str, Any] = {}

	if filters.get("from_date"):
		clauses.append("si.posting_date >= %(from_date)s")
		params["from_date"] = filters.from_date
	if filters.get("to_date"):
		clauses.append("si.posting_date <= %(to_date)s")
		params["to_date"] = filters.to_date
	if filters.get("customer"):
		clauses.append("si.customer = %(customer)s")
		params["customer"] = filters.customer
	if filters.get("chassis"):
		clauses.append(
			"(IFNULL(i.custom_chassis_no, '') LIKE %(chassis)s OR sii.item_code LIKE %(chassis)s)"
		)
		params["chassis"] = f"%{filters.chassis}%"

	# Optional Import File filter via Item BL / Car Costing / JE
	import_file = filters.get("import_file")
	item_scope = None
	if import_file:
		from vsd_jan_integration.vsd_jan_international_customization.doctype.import_file_cost_voucher.import_file_cost_voucher import (
			get_vehicles_for_import_file,
		)

		item_scope = [v.name for v in get_vehicles_for_import_file(import_file)]
		if not item_scope:
			return []
		clauses.append("sii.item_code IN %(items)s")
		params["items"] = item_scope

	has_item = frappe.db.table_exists("Item")
	join_item = "LEFT JOIN `tabItem` i ON i.name = sii.item_code" if has_item else ""

	rows = frappe.db.sql(
		f"""
		SELECT
			sii.item_code as item,
			sii.base_rate,
			sii.rate,
			si.conversion_rate,
			si.name as sales_invoice,
			si.posting_date as sale_date,
			si.customer,
			si.customer_name as buyer_name,
			si.contact_mobile as contact_mobile,
			si.contact_person as contact_person,
			si.modified
		FROM `tabSales Invoice Item` sii
		INNER JOIN `tabSales Invoice` si ON si.name = sii.parent
		{join_item}
		WHERE {' AND '.join(clauses)}
		ORDER BY si.posting_date DESC, si.modified DESC
		""",
		params,
		as_dict=True,
	)

	# One row per item — latest SI wins
	out: list[dict] = []
	seen: set[str] = set()
	for r in rows:
		if r.item in seen:
			continue
		seen.add(r.item)
		base = flt(r.base_rate)
		if not base:
			base = flt(r.rate) * (flt(r.conversion_rate) or 1.0)
		r.sale_price_native = base
		out.append(r)
	return out


def _customer_contact(customer: str, si_row: dict) -> str:
	contact = (si_row.get("contact_mobile") or "").strip()
	if contact:
		return contact
	if not customer:
		return ""
	# Prefer default Customer mobile / phone
	for field in ("mobile_no", "customer_primary_contact"):
		if frappe.db.has_column("Customer", field):
			val = frappe.db.get_value("Customer", customer, field)
			if val and field == "mobile_no":
				return str(val)
			if val and field == "customer_primary_contact":
				mobile = frappe.db.get_value("Contact", val, "mobile_no")
				if mobile:
					return str(mobile)
	phone = frappe.db.get_value("Customer", customer, "mobile_no") if frappe.db.has_column("Customer", "mobile_no") else None
	return str(phone or "")


@frappe.whitelist()
def execute(filters=None):
	frappe.has_permission("Sales Invoice", "read", throw=True)
	if isinstance(filters, str):
		import json

		filters = json.loads(filters) if filters else {}
	filters = frappe._dict(filters or {})

	display = (filters.get("currency") or "TZS").upper()
	if display not in DISPLAY_CURRENCIES:
		frappe.throw(_("Currency must be one of: {0}").format(", ".join(DISPLAY_CURRENCIES)))
	display_iso = CURRENCY_MAP.get(display, display)

	columns = get_columns(display)
	heads = cr._report_costing_heads()
	heads_by_name = {h["name"]: h for h in heads}
	heads_by_account = cr._heads_by_account(heads)
	duty_code = _tra_duty_code(heads)
	rate_cache: dict = {}

	sales = _load_submitted_sales(filters)
	if not sales:
		return columns, []

	item_codes = [r.item for r in sales]

	# Resolve import files for IFCV / JE prefetch
	import_files: list[str] = []
	if filters.get("import_file"):
		import_files.append(filters.import_file)

	# Car Costing / Item import_file recovery
	cc_by_item: dict[str, dict] = {}
	cc_fields = ["name", "item", "import_file", "costing_date", "chassis_no", "maker", "model", "m3"]
	if frappe.db.has_column("Car Costing", "expected_selling_price"):
		cc_fields.append("expected_selling_price")
	if frappe.db.has_column("Car Costing", "yen"):
		cc_fields.append("yen")
	for r in frappe.get_all(
		"Car Costing",
		filters={"item": ["in", item_codes]},
		fields=cc_fields,
		order_by="modified desc",
	):
		if r.item not in cc_by_item:
			cc_by_item[r.item] = r
			if r.import_file and r.import_file not in import_files:
				import_files.append(r.import_file)

	if not import_files and item_codes:
		recovered = set()
		if frappe.db.has_column("Journal Entry", "custom_item") and frappe.db.has_column(
			"Journal Entry", "import_file"
		):
			for ifn in frappe.db.sql(
				"""
				SELECT DISTINCT import_file
				FROM `tabJournal Entry`
				WHERE docstatus = 1
					AND custom_item IN %(items)s
					AND IFNULL(import_file, '') != ''
				""",
				{"items": item_codes},
				pluck=True,
			):
				recovered.add(ifn)
		if frappe.db.table_exists("Import File Cost Voucher Allocation"):
			for ifn in frappe.db.sql(
				"""
				SELECT DISTINCT v.import_file
				FROM `tabImport File Cost Voucher Allocation` a
				INNER JOIN `tabImport File Cost Voucher` v ON v.name = a.parent
				WHERE v.docstatus = 1
					AND a.item IN %(items)s
					AND IFNULL(v.import_file, '') != ''
				""",
				{"items": item_codes},
				pluck=True,
			):
				recovered.add(ifn)
		import_files = list(recovered)

	ifcv_by_item, items_on_ifcv = cr._load_ifcv_allocations(import_files, heads_by_name)
	item_actuals = cr._load_item_actuals(item_codes)
	item_actuals_full = cr._load_item_actuals_including_zero(
		item_codes, only_items=items_on_ifcv | set(item_actuals.keys())
	)
	je_by_item = cr._load_je_by_item(import_files, heads_by_account, item_codes=item_codes)
	pi_prices = cr._load_pi_purchase_prices(item_codes)

	data = []
	for idx, si in enumerate(sales, start=1):
		item = cr._item_fields(si.item)
		cc = cc_by_item.get(si.item) or {}
		date = getdate(si.sale_date or frappe.utils.today())

		raw_amounts, _source = cr._resolve_head_amounts(
			si.item,
			heads,
			item_actuals,
			item_actuals_full,
			ifcv_by_item,
			items_on_ifcv,
			je_by_item,
		)

		selling_native = flt(si.sale_price_native)
		# Prefer SI rate (sold) — fill selling formula gaps from SI price
		cr._fill_selling_formula_gaps(raw_amounts, heads, selling_native)

		purchase_native, purchase_currency = cr._resolve_purchase_price(
			si.item,
			pi_prices,
			item.get("custom_price"),
			cc.get("yen") if isinstance(cc, dict) else None,
		)

		converted = {}
		total_exp = 0.0
		for h in heads:
			code = h["costing_code"]
			slot = raw_amounts.get(code) or {}
			native = slot.get("currency") or h.get("currency") or "TZS"
			amt = cr._convert(flt(slot.get("amount")), native, display, date, rate_cache)
			converted[code] = amt
			total_exp += amt

		duty_native_slot = raw_amounts.get(duty_code) if duty_code else None
		if duty_code and duty_native_slot:
			duty = converted.get(duty_code, 0.0)
		else:
			duty = 0.0

		sale_price = cr._convert(
			selling_native, SELLING_NATIVE_CURRENCY, display, date, rate_cache
		)
		purchase_price = cr._convert(
			purchase_native, purchase_currency, display, date, rate_cache
		)
		expense = total_exp
		# LOCAL EXP ≈ non-duty portion of Total EXP (Excel keeps Duty separate)
		local_exp = flt(expense) - flt(duty)
		if local_exp < 0:
			local_exp = 0.0

		vat_18_native = selling_native * 0.18
		vat_20_native = vat_18_native * 0.20
		vat_18 = cr._convert(vat_18_native, SELLING_NATIVE_CURRENCY, display, date, rate_cache)
		vat_20 = cr._convert(vat_20_native, SELLING_NATIVE_CURRENCY, display, date, rate_cache)

		# REAL PRICE ≈ sale − expense − purchase_price
		# (Expense = Total EXP already includes Duty; avoid double-subtracting Duty)
		real_price = flt(sale_price) - flt(expense) - flt(purchase_price)
		total_cost = flt(expense) + flt(purchase_price)

		yard = item.get("custom_yard_date") or item.get("custom_purchase_date") or (
			cc.get("costing_date") if isinstance(cc, dict) else None
		)
		days = None
		if yard and si.sale_date:
			try:
				days = date_diff(getdate(si.sale_date), getdate(yard))
			except Exception:
				days = None

		buyer = si.buyer_name or ""
		if not buyer and si.customer:
			buyer = frappe.db.get_value("Customer", si.customer, "customer_name") or si.customer

		status = item.get("custom_status") or ""
		sold_label = status if status and "SOLD" in str(status).upper() else "SOLD"

		data.append(
			{
				"day": days if days is not None else idx,
				"stock": item.get("custom_stock_id") or item.get("custom_new_stock_id") or "",
				"chassis": item.get("custom_chassis_no")
				or (cc.get("chassis_no") if isinstance(cc, dict) else "")
				or "",
				"make": (cc.get("maker") if isinstance(cc, dict) else None)
				or item.get("custom_maker")
				or "",
				"description": item.get("item_name") or item.get("custom_model") or "",
				"model": (cc.get("model") if isinstance(cc, dict) else None)
				or item.get("custom_model")
				or "",
				"color": item.get("custom_color") or "",
				"mileage": item.get("custom_mileage") or 0,
				"sold": sold_label,
				"yard_date": yard,
				"sale_date": si.sale_date,
				"buyer_name": buyer,
				"contact": _customer_contact(si.customer, si),
				"days": days if days is not None else 0,
				"currency": display_iso,
				"sale_price": sale_price,
				"duty": duty,
				"expense": expense,
				"purchase_price": purchase_price,
				"local_exp": local_exp,
				"vat_18": vat_18,
				"vat_20": vat_20,
				"real_price": real_price,
				"total_cost": total_cost,
				"m3": flt(cc.get("m3") if isinstance(cc, dict) else 0) or flt(item.get("custom_m3")),
				"item": si.item,
				"sales_invoice": si.sales_invoice,
			}
		)

	return columns, data


@frappe.whitelist()
def run(filters=None):
	"""SPA-friendly wrapper."""
	columns, data = execute(filters)
	return {"columns": columns, "result": data}
