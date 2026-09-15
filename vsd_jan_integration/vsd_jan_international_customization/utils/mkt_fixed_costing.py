# Copyright (c) 2026, VV Systems Developer LTD and contributors
# For license information, please see license.txt

"""Fixed Costing artifacts for vehicle Items.

Rules:
- On vehicle Item create → draft Car Costing only (no Fixed JE yet).
- Fixed JE (expected / payable) only when the car is tied to an Import File via:
  - Item.custom_bl resolving to Import File, or
  - Purchase Invoice.import_file (covers cars without BL).
"""

from __future__ import annotations

import frappe
from frappe.utils import flt, today


def is_vehicle_item(item_doc_or_name) -> bool:
	"""Vehicle = has chassis and/or maker (Mukechi / MKT / manual cars)."""
	if isinstance(item_doc_or_name, str):
		row = frappe.db.get_value(
			"Item",
			item_doc_or_name,
			["custom_chassis_no", "custom_maker"],
			as_dict=True,
		)
		if not row:
			return False
		chassis = (row.custom_chassis_no or "").strip()
		maker = (row.custom_maker or "").strip()
	else:
		chassis = (item_doc_or_name.get("custom_chassis_no") or "").strip()
		maker = (item_doc_or_name.get("custom_maker") or "").strip()
	return bool(chassis or maker)


def resolve_import_file_for_item(item_doc_or_name):
	"""Match Import File by Item.custom_bl → bl_number or supplier_invoice_no."""
	if isinstance(item_doc_or_name, str):
		bl = (frappe.db.get_value("Item", item_doc_or_name, "custom_bl") or "").strip()
	else:
		bl = (item_doc_or_name.get("custom_bl") or "").strip()
	if not bl:
		return None
	by_bl = frappe.db.get_value("Import File", {"bl_number": bl}, "name")
	if by_bl:
		return by_bl
	return frappe.db.get_value("Import File", {"supplier_invoice_no": bl}, "name")


def resolve_import_file_for_item_via_pi(item_code):
	"""Fallback: latest Purchase Invoice that includes this Item and has import_file."""
	if not item_code or not frappe.db.has_column("Purchase Invoice", "import_file"):
		return None
	rows = frappe.db.sql(
		"""
		SELECT pi.import_file
		FROM `tabPurchase Invoice Item` pii
		INNER JOIN `tabPurchase Invoice` pi ON pi.name = pii.parent
		WHERE pii.item_code = %s
			AND IFNULL(pi.import_file, '') != ''
			AND pi.docstatus < 2
		ORDER BY pi.modified DESC
		LIMIT 1
		""",
		item_code,
	)
	return rows[0][0] if rows else None


def pick_import_file(item_code, preferred=None, prefer_source=""):
	"""Prefer explicit Import File (e.g. from PI); else BL; else PI lookup.

	If preferred (PI) and BL resolve to different files, keep preferred and warn.
	"""
	preferred = (preferred or "").strip() or None
	by_bl = resolve_import_file_for_item(item_code)
	if preferred and by_bl and preferred != by_bl:
		frappe.logger("vsd_jan_integration").warning(
			f"Item {item_code}: Import File from {prefer_source or 'caller'} "
			f"'{preferred}' differs from BL match '{by_bl}' — using '{preferred}'"
		)
		return preferred
	if preferred:
		return preferred
	if by_bl:
		return by_bl
	return resolve_import_file_for_item_via_pi(item_code)


def get_fixed_costing_heads():
	"""Fixed heads whose **Actual** posts per vehicle (Costing.allocation_scope=By Vehicle).

	Heads with Actual By BL (e.g. CLEARING CONTAINER) stay Fixed for Car Costing
	Expected defaults, but are excluded here so Actual is uploaded as one BL JE.
	"""
	return frappe.get_all(
		"Costing",
		filters={
			"disabled": 0,
			"entry_mode": "Fixed",
			"allocation_scope": "By Vehicle",
			"default_projected_amount": [">", 0],
			"account": ["is", "set"],
			"payable_account": ["is", "set"],
		},
		fields=[
			"name",
			"costing_code",
			"costing_name",
			"account",
			"payable_account",
			"currency",
			"default_projected_amount",
		],
		order_by="costing_name asc",
	)


