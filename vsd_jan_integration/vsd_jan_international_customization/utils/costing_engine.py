# Copyright (c) 2026, VV Systems Developer LTD and contributors
# For license information, please see license.txt

import re
from collections import defaultdict, deque

import frappe
from frappe import _
from frappe.utils import flt, getdate, today

TOKEN_PATTERN = re.compile(r"\{([a-zA-Z0-9_.]+)\}")

# Matches 1 BL COST.xlsx "NEW COST FILE " sheet:
# TOTAL EXP TSH = TZ lines excluding TRA DUTY
# TSH TO USD = TOTAL EXP TSH / exchange
# TOTAL EXP USD = TSH TO USD + Japan lines
# TOTAL COST USD = DUTY USD + TOTAL EXP USD + YEN IN USD
# COST (landed) = TOTAL COST USD * exchange
# City Levy + VAT are Selling-side formula heads driven by
# {header.expected_selling_price} (Excel AS → AM/AO); not in landed COST.
HEADER_FORMULAS = {
	"tsh_to_usd": "{header.total_exp_tsh} / {header.exchange_rate}",
	"yen_in_usd": "{header.yen} / {header.yen_exchange_rate}",
	"total_cost_usd": "{header.duty_usd} + {header.total_exp_usd} + {header.yen_in_usd}",
	"cost": "{header.total_cost_usd} * {header.exchange_rate}",
	"price": "{header.cost}",
}


def _flt(v):
	return flt(v) if v not in (None, "") else 0.0


def _doc_get(doc, field, default=0):
	if isinstance(doc, dict):
		return doc.get(field, default)
	return getattr(doc, field, default)


def _deps(formula):
	if not formula:
		return []
	return [m.group(1) for m in TOKEN_PATTERN.finditer(formula)]


def _resolve(token, ctx):
	parts = token.split(".")
	if len(parts) != 2:
		return 0.0
	grp, key = parts
	return _flt(ctx.get(grp, {}).get(key))


def _eval(formula, ctx):
	if not formula:
		return 0.0

	def replace(m):
		return str(_resolve(m.group(1), ctx))

	expr = TOKEN_PATTERN.sub(replace, formula)
	expr = re.sub(
		r"SUM\(([^)]+)\)",
		lambda m: "(" + "+".join(a.strip() for a in m.group(1).split(",")) + ")",
		expr,
		flags=re.IGNORECASE,
	)
	try:
		return _flt(frappe.safe_eval(expr))
	except Exception as exc:
		frappe.throw(_("Formula failed: {0} ({1})").format(formula, exc))


def _toposort(heads):
	idx = {h.costing_code: h for h in heads}
	graph = defaultdict(set)
	indeg = defaultdict(int)
	for h in heads:
		deps = set((h.depends_on or "").replace(" ", "").split(",")) - {""}
		for token in _deps(h.formula or ""):
			p = token.split(".")
			if len(p) == 2 and p[0] == "line":
				deps.add(p[1])
		for d in deps:
			if d in idx and d != h.costing_code:
				graph[d].add(h.costing_code)
				indeg[h.costing_code] += 1
		indeg[h.costing_code] = indeg[h.costing_code]

	q = deque([k for k in idx if indeg[k] == 0])
	out = []
	while q:
		n = q.popleft()
		out.append(idx[n])
		for nxt in graph.get(n, []):
			indeg[nxt] -= 1
			if indeg[nxt] == 0:
				q.append(nxt)

	if len(out) != len(idx):
		frappe.throw(_("Circular costing dependencies detected"))
	return out


def get_heads(region=None, costing_side=None):
	"""Return active Costing heads.

	costing_side:
	  None → all sides
	  \"Purchase\" → Purchase + Both
	  \"Selling\" → Selling + Both
	  exact value otherwise
	"""
	filters = {"disabled": 0}
	if region:
		filters["region"] = region
	fields = [
		"name",
		"costing_code",
		"costing_name",
		"entry_mode",
		"allocation_scope",
		"account",
		"payable_account",
		"currency",
		"default_projected_amount",
		"formula",
		"depends_on",
	]
	if frappe.db.has_column("Costing", "costing_side"):
		fields.append("costing_side")

	rows = frappe.get_all(
		"Costing",
		filters=filters,
		fields=fields,
		order_by="costing_name asc, costing_code asc",
	)

	out = []
	for h in rows:
		side = (h.get("costing_side") or "Purchase") if isinstance(h, dict) else (getattr(h, "costing_side", None) or "Purchase")
		if costing_side == "Purchase" and side not in ("Purchase", "Both"):
			continue
		if costing_side == "Selling" and side not in ("Selling", "Both"):
			continue
		if costing_side and costing_side not in ("Purchase", "Selling") and side != costing_side:
			continue
		out.append(frappe._dict(h))
	return out


def is_purchase_side(side):
	return (side or "Purchase") in ("Purchase", "Both")


def is_selling_side(side):
	return (side or "Purchase") in ("Selling", "Both")


def load_template_lines(region):
	rows = []
	for h in get_heads(region):
		rows.append(
			{
				"costing_head": h.name,
				"costing_code": h.costing_code,
				"costing_name": h.costing_name,
				"entry_mode": h.entry_mode,
				"allocation_scope": h.allocation_scope,
				"account": h.account,
				"currency": h.currency,
				"projected_amount": _flt(h.default_projected_amount) if h.entry_mode == "Fixed" else 0,
				"actual_amount": 0,
				"is_manual_override": 0,
			}
		)
	return rows


