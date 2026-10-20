# Copyright (c) 2026, VV Systems Developer LTD and contributors
# For license information, please see license.txt

"""Jan BL Costing report — columns driven by Costing masters (Purchase + Selling).

Banned multi-currency aggregate columns (TOTAL EXP TSH/USD, YEN IN USD, etc.) are
intentionally omitted. The Currency filter converts every money column via Currency
Exchange on the row date — one Total EXP is enough.

**Purchase-side heads are Actual only.** Cells never use Car Costing Expected
amounts or ESP-based projections. Priority per Purchase/Both head:
1. Item child-table Actual (custom_tz_costing / custom_japan_costing) — IFCV submit
   writes Actual here; preferred source of truth when present.
2. Submitted IFCV allocations for that item (fallback if Actual not stamped yet).
3. Journal Entry debits with custom_item = this car, mapped to Costing via account
   (Fixed Costing JEs: cheque FIXED|*; Selling Costing JEs: cheque SELL|*).

**Selling column + selling-dependent amounts** use a submitted Sales Invoice only:
- Selling — submitted SI base_rate (company currency). No Item custom_selling_price,
  no Car Costing expected_selling_price. No SI → 0.
- VAT 18% — SI selling × 0.18 (informational; distinct from Costing ``vat``).
- Selling-side Costing heads: prefer Item Actual / Selling JE Actual; if still
  zero and a submitted SI exists, compute Formula/Fixed from that SI figure.
  No SI and no Actual → 0 (never Car Costing Expected).

Extra non-master columns:
- Purchase Price — PI Item rate (txn currency), else Item.custom_price (JPY)

Total EXP = sum of all Costing head columns (purchase-landed + selling costing heads).
VAT 18% is informational only and is not added into Total EXP.
Total Cost = Total EXP + Purchase Price (car price).
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

import frappe
from frappe import _
from frappe.utils import flt, getdate

from vsd_jan_integration.vsd_jan_international_customization.utils.costing_engine import (
	_eval as _eval_costing_formula,
	is_selling_side,
)

DISPLAY_CURRENCIES = ("TZS", "YEN", "USD")
# Map UI label YEN → ISO JPY for Currency Exchange
CURRENCY_MAP = {"TZS": "TZS", "YEN": "JPY", "USD": "USD", "JPY": "JPY"}
REGION_ORDER = {"Tanzania": 0, "Japan": 1}
# ESP / SI base_rate are company currency (typically TZS)
SELLING_NATIVE_CURRENCY = "TZS"
# Item.custom_price / excel YEN / Car Costing.yen — Japan purchase in JPY
PURCHASE_FALLBACK_CURRENCY = "JPY"


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
	]


def _head_sort_key(h: dict) -> tuple:
	return (
		REGION_ORDER.get(h.get("region") or "", 9),
		(h.get("costing_name") or "").lower(),
		h.get("costing_code") or "",
	)


def _report_costing_heads() -> list[dict]:
	"""Active Costing masters for report columns — Purchase, Selling, and Both.

	Order: Purchase/Both (landed) first, then Selling-only. Column layout in
	get_columns splits these around the Selling price column.
	"""
	fields = [
		"name",
		"costing_code",
		"costing_name",
		"region",
		"currency",
		"account",
		"allocation_scope",
		"costing_side",
		"entry_mode",
		"formula",
		"default_projected_amount",
	]
	rows = frappe.get_all(
		"Costing",
		filters={"disabled": 0},
		fields=fields,
		order_by="costing_name asc",
	)
	out = []
	for h in rows:
		if not h.get("costing_code"):
			continue
		if not h.get("costing_side"):
			h["costing_side"] = "Purchase"
		out.append(h)
	out.sort(
		key=lambda h: (
			0 if (h.get("costing_side") or "Purchase") != "Selling" else 1,
			*_head_sort_key(h),
		)
	)
	return out


def _split_heads_for_columns(heads: list[dict]) -> tuple[list[dict], list[dict]]:
	"""Split into purchase/landed (Purchase + Both) vs Selling-only heads."""
	purchase, selling = [], []
	for h in heads:
		side = h.get("costing_side") or "Purchase"
		if side == "Selling":
			selling.append(h)
		else:
			# Purchase and Both — landed / purchase-side block
			purchase.append(h)
	purchase.sort(key=_head_sort_key)
	selling.sort(key=_head_sort_key)
	return purchase, selling


def _landed_costing_heads() -> list[dict]:
	"""Backward-compatible alias — now returns all sides (Purchase/Selling/Both)."""
	return _report_costing_heads()


def _money_col(label: str, fieldname: str, width: int = 120) -> dict:
	return {
		"label": label,
		"fieldname": fieldname,
		"fieldtype": "Currency",
		"options": "currency",
		"width": width,
	}


def get_columns(display_currency="TZS", heads=None):
	"""Identity → Purchase Price → purchase heads → Selling → selling heads → VAT 18% → Total EXP → Total Cost.

	Money columns use options=\"currency\" (row field name). Desk's
	frappe.meta.get_field_currency reads doc[options] for the ISO code —
	putting JPY/USD/TZS directly in options is ignored and falls back to
	company default (often TZS).
	"""
	ccy = display_currency or "TZS"
	# Display label may be YEN; ISO for Currency doctype / formatters is JPY
	_iso = CURRENCY_MAP.get(ccy, ccy)
	heads = heads if heads is not None else _report_costing_heads()
	purchase_heads, selling_heads = _split_heads_for_columns(heads)

	cols = [
		# Core identity first, then Purchase Price (visible without scrolling past stock/specs)
		{"label": "Item", "fieldname": "item", "fieldtype": "Link", "options": "Item", "width": 250},
		{"label": "Make", "fieldname": "make", "fieldtype": "Data", "width": 140},
		{"label": "Model", "fieldname": "model", "fieldtype": "Data", "width": 90},
		{"label": "Chassis", "fieldname": "chassis", "fieldtype": "Data", "width": 150},
		# Hidden; referenced by Currency columns via options="currency"
		{
			"label": _("Currency"),
			"fieldname": "currency",
			"fieldtype": "Link",
			"options": "Currency",
			"hidden": 1,
			"width": 80,
		},
		# Purchase Price immediately after chassis — Japan YEN / PI rate
		_money_col(_("Purchase Price"), "purchase_price", 140),
		{"label": "Yard Date", "fieldname": "yard_date", "fieldtype": "Date", "width": 110},
		{"label": "BL", "fieldname": "bl", "fieldtype": "Data", "width": 120},
		{"label": "Container", "fieldname": "container_no", "fieldtype": "Data", "width": 110},
		{"label": "Stock", "fieldname": "stock", "fieldtype": "Data", "width": 90},
		{"label": "New Stock I.D", "fieldname": "new_stock_id", "fieldtype": "Data", "width": 100},
		{"label": "Description", "fieldname": "description", "fieldtype": "Data", "width": 100},
		{"label": "Status", "fieldname": "status", "fieldtype": "Data", "width": 110},
		{"label": "CC", "fieldname": "cc", "fieldtype": "Data", "width": 70},
		{"label": "Mileage", "fieldname": "mileage", "fieldtype": "Float", "width": 90},
		{"label": "M3", "fieldname": "m3", "fieldtype": "Float", "width": 70},
	]

	# Purchase / Both landed Costing heads
	for h in purchase_heads:
		cols.append(_money_col(h.get("costing_name") or h.get("costing_code"), h["costing_code"]))

	# Selling price, then all Selling-side Costing heads immediately after
	cols.append(_money_col(_("Selling"), "selling", 120))
	for h in selling_heads:
		cols.append(_money_col(h.get("costing_name") or h.get("costing_code"), h["costing_code"]))

	cols.extend(
		[
			_money_col(_("VAT 18%"), "vat_18", 110),
			_money_col(_("Total EXP"), "total_exp", 120),
			# Total Cost = Total EXP (all costing heads) + Purchase Price (car price)
			_money_col(_("Total Cost"), "total_cost", 130),
		]
	)
	# Stash ISO on columns for SPA formatters (Desk uses row.currency)
	for col in cols:
		if col.get("fieldtype") == "Currency":
			col["currency"] = _iso
	return cols


def _buying_rate(from_currency: str, to_currency: str, date) -> float:
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
		frappe.log_error(title="Jan costing FX lookup", message=frappe.get_traceback())
	return 0.0


def _convert(amount: float, native: str | None, display: str, date, rate_cache: dict) -> float:
	if native is None or amount is None:
		return flt(amount)
	native_iso = CURRENCY_MAP.get(native, native)
	display_iso = CURRENCY_MAP.get(display, display)
	if not native_iso or native_iso == display_iso:
		return flt(amount)
	key = (native_iso, display_iso, str(date))
	if key not in rate_cache:
		rate_cache[key] = _buying_rate(native_iso, display_iso, date)
	rate = rate_cache[key]
	if not rate:
		if native_iso != "USD" and display_iso != "USD":
			to_usd = rate_cache.setdefault(
				(native_iso, "USD", str(date)), _buying_rate(native_iso, "USD", date)
			)
			usd_to = rate_cache.setdefault(
				("USD", display_iso, str(date)), _buying_rate("USD", display_iso, date)
			)
			if to_usd and usd_to:
				return flt(amount) * flt(to_usd) * flt(usd_to)
		return flt(amount)
	return flt(amount) * flt(rate)


def _item_fields(item_name: str) -> dict[str, Any]:
	if not item_name or not frappe.db.exists("Item", item_name):
		return {}
	meta = frappe.get_meta("Item")
	wanted = [
		"item_name",
		"custom_chassis_no",
		"custom_maker",
		"custom_model",
		"custom_new_stock_id",
		"custom_bl",
		"custom_m3",
		"custom_color",
		"custom_cc",
		"custom_mileage",
		"custom_purchase_date",
		"custom_yard_date",
		"custom_container_no",
		"custom_stock_id",
		"custom_status",
		"custom_price",  # Purchase Price (Yen) — excel YEN stamped on Item
	]
	fields = ["name"] + [f for f in wanted if meta.has_field(f)]
	return frappe.db.get_value("Item", item_name, fields, as_dict=True) or {}


def _heads_by_account(heads: list[dict]) -> dict[str, dict]:
	"""Map expense account → Costing head (first wins)."""
	out = {}
	for h in heads:
		acc = h.get("account")
		if acc and acc not in out:
			out[acc] = h
	return out


def _load_pi_purchase_prices(item_codes: list[str]) -> dict[str, dict]:
	"""Latest submitted Purchase Invoice unit price per item.

	Returns item_code → {amount, currency} using PI Item rate in transaction
	currency (Japan purchases are typically JPY). Falls back to base_rate in
	company currency when rate is blank.
	"""
	out: dict[str, dict] = {}
	if not item_codes:
		return out
	company = (
		frappe.defaults.get_user_default("Company")
		or frappe.db.get_single_value("Global Defaults", "default_company")
	)
	company_currency = (
		frappe.get_cached_value("Company", company, "default_currency") if company else None
	) or "TZS"
	rows = frappe.db.sql(
		"""
		SELECT
			pii.item_code,
			pii.rate,
			pii.base_rate,
			pi.currency,
			pi.conversion_rate,
			pi.posting_date,
			pi.modified,
			pi.docstatus,
			IFNULL(pi.update_stock, 0) as update_stock
		FROM `tabPurchase Invoice Item` pii
		INNER JOIN `tabPurchase Invoice` pi ON pi.name = pii.parent
		WHERE pi.docstatus = 1
			AND pii.item_code IN %(items)s
		ORDER BY
			pi.update_stock DESC,
			pi.posting_date DESC,
			pi.modified DESC
		""",
		{"items": item_codes},
		as_dict=True,
	)
	for r in rows:
		if r.item_code in out:
			continue
		rate = flt(r.rate)
		currency = (r.currency or "").strip() or PURCHASE_FALLBACK_CURRENCY
		if rate > 0:
			out[r.item_code] = {"amount": rate, "currency": currency}
			continue
		base = flt(r.base_rate)
		if not base:
			base = flt(r.rate) * (flt(r.conversion_rate) or 1.0)
		if base > 0:
			out[r.item_code] = {"amount": base, "currency": company_currency}
	return out


def _resolve_purchase_price(
	item_code: str,
	pi_prices: dict[str, dict],
	item_custom_price: float | None = None,
	cc_yen: float | None = None,
) -> tuple[float, str]:
	"""Prefer PI Item rate, then Item.custom_price (JPY).

	Never use Car Costing.yen / expected, selling, valuation, or standard_rate.
	``cc_yen`` is accepted for callers but ignored (Actual purchase only).
	"""
	pi = pi_prices.get(item_code) or {}
	amt = flt(pi.get("amount"))
	if amt > 0:
		return amt, pi.get("currency") or PURCHASE_FALLBACK_CURRENCY
	custom = flt(item_custom_price)
	if custom > 0:
		return custom, PURCHASE_FALLBACK_CURRENCY
	return 0.0, PURCHASE_FALLBACK_CURRENCY


def _load_si_selling_prices(item_codes: list[str]) -> dict[str, float]:
	"""Latest submitted Sales Invoice unit price (company currency) per item."""
	out: dict[str, float] = {}
	if not item_codes:
		return out
	rows = frappe.db.sql(
		"""
		SELECT
			sii.item_code,
			sii.base_rate,
			sii.rate,
			si.conversion_rate,
			si.posting_date,
			si.modified
		FROM `tabSales Invoice Item` sii
		INNER JOIN `tabSales Invoice` si ON si.name = sii.parent
		WHERE si.docstatus = 1
			AND sii.item_code IN %(items)s
		ORDER BY si.posting_date DESC, si.modified DESC
		""",
		{"items": item_codes},
		as_dict=True,
	)
	for r in rows:
		if r.item_code in out:
			continue
		base = flt(r.base_rate)
		if not base:
			base = flt(r.rate) * (flt(r.conversion_rate) or 1.0)
		if base > 0:
			out[r.item_code] = base
	return out


def _resolve_selling_price(
	item_code: str,
	si_prices: dict[str, float],
	item_selling: float | None = None,
	cc_esp: float | None = None,
) -> float:
	"""Submitted Sales Invoice unit price only (company currency).

	No Item custom_selling_price, no Car Costing expected_selling_price.
	``item_selling`` / ``cc_esp`` are accepted for callers but ignored.
	"""
	return flt(si_prices.get(item_code))


def _fill_selling_formula_gaps(
	merged: dict[str, dict],
	heads: list[dict],
	selling_price: float,
) -> None:
	"""Fill zero Selling-side head slots from Formula/Fixed using SI selling figure.

	Call only with a submitted-SI selling base (never Car Costing ESP).
	Does not overwrite Item Actual / IFCV / JE amounts already in ``merged``.
	Purchase-side heads are skipped.
	"""
	if selling_price <= 0:
		return
	ctx = {
		"header": {"expected_selling_price": selling_price},
		"line": {code: flt(v.get("amount")) for code, v in merged.items()},
	}
	for h in heads:
		if not is_selling_side(h.get("costing_side")):
			continue
		code = h["costing_code"]
		if code not in merged:
			continue
		if flt(merged[code].get("amount")):
			continue
		amt = 0.0
		if (h.get("entry_mode") or "") == "Formula" and h.get("formula"):
			try:
				amt = flt(_eval_costing_formula(h["formula"], ctx))
			except Exception:
				frappe.log_error(
					title=f"BL Costing formula {code}",
					message=frappe.get_traceback(),
				)
				amt = 0.0
		elif (h.get("entry_mode") or "") == "Fixed":
			amt = flt(h.get("default_projected_amount"))
		if amt:
			merged[code] = {
				"amount": amt,
				"currency": h.get("currency") or merged[code].get("currency") or SELLING_NATIVE_CURRENCY,
			}
			ctx["line"][code] = amt


def _code_for_head_name(head_name: str, heads_by_name: dict) -> str | None:
	h = heads_by_name.get(head_name)
	return h["costing_code"] if h else None


def _load_item_actuals(item_codes: list[str]) -> dict[str, dict[str, dict]]:
	"""item → costing_code → {amount, currency} from Item Costing Line Actual."""
	out: dict[str, dict[str, dict]] = defaultdict(dict)
	if not item_codes:
		return out
	if not frappe.db.table_exists("Item Costing Line"):
		return out

	rows = frappe.db.sql(
		"""
		SELECT parent, costing_code, costing_head, actual_amount, currency
		FROM `tabItem Costing Line`
		WHERE parent IN %(items)s
			AND IFNULL(actual_amount, 0) != 0
		""",
		{"items": item_codes},
		as_dict=True,
	)
	# Also detect "touched by IFCV" rows with actual=0 via a separate existence check
	# when parent is on a submitted IFCV (handled in resolve). Here keep non-zero actuals.
	for r in rows:
		code = r.costing_code or r.costing_head
		if not code:
			continue
		out[r.parent][code] = {
			"amount": flt(r.actual_amount),
			"currency": r.currency or None,
		}
	return out


def _load_item_actuals_including_zero(
	item_codes: list[str], only_items: set[str] | None = None
) -> dict[str, dict[str, dict]]:
	"""Full Actual map (incl. 0) for items known to be on submitted IFCVs."""
	out: dict[str, dict[str, dict]] = defaultdict(dict)
	targets = [i for i in item_codes if (only_items is None or i in only_items)]
	if not targets or not frappe.db.table_exists("Item Costing Line"):
		return out
	rows = frappe.db.sql(
		"""
		SELECT parent, costing_code, costing_head, actual_amount, currency
		FROM `tabItem Costing Line`
		WHERE parent IN %(items)s
		""",
		{"items": targets},
		as_dict=True,
	)
	for r in rows:
		code = r.costing_code or r.costing_head
		if not code:
			continue
		out[r.parent][code] = {
			"amount": flt(r.actual_amount),
			"currency": r.currency or None,
		}
	return out


def _load_ifcv_allocations(
	import_files: list[str], heads_by_name: dict
) -> tuple[dict[str, dict[str, dict]], set[str]]:
	"""item → costing_code → {amount, currency}; plus set of items on submitted IFCVs."""
	by_item: dict[str, dict[str, dict]] = defaultdict(lambda: defaultdict(lambda: {"amount": 0.0, "currency": None}))
	items_on_ifcv: set[str] = set()
	if not import_files:
		return {}, items_on_ifcv
	if not frappe.db.table_exists("Import File Cost Voucher Allocation"):
		return {}, items_on_ifcv

	rows = frappe.db.sql(
		"""
		SELECT
			a.item,
			a.costing_head,
			a.amount,
			a.currency,
			a.account
		FROM `tabImport File Cost Voucher Allocation` a
		INNER JOIN `tabImport File Cost Voucher` v ON v.name = a.parent
		WHERE v.docstatus = 1
			AND v.import_file IN %(ifs)s
			AND IFNULL(a.item, '') != ''
		""",
		{"ifs": import_files},
		as_dict=True,
	)
	for r in rows:
		items_on_ifcv.add(r.item)
		code = None
		if r.costing_head:
			code = _code_for_head_name(r.costing_head, heads_by_name)
			if not code and frappe.db.exists("Costing", r.costing_head):
				code = frappe.db.get_value("Costing", r.costing_head, "costing_code") or r.costing_head
		if not code:
			continue
		cur = r.currency
		if not cur and r.account:
			cur = frappe.db.get_value("Account", r.account, "account_currency")
		slot = by_item[r.item][code]
		slot["amount"] = flt(slot["amount"]) + flt(r.amount)
		slot["currency"] = cur or slot["currency"]

	# normalize nested defaultdict
	return {item: dict(codes) for item, codes in by_item.items()}, items_on_ifcv


def _is_stock_account(account: str) -> bool:
	if not account:
		return False
	acc_type = frappe.db.get_value("Account", account, "account_type")
	return acc_type in ("Stock", "Stock Received But Not Billed")


def _load_je_by_item(
	import_files: list[str],
	heads_by_account: dict[str, dict],
	item_codes: list[str] | None = None,
) -> dict[str, dict[str, dict]]:
	"""item → costing_code → {amount, currency} from JE.custom_item linked debits only.

	Loads by Import File and also by custom_item ∈ item_codes so Fixed Costing JEs
	with a blank/mismatched import_file still map to the car on the report.
	"""
	out: dict[str, dict[str, dict]] = defaultdict(
		lambda: defaultdict(lambda: {"amount": 0.0, "currency": None})
	)
	if not frappe.db.has_column("Journal Entry", "custom_item"):
		return {}

	clauses = []
	params: dict[str, Any] = {}
	if import_files and frappe.db.has_column("Journal Entry", "import_file"):
		clauses.append("je.import_file IN %(ifs)s")
		params["ifs"] = import_files
	if item_codes:
		clauses.append("je.custom_item IN %(items)s")
		params["items"] = item_codes
	if not clauses:
		return {}

	rows = frappe.db.sql(
		f"""
		SELECT
			je.custom_item as item,
			jea.account as expense_account,
			jea.debit_in_account_currency as amount,
			jea.account_currency as currency
		FROM `tabJournal Entry` je
		INNER JOIN `tabJournal Entry Account` jea ON jea.parent = je.name
		WHERE je.docstatus = 1
			AND IFNULL(je.custom_item, '') != ''
			AND jea.debit_in_account_currency > 0
			AND ({' OR '.join(clauses)})
		""",
		params,
		as_dict=True,
	)
	for r in rows:
		if _is_stock_account(r.expense_account):
			continue
		head = heads_by_account.get(r.expense_account)
		if not head:
			continue
		code = head["costing_code"]
		slot = out[r.item][code]
		slot["amount"] = flt(slot["amount"]) + flt(r.amount)
		slot["currency"] = r.currency or head.get("currency") or slot["currency"]

	return {item: dict(codes) for item, codes in out.items()}

def _fill_missing_from_je(
	merged: dict[str, dict], je_map: dict[str, dict]
) -> bool:
	"""Fill zero/missing head slots from JE.custom_item debits (Fixed Costing path).

	Priority per head remains: Item Actual → IFCV → JE. Never overwrite a non-zero
	Actual/IFCV amount; only plug gaps so Fixed JE heads appear alongside IFCV freight.
	"""
	if not je_map:
		return False
	filled = False
	for code, val in je_map.items():
		if code not in merged:
			continue
		if flt(merged[code].get("amount")):
			continue
		amt = flt(val.get("amount"))
		if not amt:
			continue
		merged[code] = {
			"amount": amt,
			"currency": val.get("currency") or merged[code].get("currency"),
		}
		filled = True
	return filled


def _resolve_head_amounts(
	item_code: str,
	heads: list[dict],
	item_actuals: dict[str, dict[str, dict]],
	item_actuals_full: dict[str, dict[str, dict]],
	ifcv_by_item: dict[str, dict[str, dict]],
	items_on_ifcv: set[str],
	je_by_item: dict[str, dict[str, dict]],
) -> tuple[dict[str, dict], str]:
	"""Return costing_code → {amount, currency} and source label.

	Per-head priority: Item Actual → IFCV allocation → JE debit with custom_item.
	Fixed Costing JEs (cheque FIXED|*, custom_item set) must populate heads even when
	the car is already on a submitted IFCV for other expenses.
	"""
	zeros = {
		h["costing_code"]: {"amount": 0.0, "currency": h.get("currency")}
		for h in heads
	}
	if not item_code:
		return zeros, "none"

	nonzero_actual = item_actuals.get(item_code) or {}
	on_ifcv = item_code in items_on_ifcv
	ifcv_map = ifcv_by_item.get(item_code) or {}
	je_map = je_by_item.get(item_code) or {}

	# 1) Submitted IFCV path — Item Actual is SoT (IFCV.submit → push_actual_to_item)
	if on_ifcv or ifcv_map:
		full = item_actuals_full.get(item_code) or nonzero_actual
		merged = {k: dict(v) for k, v in zeros.items()}
		for code, val in full.items():
			if code in merged:
				merged[code] = {
					"amount": flt(val.get("amount")),
					"currency": val.get("currency") or merged[code]["currency"],
				}
		# Fill gaps from IFCV allocations when Actual row missing / zero
		for code, val in ifcv_map.items():
			if code in merged and not flt(merged[code]["amount"]) and flt(val.get("amount")):
				merged[code] = {
					"amount": flt(val.get("amount")),
					"currency": val.get("currency") or merged[code]["currency"],
				}
		# Fill remaining gaps from Fixed/item-linked JEs (e.g. Bond Insurance)
		je_filled = _fill_missing_from_je(merged, je_map)
		if full:
			src = "item_actual+je" if je_filled else "item_actual"
		elif ifcv_map:
			src = "ifcv+je" if je_filled else "ifcv"
		else:
			src = "je" if je_filled else "none"
		return merged, src

	# 2) Item Actual without live IFCV (e.g. Actual left after cancel, or stamped elsewhere)
	if nonzero_actual:
		merged = {k: dict(v) for k, v in zeros.items()}
		for code, val in nonzero_actual.items():
			if code in merged:
				merged[code] = {
					"amount": flt(val.get("amount")),
					"currency": val.get("currency") or merged[code]["currency"],
				}
		je_filled = _fill_missing_from_je(merged, je_map)
		return merged, "item_actual+je" if je_filled else "item_actual"

	# 3) No IFCV / Actual — JE debits linked via custom_item (BL-wide untied stay 0)
	if je_map:
		merged = {k: dict(v) for k, v in zeros.items()}
		for code, val in je_map.items():
			if code in merged:
				merged[code] = {
					"amount": flt(val.get("amount")),
					"currency": val.get("currency") or merged[code]["currency"],
				}
		return merged, "je"

	return zeros, "none"


@frappe.whitelist()
def execute(filters=None):
	frappe.has_permission("Car Costing", "read", throw=True)
	if isinstance(filters, str):
		import json

		filters = json.loads(filters) if filters else {}
	filters = frappe._dict(filters or {})

	display = (filters.get("currency") or "TZS").upper()
	if display not in DISPLAY_CURRENCIES:
		frappe.throw(_("Currency must be one of: {0}").format(", ".join(DISPLAY_CURRENCIES)))
	display_iso = CURRENCY_MAP.get(display, display)

	heads = _report_costing_heads()
	columns = get_columns(display, heads)
	heads_by_name = {h["name"]: h for h in heads}
	heads_by_account = _heads_by_account(heads)
	rate_cache: dict = {}

	list_filters = []
	if filters.get("from_date"):
		list_filters.append(["costing_date", ">=", filters.from_date])
	if filters.get("to_date"):
		list_filters.append(["costing_date", "<=", filters.to_date])
	if filters.get("chassis"):
		list_filters.append(["chassis_no", "like", f"%{filters.chassis}%"])

	# Import File may live on Car Costing; also resolve via Item BL / PI (get_vehicles_for_import_file)
	import_file_filter = filters.get("import_file")
	if import_file_filter:
		list_filters.append(["import_file", "=", import_file_filter])

	names = frappe.get_list(
		"Car Costing",
		filters=list_filters,
		fields=["name"],
		order_by="costing_date desc, modified desc",
		# limit_page_length=500,
	)

	if import_file_filter:
		from vsd_jan_integration.vsd_jan_international_customization.doctype.import_file_cost_voucher.import_file_cost_voucher import (
			get_vehicles_for_import_file,
		)

		item_names = [v.name for v in get_vehicles_for_import_file(import_file_filter)]
		extra = []
		if item_names:
			extra_filters = [["item", "in", item_names]]
			if filters.get("from_date"):
				extra_filters.append(["costing_date", ">=", filters.from_date])
			if filters.get("to_date"):
				extra_filters.append(["costing_date", "<=", filters.to_date])
			if filters.get("chassis"):
				extra_filters.append(["chassis_no", "like", f"%{filters.chassis}%"])
			extra = frappe.get_list(
				"Car Costing",
				filters=extra_filters,
				fields=["name"],
				# limit_page_length=500,
			)
		seen = {r.name for r in names}
		for r in extra:
			if r.name not in seen:
				names.append(r)
				seen.add(r.name)

	# Prefetch Car Costing headers
	cc_names = [r.name for r in names]
	cc_fields = [
		"name",
		"item",
		"import_file",
		"costing_date",
		"chassis_no",
		"maker",
		"model",
		"m3",
	]
	# Do not load expected_selling_price / yen — Actual-only report; those are Expected.
	cc_rows = (
		frappe.get_all(
			"Car Costing",
			filters={"name": ["in", cc_names]},
			fields=cc_fields,
		)
		if cc_names
		else []
	)
	cc_by_name = {r.name: r for r in cc_rows}
	ordered = [cc_by_name[n.name] for n in names if n.name in cc_by_name]

	# Stamp resolved import_file for JE/IFCV prefetch (CC.import_file often blank)
	for r in ordered:
		if not r.import_file and import_file_filter:
			r.import_file = import_file_filter

	item_codes = [r.item for r in ordered if r.item]
	import_files = list({r.import_file for r in ordered if r.import_file})
	if import_file_filter and import_file_filter not in import_files:
		import_files.append(import_file_filter)

	# When CC.import_file is blank, recover Import Files from JE / IFCV for these cars
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

	ifcv_by_item, items_on_ifcv = _load_ifcv_allocations(import_files, heads_by_name)
	item_actuals = _load_item_actuals(item_codes)
	item_actuals_full = _load_item_actuals_including_zero(
		item_codes, only_items=items_on_ifcv | set(item_actuals.keys())
	)
	je_by_item = _load_je_by_item(import_files, heads_by_account, item_codes=item_codes)
	si_prices = _load_si_selling_prices(item_codes)
	pi_prices = _load_pi_purchase_prices(item_codes)

	data = []
	for idx, cc in enumerate(ordered, start=1):
		item = _item_fields(cc.item)
		date = getdate(cc.costing_date or frappe.utils.today())

		raw_amounts, _source = _resolve_head_amounts(
			cc.item,
			heads,
			item_actuals,
			item_actuals_full,
			ifcv_by_item,
			items_on_ifcv,
			je_by_item,
		)

		# Selling + VAT 18% + selling-head formula fills: submitted SI only
		selling_native = _resolve_selling_price(cc.item, si_prices)
		# Prefer Actual/JE already in raw_amounts; fill Selling-side gaps from SI
		_fill_selling_formula_gaps(raw_amounts, heads, selling_native)

		purchase_native, purchase_currency = _resolve_purchase_price(
			cc.item,
			pi_prices,
			item.get("custom_price"),
		)

		converted = {}
		total_exp = 0.0
		for h in heads:
			code = h["costing_code"]
			slot = raw_amounts.get(code) or {}
			native = slot.get("currency") or h.get("currency") or "TZS"
			amt = _convert(flt(slot.get("amount")), native, display, date, rate_cache)
			converted[code] = amt
			total_exp += amt

		purchase_price = _convert(
			purchase_native, purchase_currency, display, date, rate_cache
		)
		selling = _convert(selling_native, SELLING_NATIVE_CURRENCY, display, date, rate_cache)
		vat_18 = _convert(
			selling_native * 0.18, SELLING_NATIVE_CURRENCY, display, date, rate_cache
		)
		total_cost = flt(total_exp) + flt(purchase_price)

		data.append(
			{
				"s_no": idx,
				"yard_date": item.get("custom_yard_date")
				or item.get("custom_purchase_date")
				or cc.costing_date,
				"bl": item.get("custom_bl") or "",
				"container_no": item.get("custom_container_no") or "",
				"chassis": cc.chassis_no or item.get("custom_chassis_no") or "",
				"stock": item.get("custom_stock_id") or "",
				"new_stock_id": item.get("custom_new_stock_id") or "",
				"make": cc.maker or item.get("custom_maker") or "",
				"description": item.get("custom_color") or "",
				"model": cc.model or item.get("custom_model") or "",
				"item_name": item.get("item_name") or "",
				"status": item.get("custom_status") or "",
				"cc": item.get("custom_cc") or "",
				"mileage": item.get("custom_mileage") or 0,
				"m3": flt(cc.m3) or flt(item.get("custom_m3")),
				# Desk Currency formatter: column options="currency" → this field
				"currency": display_iso,
				"purchase_price": purchase_price,
				"selling": selling,
				**converted,
				"vat_18": vat_18,
				"total_exp": total_exp,
				"total_cost": total_cost,
				"car_costing": cc.name,
				"item": cc.item,
			}
		)

	return columns, data


@frappe.whitelist()
def run(filters=None):
	"""SPA-friendly wrapper."""
	columns, data = execute(filters)
	return {"columns": columns, "result": data}