def ensure_draft_car_costing(item_code, import_file=None, force_reload=False):
	"""Create or refresh draft Car Costing so Fixed expected lines are filled.

	By default, if a draft already exists, only patch import_file when needed
	(avoids full load_from_item on bulk MKT — that was hanging the import).
	"""
	from vsd_jan_integration.vsd_jan_international_customization.doctype.car_costing.car_costing import (
		load_from_item,
	)

	existing = None
	if import_file:
		existing = frappe.db.get_value(
			"Car Costing",
			{"item": item_code, "import_file": import_file, "docstatus": 0},
			"name",
			order_by="modified desc",
		)
	if not existing:
		existing = frappe.db.get_value(
			"Car Costing",
			{"item": item_code, "docstatus": 0},
			"name",
			order_by="modified desc",
		)

	if existing and not force_reload:
		if import_file:
			cur = frappe.db.get_value("Car Costing", existing, "import_file")
			if cur != import_file:
				frappe.db.set_value("Car Costing", existing, "import_file", import_file, update_modified=False)
		return existing

	if existing:
		return load_from_item(docname=existing, import_file=import_file)
	return load_from_item(item=item_code, import_file=import_file)


def _buying_rate(from_currency, to_currency, rate_cache, get_exchange_rate):
	"""Cached buying exchange rate (with inverse fallback)."""
	if not from_currency or not to_currency or from_currency == to_currency:
		return 1.0
	key = (from_currency, to_currency)
	if key in rate_cache:
		return rate_cache[key]
	rate = 0.0
	if get_exchange_rate:
		rate = flt(get_exchange_rate(from_currency, to_currency, today(), "for_buying")) or 0
		if not rate:
			inv = flt(get_exchange_rate(to_currency, from_currency, today(), "for_buying")) or 0
			rate = (1.0 / inv) if inv else 1.0
	rate = rate or 1.0
	rate_cache[key] = rate
	return rate


def _build_fixed_je_template(company, heads=None):
	"""Precompute Fixed Costing debit/credit lines once for the whole batch.

	Each head credits its payable in the **same account currency and amount** as
	the expense debit (JPY↔JPY, TZS↔TZS). Payables must already match expense
	currency via Costing.payable_account setup.
	"""
	from collections import defaultdict

	try:
		from erpnext.setup.utils import get_exchange_rate
	except Exception:
		get_exchange_rate = None

	heads = heads or get_fixed_costing_heads()
	comp_currency = frappe.db.get_value("Company", company, "default_currency") or "TZS"
	cost_center = (
		frappe.db.get_value("Company", company, "cost_center")
		or frappe.db.get_value("Cost Center", {"company": company, "is_group": 0}, "name")
	)
	rate_cache = {}
	acc_curr_cache = {}
	debit_lines = []
	# payable → {curr, amt_in_acc, base, ex_rate}
	payable_totals = defaultdict(lambda: {"curr": None, "amt": 0.0, "base": 0.0, "ex_rate": 1.0})
	has_foreign = False

	for h in heads:
		amt = flt(h.default_projected_amount)
		if amt <= 0 or not h.account or not h.payable_account:
			continue
		if h.account not in acc_curr_cache:
			acc_curr_cache[h.account] = (
				frappe.db.get_value("Account", h.account, "account_currency") or comp_currency
			)
		acc_curr = acc_curr_cache[h.account]
		costing_curr = h.currency or acc_curr

		amt_in_acc = amt
		if costing_curr != acc_curr:
			amt_in_acc = amt * _buying_rate(costing_curr, acc_curr, rate_cache, get_exchange_rate)

		if acc_curr != comp_currency:
			ex_rate = _buying_rate(acc_curr, comp_currency, rate_cache, get_exchange_rate)
			base_amt = amt_in_acc * ex_rate
			has_foreign = True
		else:
			base_amt = amt_in_acc
			ex_rate = 1.0

		debit_lines.append(
			{
				"account": h.account,
				"debit_in_account_currency": amt_in_acc,
				"debit": base_amt,
				"account_currency": acc_curr,
				"exchange_rate": ex_rate,
				"cost_center": cost_center,
				"user_remark": h.costing_name or h.costing_code,
			}
		)

		# Payable must mirror expense currency — convert only if setup is wrong
		if h.payable_account not in acc_curr_cache:
			acc_curr_cache[h.payable_account] = (
				frappe.db.get_value("Account", h.payable_account, "account_currency") or comp_currency
			)
		pay_curr = acc_curr_cache[h.payable_account]
		if pay_curr == acc_curr:
			credit_in_acc = amt_in_acc
			credit_base = base_amt
			credit_rate = ex_rate
		else:
			# Fallback: convert expense amount into payable currency
			credit_in_acc = amt_in_acc * _buying_rate(acc_curr, pay_curr, rate_cache, get_exchange_rate)
			if pay_curr != comp_currency:
				credit_rate = _buying_rate(pay_curr, comp_currency, rate_cache, get_exchange_rate)
				credit_base = credit_in_acc * credit_rate
				has_foreign = True
			else:
				credit_rate = 1.0
				credit_base = credit_in_acc

		bucket = payable_totals[h.payable_account]
		bucket["curr"] = pay_curr
		bucket["amt"] += flt(credit_in_acc)
		bucket["base"] += flt(credit_base)
		bucket["ex_rate"] = credit_rate
		if pay_curr != comp_currency:
			has_foreign = True

	credit_lines = []
	for payable_acc, tot in payable_totals.items():
		pay_curr = tot["curr"] or comp_currency
		credit_lines.append(
			{
				"account": payable_acc,
				"credit_in_account_currency": tot["amt"],
				"credit": tot["base"],
				"account_currency": pay_curr,
				"exchange_rate": tot["ex_rate"] if pay_curr != comp_currency else 1.0,
				"cost_center": cost_center,
			}
		)

	return {
		"company": company,
		"comp_currency": comp_currency,
		"debit_lines": debit_lines,
		"credit_lines": credit_lines,
		"has_foreign": has_foreign,
		"ok": bool(debit_lines and credit_lines),
	}



