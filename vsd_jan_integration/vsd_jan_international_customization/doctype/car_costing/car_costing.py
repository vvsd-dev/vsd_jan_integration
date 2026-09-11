# Copyright (c) 2026, VV Systems Developer LTD and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

from vsd_jan_integration.vsd_jan_international_customization.utils.costing_engine import (
	get_heads,
	load_template_lines,
	merge_existing_lines,
	recalculate_car_costing,
)


class CarCosting(Document):
	def validate(self):
		if not self.usd_currency:
			self.usd_currency = "USD"
		self.apply_exchange_rates_from_currency_exchange(force=False)
		if not self.exchange_rate:
			frappe.throw(_("Exchange Rate (TZS/USD) is required — set Currency Exchange USD→TZS or enter the rate"))
		from vsd_jan_integration.vsd_jan_international_customization.utils.costing_engine import (
			sort_costing_lines,
		)

		self.set("tz_costing_lines", sort_costing_lines(self.tz_costing_lines))
		self.set("japan_costing_lines", sort_costing_lines(self.japan_costing_lines))
		self.recalculate(save=False)

	def on_update(self):
		"""Save immediately updates Item Expected (no submit). Actuals stay IFCV-only."""
		if self.flags.skip_push_to_item:
			return
		self.push_expected_to_item()

	def apply_exchange_rates_from_currency_exchange(self, force=False):
		"""Pick TZS/USD and YEN/USD from Currency Exchange on costing_date."""
		date = self.costing_date or frappe.utils.today()
		if force or not flt(self.exchange_rate):
			rate = _buying_rate("USD", "TZS", date)
			if rate:
				self.exchange_rate = rate
		if force or not flt(self.yen_exchange_rate):
			yen_rate = _buying_rate("USD", "JPY", date)
			if yen_rate:
				self.yen_exchange_rate = yen_rate

	def recalculate(self, save=False):
		recalculate_car_costing(self)
		if self.meta.has_field("readiness_html"):
			self.readiness_html = self.get_readiness_html()
		if save:
			self.save()

	def get_readiness_html(self):
		checks = [
			("Item", bool(self.item)),
			("Import File", bool(self.import_file)),
			("Exchange Rate", flt(self.exchange_rate) > 0),
			("M3 (CBM)", flt(self.m3) > 0),
			("TRA Duty", self._line_value("tra_duty") > 0),
		]
		badges = []
		for label, ok in checks:
			color = "#28a745" if ok else "#dc3545"
			badges.append(f'<span style="color:{color};margin-right:12px;">● {label}</span>')
		return "".join(badges)

	def _line_value(self, code):
		for line in self.tz_costing_lines or []:
			if line.costing_code == code:
				return flt(line.projected_amount)
		return 0

	def push_expected_to_item(self):
		if not self.item:
			return
		from vsd_jan_integration.vsd_jan_international_customization.utils.costing_engine import (
			refresh_item_expense_totals,
			sort_costing_lines,
		)

		item = frappe.get_doc("Item", self.item)
		item.custom_exchange_rate = self.exchange_rate
		item.custom_cost = self.cost
		if hasattr(item, "custom_profit_usd"):
			item.custom_profit_usd = 0
		item.custom_last_car_costing = self.name

		prev_actual = {}
		for row in list(item.get("custom_tz_costing") or []) + list(item.get("custom_japan_costing") or []):
			if row.costing_code:
				prev_actual[row.costing_code] = flt(row.actual_amount)

		tz_rows = []
		for row in self.tz_costing_lines or []:
			tz_rows.append(
				{
					"costing_head": row.costing_head,
					"costing_code": row.costing_code,
					"costing_name": row.costing_name,
					"entry_mode": row.entry_mode,
					"allocation_scope": row.allocation_scope,
					"account": row.account,
					"currency": row.currency,
					"projected_amount": row.projected_amount,
					"actual_amount": prev_actual.get(row.costing_code, 0),
					"remarks": row.remarks,
				}
			)
		jp_rows = []
		for row in self.japan_costing_lines or []:
			jp_rows.append(
				{
					"costing_head": row.costing_head,
					"costing_code": row.costing_code,
					"costing_name": row.costing_name,
					"entry_mode": row.entry_mode,
					"allocation_scope": row.allocation_scope,
					"account": row.account,
					"currency": row.currency,
					"projected_amount": row.projected_amount,
					"actual_amount": prev_actual.get(row.costing_code, 0),
					"remarks": row.remarks,
				}
			)
		item.set("custom_tz_costing", sort_costing_lines(tz_rows))
		item.set("custom_japan_costing", sort_costing_lines(jp_rows))
		refresh_item_expense_totals(item)

		if hasattr(item, "custom_m3"):
			item.custom_m3 = self.m3
		item.flags.ignore_permissions = True
		item.save()