def merge_existing_lines(template, existing):
	ex = {}
	for r in existing or []:
		code = r.get("costing_code") if isinstance(r, dict) else getattr(r, "costing_code", None)
		if code:
			ex[code] = r
	for r in template:
		old = ex.get(r["costing_code"])
		if not old:
			continue
		val = old.get("projected_amount") if isinstance(old, dict) else getattr(old, "projected_amount", None)
		r["projected_amount"] = _flt(val) or r["projected_amount"]
		actual = old.get("actual_amount") if isinstance(old, dict) else getattr(old, "actual_amount", None)
		r["actual_amount"] = _flt(actual)
		r["is_manual_override"] = (
			old.get("is_manual_override", 0) if isinstance(old, dict) else getattr(old, "is_manual_override", 0)
		)
		r["remarks"] = old.get("remarks") if isinstance(old, dict) else getattr(old, "remarks", None)
	return template


def sort_costing_lines(lines):
	"""Stable sort by Costing Name (then code)."""
	def key(r):
		name = r.get("costing_name") if isinstance(r, dict) else getattr(r, "costing_name", None)
		code = r.get("costing_code") if isinstance(r, dict) else getattr(r, "costing_code", None)
		return ((name or "").lower(), code or "")

	return sorted(list(lines or []), key=key)


def sum_line_amounts(lines, field="projected_amount"):
	total = 0.0
	for r in lines or []:
		val = r.get(field) if isinstance(r, dict) else getattr(r, field, None)
		total += _flt(val)
	return total


def refresh_item_expense_totals(item_doc):
	"""Set Item total expected / actual from TZ + Japan costing child tables."""
	tz = item_doc.get("custom_tz_costing") or []
	jp = item_doc.get("custom_japan_costing") or []
	if item_doc.meta.has_field("custom_total_expected_expense"):
		item_doc.custom_total_expected_expense = sum_line_amounts(tz, "projected_amount") + sum_line_amounts(
			jp, "projected_amount"
		)
	if item_doc.meta.has_field("custom_total_actual_expense"):
		item_doc.custom_total_actual_expense = sum_line_amounts(tz, "actual_amount") + sum_line_amounts(
			jp, "actual_amount"
		)


def recalculate_car_costing(doc):
	item = frappe.get_doc("Item", doc.item) if _doc_get(doc, "item") else None

	line_ctx = {}
	all_lines = list(doc.get("tz_costing_lines") or []) + list(doc.get("japan_costing_lines") or [])
	for line in all_lines:
		line_ctx[line.costing_code] = _flt(line.projected_amount)

	heads = _toposort(get_heads())
	line_by_code = {l.costing_code: l for l in all_lines}

	exchange_rate = _flt(_doc_get(doc, "exchange_rate"))
	yen = _flt(_doc_get(doc, "yen")) or (_flt(item.custom_price) if item else 0)
	yen_exchange_rate = _flt(_doc_get(doc, "yen_exchange_rate"))
	expected_selling_price = _flt(_doc_get(doc, "expected_selling_price"))

	ctx = {
		"line": line_ctx,
		"header": {
			"exchange_rate": exchange_rate,
			"yen_exchange_rate": yen_exchange_rate,
			"yen": yen,
			"duty_usd": 0,
			"total_exp_tsh": 0,
			"total_exp_usd": 0,
			"expected_selling_price": expected_selling_price,
		},
	}

	for h in heads:
		line = line_by_code.get(h.costing_code)
		if not line:
			continue
		if h.entry_mode == "Fixed" and not line.is_manual_override:
			line.projected_amount = _flt(h.default_projected_amount)
		elif h.entry_mode == "Formula" and not line.is_manual_override:
			line.projected_amount = _eval(h.formula, ctx)
		line_ctx[h.costing_code] = _flt(line.projected_amount)

	# Excel TOTAL EXP TSH excludes TRA DUTY (col Y = Q..X only)
	# and excludes Selling-side tax lines (City Levy / VAT — cols AM/AO).
	tz_lines = list(doc.get("tz_costing_lines") or [])
	japan_lines = list(doc.get("japan_costing_lines") or [])
	selling_only = {
		h.costing_code
		for h in heads
		if (getattr(h, "costing_side", None) or "Purchase") == "Selling"
	}
	doc.total_exp_tsh = sum(
		_flt(l.projected_amount)
		for l in tz_lines
		if l.costing_code != "tra_duty" and l.costing_code not in selling_only
	)
	ctx["header"]["total_exp_tsh"] = _flt(doc.total_exp_tsh)

	tra_duty = _flt(line_ctx.get("tra_duty"))
	ctx["header"]["duty_usd"] = (tra_duty / exchange_rate) if exchange_rate else 0

	# TSH TO USD first — Excel TOTAL EXP USD includes it
	doc.tsh_to_usd = _eval(HEADER_FORMULAS["tsh_to_usd"], ctx)
	ctx["header"]["tsh_to_usd"] = _flt(doc.tsh_to_usd)

	japan_sum = sum(_flt(l.projected_amount) for l in japan_lines)
	doc.total_exp_usd = _flt(doc.tsh_to_usd) + japan_sum
	ctx["header"]["total_exp_usd"] = _flt(doc.total_exp_usd)

	for fld in ["yen_in_usd", "total_cost_usd", "cost", "price"]:
		value = _eval(HEADER_FORMULAS[fld], ctx)
		setattr(doc, fld, value)
		ctx["header"][fld] = value

	# Surface planned selling price when set (Excel AS); else PRICE mirrors landed COST
	if expected_selling_price:
		doc.price = expected_selling_price
		ctx["header"]["price"] = expected_selling_price

	doc.yen = yen
	if item and item.custom_purchase_date:
		doc.days_since_purchase = (getdate(today()) - getdate(item.custom_purchase_date)).days
	else:
		doc.days_since_purchase = 0

	return doc