def _fixed_je_name(item_code):
	"""Deterministic name — avoids tabSeries FOR UPDATE on every insert.

	If a cancelled JE still occupies the hash name, use FCJV-{digest}-N.
	"""
	import hashlib

	digest = hashlib.md5(f"FIXED|{item_code}".encode()).hexdigest()[:12].upper()
	base = f"FCJV-{digest}"
	if not frappe.db.exists("Journal Entry", base):
		return base
	for n in range(1, 50):
		candidate = f"{base}-{n}"
		if not frappe.db.exists("Journal Entry", candidate):
			return candidate
	return f"{base}-{frappe.generate_hash(length=4)}"


def create_or_update_fixed_costing_journal_entry(
	item_code,
	import_file=None,
	company=None,
	auto_submit=False,
	template=None,
	item_row=None,
):
	"""One JE per Item with all Fixed Costing debit lines + payable credits.

	Requires Import File. Idempotent via cheque_no = FIXED|{item_code}.
	Pass `template` from _build_fixed_je_template for bulk speed.
	"""
	company = company or frappe.defaults.get_user_default("Company") or frappe.db.get_single_value(
		"Global Defaults", "default_company"
	)
	if not company:
		return None, False

	if template is None:
		template = _build_fixed_je_template(company)
	if not template.get("ok"):
		return None, False

	if item_row is None:
		item_row = frappe.db.get_value(
			"Item",
			item_code,
			["name", "custom_chassis_no", "custom_bl"],
			as_dict=True,
		) or {}
	chassis = (item_row.get("custom_chassis_no") or "").strip()
	import_file = (import_file or "").strip() or pick_import_file(item_code)
	if not import_file:
		return None, False

	cheque_no = f"FIXED|{item_code}"[:140]
	existing = frappe.db.get_value(
		"Journal Entry",
		{"cheque_no": cheque_no, "company": company, "docstatus": ["!=", 2]},
		["name", "docstatus"],
		as_dict=True,
	)
	if existing:
		_set_je_item_links(existing.name, item_code, chassis, import_file)
		return existing.name, False

	jv = frappe.new_doc("Journal Entry")
	jv.name = _fixed_je_name(item_code)
	jv.voucher_type = "Journal Entry"
	jv.company = company
	jv.posting_date = today()
	jv.cheque_no = cheque_no
	jv.cheque_date = today()
	jv.user_remark = f"FIXED COSTING | {chassis or item_code} | {item_code}"
	jv.title = f"Fixed Costing | {chassis or item_code}"[:140]
	jv.multi_currency = 1 if template["has_foreign"] else 0

	if hasattr(jv, "import_file"):
		jv.import_file = import_file
	if frappe.db.has_column("Journal Entry", "custom_item"):
		jv.custom_item = item_code
	if frappe.db.has_column("Journal Entry", "custom_chassis_no"):
		jv.custom_chassis_no = chassis

	for line in template["debit_lines"]:
		jv.append("accounts", dict(line))
	for line in template["credit_lines"]:
		row = dict(line)
		row["user_remark"] = f"Payable for Fixed Costing — {chassis or item_code}"
		jv.append("accounts", row)

	# ignore_validate skips ERPNext total calc — set explicitly for list/form display
	jv.total_debit = sum(flt(r.debit) for r in jv.accounts)
	jv.total_credit = sum(flt(r.credit) for r in jv.accounts)
	jv.difference = abs(flt(jv.total_debit) - flt(jv.total_credit))

	jv.flags.ignore_mandatory = True
	jv.flags.ignore_permissions = True
	jv.flags.ignore_links = True
	jv.flags.ignore_validate = True
	# Name already set — skip naming series (major lock/contention source)
	prev_in_import = getattr(frappe.flags, "in_import", False)
	frappe.flags.in_import = True
	try:
		try:
			jv.insert(ignore_permissions=True, set_name=jv.name)
		except TypeError:
			# Older frappe: set_name kw not supported — name already on doc
			jv.insert(ignore_permissions=True)
		except frappe.DuplicateEntryError:
			# Cancelled JE may still hold the hash name — pick next free suffix
			jv.name = _fixed_je_name(item_code)
			try:
				jv.insert(ignore_permissions=True, set_name=jv.name)
			except TypeError:
				jv.insert(ignore_permissions=True)
			except frappe.DuplicateEntryError:
				existing = frappe.db.get_value(
					"Journal Entry",
					{"cheque_no": cheque_no, "company": company, "docstatus": ["!=", 2]},
					"name",
				)
				if existing:
					_set_je_item_links(existing, item_code, chassis, import_file)
					return existing, False
				raise
	finally:
		frappe.flags.in_import = prev_in_import

	if auto_submit and jv.docstatus == 0:
		jv.flags.ignore_mandatory = True
		jv.submit()

	return jv.name, True