def _buying_rate(from_currency, to_currency, date=None):
	"""Currency Exchange for_buying; try inverse if direct missing."""
	if not from_currency or not to_currency or from_currency == to_currency:
		return 1.0
	date = date or frappe.utils.today()
	try:
		from erpnext.setup.utils import get_exchange_rate

		rate = flt(get_exchange_rate(from_currency, to_currency, date, "for_buying"))
		if rate:
			return rate
		inv = flt(get_exchange_rate(to_currency, from_currency, date, "for_buying"))
		if inv:
			return flt(1.0 / inv)
	except Exception:
		pass
	return 0.0


@frappe.whitelist()
def fetch_exchange_rates(docname=None, costing_date=None):
	"""Return live rates from Currency Exchange for the form."""
	date = costing_date or frappe.utils.today()
	usd_tzs = _buying_rate("USD", "TZS", date)
	usd_jpy = _buying_rate("USD", "JPY", date)
	if docname and frappe.db.exists("Car Costing", docname):
		doc = frappe.get_doc("Car Costing", docname)
		doc.costing_date = date
		doc.apply_exchange_rates_from_currency_exchange(force=True)
		doc.flags.skip_push_to_item = True
		doc.save()
		return {
			"exchange_rate": doc.exchange_rate,
			"yen_exchange_rate": doc.yen_exchange_rate,
		}
	return {"exchange_rate": usd_tzs, "yen_exchange_rate": usd_jpy}


@frappe.whitelist()
def load_from_item(docname=None, item=None, import_file=None):
	if docname:
		doc = frappe.get_doc("Car Costing", docname)
	elif item:
		doc = frappe.new_doc("Car Costing")
		doc.item = item
	else:
		frappe.throw(_("Item or Car Costing is required"))

	if not doc.item:
		frappe.throw(_("Please select an Item first"))

	item_doc = frappe.get_doc("Item", doc.item)
	doc.chassis_no = item_doc.get("custom_chassis_no")
	doc.maker = item_doc.get("custom_maker")
	doc.model = item_doc.get("custom_model")
	doc.yen = flt(item_doc.get("custom_price"))
	if not flt(doc.m3):
		doc.m3 = flt(item_doc.get("custom_m3"))

	if import_file:
		doc.import_file = import_file
	elif not doc.import_file:
		doc.import_file = _resolve_import_file_for_item(item_doc)

	# Prefer Currency Exchange; fall back to Item only if CE missing
	doc.apply_exchange_rates_from_currency_exchange(force=not flt(doc.exchange_rate))
	if not flt(doc.exchange_rate):
		doc.exchange_rate = flt(item_doc.get("custom_exchange_rate"))
	if not flt(doc.yen_exchange_rate):
		doc.apply_exchange_rates_from_currency_exchange(force=True)

	from vsd_jan_integration.vsd_jan_international_customization.utils.costing_engine import (
		sort_costing_lines,
	)

	existing_tz = item_doc.get("custom_tz_costing") or []
	existing_jp = item_doc.get("custom_japan_costing") or []
	doc.set(
		"tz_costing_lines",
		sort_costing_lines(merge_existing_lines(load_template_lines("Tanzania"), existing_tz)),
	)
	doc.set(
		"japan_costing_lines",
		sort_costing_lines(merge_existing_lines(load_template_lines("Japan"), existing_jp)),
	)

	active = {h.costing_code for h in get_heads()}
	doc.set("tz_costing_lines", [r for r in doc.tz_costing_lines if r.costing_code in active])
	doc.set("japan_costing_lines", [r for r in doc.japan_costing_lines if r.costing_code in active])

	for row in list(doc.tz_costing_lines or []) + list(doc.japan_costing_lines or []):
		row.actual_amount = 0

	recalculate_car_costing(doc)
	if docname:
		doc.flags.skip_push_to_item = True
		doc.save()
		doc.flags.skip_push_to_item = False
		doc.push_expected_to_item()
	else:
		doc.insert()
	return doc.name


@frappe.whitelist()
def recalculate(docname):
	doc = frappe.get_doc("Car Costing", docname)
	doc.recalculate(save=True)
	return {"cost": doc.cost, "price": doc.price, "total_cost_usd": doc.total_cost_usd}


@frappe.whitelist()
def get_or_create_for_item(item):
	existing = frappe.db.get_value(
		"Car Costing",
		{"item": item, "docstatus": ["<", 2]},
		"name",
		order_by="modified desc",
	)
	return existing or load_from_item(item=item)


def _resolve_import_file_for_item(item_doc):
	bl = (item_doc.get("custom_bl") or "").strip()
	if not bl:
		return None
	by_bl = frappe.db.get_value("Import File", {"bl_number": bl}, "name")
	if by_bl:
		return by_bl
	return frappe.db.get_value("Import File", {"supplier_invoice_no": bl}, "name")