def _set_je_item_links(je_name, item_code, chassis, import_file):
	if frappe.db.has_column("Journal Entry", "custom_item"):
		frappe.db.set_value("Journal Entry", je_name, "custom_item", item_code, update_modified=False)
	if frappe.db.has_column("Journal Entry", "custom_chassis_no") and chassis:
		frappe.db.set_value("Journal Entry", je_name, "custom_chassis_no", chassis, update_modified=False)
	if import_file and frappe.db.has_column("Journal Entry", "import_file"):
		frappe.db.set_value("Journal Entry", je_name, "import_file", import_file, update_modified=False)


def ensure_fixed_expected_for_item(
	item_code,
	import_file=None,
	prefer_source="",
	create_car_costing=True,
	create_journal_entry=True,
	auto_submit_jv=False,
	require_import_file_for_je=True,
	template=None,
	item_row=None,
	company=None,
):
	"""Idempotent ensure for one vehicle Item.

	- Car Costing: optional, no Import File required.
	- Fixed JE: only when Import File is known (unless require_import_file_for_je=False).
	"""
	if not item_code or not is_vehicle_item(item_code if item_row is None else item_row):
		return {"car_costing": None, "journal_entry": None, "import_file": None}

	if frappe.flags.get("in_fixed_costing_hook"):
		return {"car_costing": None, "journal_entry": None, "import_file": None}

	frappe.flags.in_fixed_costing_hook = True
	try:
		resolved = pick_import_file(item_code, preferred=import_file, prefer_source=prefer_source)
		cc_name = None
		je_name = None

		if create_car_costing:
			cc_name = ensure_draft_car_costing(item_code, import_file=resolved)

		if create_journal_entry:
			if require_import_file_for_je and not resolved:
				je_name = None
			else:
				company = company or frappe.defaults.get_user_default("Company") or frappe.db.get_single_value(
					"Global Defaults", "default_company"
				)
				je_name, _ = create_or_update_fixed_costing_journal_entry(
					item_code,
					import_file=resolved,
					company=company,
					auto_submit=auto_submit_jv,
					template=template,
					item_row=item_row,
				)

		return {"car_costing": cc_name, "journal_entry": je_name, "import_file": resolved}
	finally:
		frappe.flags.in_fixed_costing_hook = False


def ensure_fixed_costing_for_items(item_codes, auto_submit_jv=False, import_file=None):
	"""Batch ensure: Car Costing always; Fixed JE only when Import File resolvable.

	Optimized for thousands of cars:
	- one Fixed JE amount template (FX looked up once)
	- bulk prefetch of Items / Car Costings / existing JEs / Import Files
	- deterministic JE names (no tabSeries lock)
	- skip link rewrites when JE already exists
	- commit every 50 inserts (not every row)
	"""
	created_cc = []
	created_je = []
	errors = []
	codes = [c for c in (item_codes or []) if c]
	if not codes:
		return {"car_costings": created_cc, "journal_entries": created_je, "errors": errors}

	company = frappe.defaults.get_user_default("Company") or frappe.db.get_single_value(
		"Global Defaults", "default_company"
	)
	template = _build_fixed_je_template(company) if company else {"ok": False}

	prev_in_import = getattr(frappe.flags, "in_import", False)
	prev_mute = getattr(frappe.flags, "mute_messages", False)
	frappe.flags.in_import = True
	frappe.flags.mute_messages = True

	try:
		# Prefetch item rows
		item_map = {
			r.name: r
			for r in frappe.get_all(
				"Item",
				filters={"name": ["in", codes]},
				fields=["name", "custom_chassis_no", "custom_maker", "custom_bl"],
			)
		}

		# Prefetch draft Car Costings (item → name, import_file)
		cc_map = {}
		for chunk_start in range(0, len(codes), 500):
			chunk = codes[chunk_start : chunk_start + 500]
			for r in frappe.get_all(
				"Car Costing",
				filters={"item": ["in", chunk], "docstatus": 0},
				fields=["name", "item", "import_file", "modified"],
				order_by="modified desc",
			):
				# first (newest) wins
				if r.item not in cc_map:
					cc_map[r.item] = r

		# Prefetch existing Fixed JEs
		cheque_nos = [f"FIXED|{c}"[:140] for c in codes]
		existing_je = {}
		for chunk_start in range(0, len(cheque_nos), 500):
			chunk = cheque_nos[chunk_start : chunk_start + 500]
			for r in frappe.get_all(
				"Journal Entry",
				filters={"cheque_no": ["in", chunk], "company": company, "docstatus": ["!=", 2]},
				fields=["name", "cheque_no", "docstatus"],
			):
				existing_je[r.cheque_no] = r

		# Prefetch Import File by BL / supplier invoice
		bls = list(
			{(item_map[c].custom_bl or "").strip() for c in codes if c in item_map and item_map[c].custom_bl}
		)
		bl_to_if = {}
		if bls:
			for chunk_start in range(0, len(bls), 500):
				chunk = bls[chunk_start : chunk_start + 500]
				for r in frappe.get_all(
					"Import File",
					filters={"bl_number": ["in", chunk]},
					fields=["name", "bl_number"],
				):
					if r.bl_number:
						bl_to_if[r.bl_number.strip()] = r.name
				for r in frappe.get_all(
					"Import File",
					filters={"supplier_invoice_no": ["in", chunk]},
					fields=["name", "supplier_invoice_no"],
				):
					key = (r.supplier_invoice_no or "").strip()
					if key and key not in bl_to_if:
						bl_to_if[key] = r.name

		# Prefetch PI→Import File for cars without BL match
		need_pi = [
			c for c in codes if c in item_map and (item_map[c].custom_bl or "").strip() not in bl_to_if
		]
		pi_if = {}
		if need_pi and frappe.db.has_column("Purchase Invoice", "import_file"):
			for chunk_start in range(0, len(need_pi), 300):
				chunk = need_pi[chunk_start : chunk_start + 300]
				rows = frappe.db.sql(
					"""
					SELECT pii.item_code, pi.import_file
					FROM `tabPurchase Invoice Item` pii
					INNER JOIN `tabPurchase Invoice` pi ON pi.name = pii.parent
					WHERE pii.item_code IN ({})
						AND IFNULL(pi.import_file, '') != ''
						AND pi.docstatus < 2
					ORDER BY pi.modified DESC
					""".format(",".join(["%s"] * len(chunk))),
					tuple(chunk),
				)
				for item_code, if_name in rows:
					if item_code not in pi_if:
						pi_if[item_code] = if_name

		pending_commit = 0
		COMMIT_EVERY = 50

		for item_code in codes:
			try:
				row = item_map.get(item_code)
				if not row or not is_vehicle_item(row):
					continue

				bl = (row.custom_bl or "").strip()
				resolved = (import_file or "").strip() or bl_to_if.get(bl) or pi_if.get(item_code)

				# Car Costing — only create if missing (skip heavy load_from_item when present)
				cc_row = cc_map.get(item_code)
				if not cc_row:
					cc_name = ensure_draft_car_costing(item_code, import_file=resolved)
					if cc_name:
						created_cc.append(cc_name)
						cc_map[item_code] = frappe._dict(
							name=cc_name, item=item_code, import_file=resolved
						)
						pending_commit += 1
				elif resolved and (cc_row.import_file or "") != resolved:
					frappe.db.set_value(
						"Car Costing",
						cc_row.name,
						"import_file",
						resolved,
						update_modified=False,
					)
					cc_row.import_file = resolved

				cheque_no = f"FIXED|{item_code}"[:140]
				if cheque_no in existing_je:
					# Already exists — do not rewrite links on every batch (was thousands of UPDATEs)
					created_je.append(existing_je[cheque_no].name)
				elif resolved and template.get("ok"):
					je_name, is_new = create_or_update_fixed_costing_journal_entry(
						item_code,
						import_file=resolved,
						company=company,
						auto_submit=auto_submit_jv,
						template=template,
						item_row=row,
					)
					if je_name:
						created_je.append(je_name)
						if is_new:
							pending_commit += 1
							existing_je[cheque_no] = frappe._dict(
								name=je_name, cheque_no=cheque_no, docstatus=0
							)

				if pending_commit >= COMMIT_EVERY:
					frappe.db.commit()
					pending_commit = 0
			except Exception:
				frappe.db.rollback()
				pending_commit = 0
				frappe.log_error(
					title=f"Fixed Costing for Item {item_code}",
					message=frappe.get_traceback(),
				)
				errors.append(item_code)

		frappe.db.commit()
	finally:
		frappe.flags.in_import = prev_in_import
		frappe.flags.mute_messages = prev_mute

	frappe.logger("vsd_jan_integration").info(
		f"Fixed Costing batch: items={len(codes)} je={len(created_je)} cc={len(created_cc)} errors={len(errors)}"
	)
	return {"car_costings": created_cc, "journal_entries": created_je, "errors": errors}


def enqueue_fixed_costing_for_items(item_codes, ref_doc=None, auto_submit_jv=False):
	"""Run Fixed Costing ensure in background so MKT/Mukechi import can finish.

	Uses a single long job (chunked internally) to avoid stampeding tabSeries locks
	with many parallel JE inserts.
	"""
	if not item_codes:
		return
	codes = list(dict.fromkeys([c for c in item_codes if c]))
	frappe.enqueue(
		"vsd_jan_integration.vsd_jan_international_customization.utils.mkt_fixed_costing.ensure_fixed_costing_for_items",
		item_codes=codes,
		auto_submit_jv=auto_submit_jv,
		queue="long",
		timeout=7200,
		job_name=f"fixed_costing:{(ref_doc or 'bulk')}",
		# dedupe if same importer requeues
		enqueue_after_commit=True,
	)


def enqueue_draft_car_costings(item_codes, ref_doc=None):
	"""Background job: create missing draft Car Costings after bulk Item import."""
	if not item_codes:
		return
	frappe.enqueue(
		"vsd_jan_integration.vsd_jan_international_customization.utils.mkt_fixed_costing.create_missing_draft_car_costings",
		item_codes=list(item_codes),
		ref_doc=ref_doc,
		queue="long",
		timeout=7200,
		job_name=f"draft_car_costings:{(ref_doc or 'bulk')}",
	)


def create_missing_draft_car_costings(item_codes, ref_doc=None):
	"""Create draft Car Costing only where missing (idempotent, no Fixed JE)."""
	created = 0
	skipped = 0
	errors = 0
	for idx, item_code in enumerate(item_codes or [], start=1):
		if not item_code or not is_vehicle_item(item_code):
			continue
		try:
			exists = frappe.db.exists("Car Costing", {"item": item_code, "docstatus": 0})
			if exists:
				skipped += 1
				continue
			if ensure_draft_car_costing(item_code):
				created += 1
			if idx % 50 == 0:
				frappe.db.commit()
		except Exception:
			errors += 1
			if errors <= 20 or errors % 50 == 0:
				frappe.log_error(
					title=f"Draft Car Costing for {item_code}",
					message=frappe.get_traceback(),
				)
	frappe.db.commit()
	frappe.logger("vsd_jan_integration").info(
		f"draft Car Costings ref={ref_doc}: created={created} skipped={skipped} errors={errors}"
	)
	return {"created": created, "skipped": skipped, "errors": errors}
