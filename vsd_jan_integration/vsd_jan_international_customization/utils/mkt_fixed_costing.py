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
	return frappe.get_all(
		"Costing",
		filters={
			"disabled": 0,
			"entry_mode": "Fixed",
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


def create_or_update_fixed_costing_journal_entry(item_code, import_file=None, company=None, auto_submit=False):
	"""One JE per Item with all Fixed Costing debit lines + payable credits.

	Requires Import File. Idempotent via cheque_no = FIXED|{item_code}.
	"""
	heads = get_fixed_costing_heads()
	if not heads:
		return None, False

	item = frappe.get_doc("Item", item_code)
	chassis = (item.get("custom_chassis_no") or "").strip()
	import_file = (import_file or "").strip() or pick_import_file(item_code)
	if not import_file:
		# Expected Fixed JE only once the car is tied to an Import File
		return None, False

	company = company or frappe.defaults.get_user_default("Company") or frappe.db.get_single_value(
		"Global Defaults", "default_company"
	)
	if not company:
		return None, False

	cheque_no = f"FIXED|{item_code}"[:140]
	existing = frappe.db.get_value(
		"Journal Entry",
		{"cheque_no": cheque_no, "company": company, "docstatus": ["!=", 2]},
		["name", "docstatus"],
		as_dict=True,
	)
	if existing and existing.docstatus == 1:
		_set_je_item_links(existing.name, item_code, chassis, import_file)
		return existing.name, False

	# Draft already exists — do not rebuild accounts on every bulk pass (lock storm)
	if existing and existing.docstatus == 0:
		_set_je_item_links(existing.name, item_code, chassis, import_file)
		return existing.name, False

	jv = frappe.new_doc("Journal Entry")
	jv.voucher_type = "Journal Entry"
	jv.company = company
	is_new = True

	jv.posting_date = today()
	jv.cheque_no = cheque_no
	jv.cheque_date = today()
	jv.user_remark = f"FIXED COSTING | {chassis or item_code} | {item_code}"
	jv.title = f"Fixed Costing | {chassis or item_code}"[:140]

	if hasattr(jv, "import_file"):
		jv.import_file = import_file
	if frappe.db.has_column("Journal Entry", "custom_item"):
		jv.custom_item = item_code
	if frappe.db.has_column("Journal Entry", "custom_chassis_no"):
		jv.custom_chassis_no = chassis

	jv.accounts = []
	from collections import defaultdict

	try:
		from erpnext.setup.utils import get_exchange_rate
	except Exception:
		get_exchange_rate = None

	payable_base_totals = defaultdict(float)
	comp_currency = frappe.db.get_value("Company", company, "default_currency") or "TZS"
	has_foreign = False

	for h in heads:
		amt = flt(h.default_projected_amount)
		if amt <= 0 or not h.account:
			continue
		acc_curr = frappe.db.get_value("Account", h.account, "account_currency") or comp_currency
		costing_curr = h.currency or acc_curr

		# Excel Expected may be USD while GL account is JPY — convert Expected → account currency
		amt_in_acc = amt
		if costing_curr != acc_curr:
			rate_to_acc = 1.0
			if get_exchange_rate:
				rate_to_acc = flt(get_exchange_rate(costing_curr, acc_curr, today(), "for_buying")) or 0
				if not rate_to_acc:
					inv = flt(get_exchange_rate(acc_curr, costing_curr, today(), "for_buying")) or 0
					rate_to_acc = (1.0 / inv) if inv else 1.0
			amt_in_acc = amt * (rate_to_acc or 1.0)

		if acc_curr != comp_currency:
			rate = 1.0
			if get_exchange_rate:
				rate = flt(get_exchange_rate(acc_curr, comp_currency, today(), "for_buying")) or 1.0
			base_amt = amt_in_acc * rate
			ex_rate = rate
			has_foreign = True
		else:
			base_amt = amt_in_acc
			ex_rate = 1

		jv.append(
			"accounts",
			{
				"account": h.account,
				"debit_in_account_currency": amt_in_acc,
				"debit": base_amt,
				"account_currency": acc_curr,
				"exchange_rate": ex_rate,
				"user_remark": h.costing_name or h.costing_code,
			},
		)
		payable_base_totals[h.payable_account] += base_amt

	if not payable_base_totals:
		return None, False

	jv.multi_currency = 1 if has_foreign else 0

	for payable_acc, total in payable_base_totals.items():
		acc_type = frappe.db.get_value("Account", payable_acc, "account_type")
		row = {
			"account": payable_acc,
			"credit_in_account_currency": total,
			"credit": total,
			"account_currency": comp_currency,
			"exchange_rate": 1,
			"user_remark": f"Payable for Fixed Costing — {chassis or item_code}",
		}
		if acc_type == "Payable":
			supplier = (
				frappe.db.get_value("Supplier", {"name": "JAN JAPAN"}, "name")
				or frappe.db.get_value("Supplier", {"disabled": 0}, "name", order_by="creation asc")
			)
			if supplier:
				row["party_type"] = "Supplier"
				row["party"] = supplier
		jv.append("accounts", row)

	jv.flags.ignore_mandatory = True
	jv.flags.ignore_permissions = True
	jv.flags.ignore_links = True

	if is_new:
		jv.insert(ignore_permissions=True)
	else:
		jv.save(ignore_permissions=True)

	if auto_submit and jv.docstatus == 0:
		jv.flags.ignore_mandatory = True
		jv.submit()

	return jv.name, is_new


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
):
	"""Idempotent ensure for one vehicle Item.

	- Car Costing: optional, no Import File required.
	- Fixed JE: only when Import File is known (unless require_import_file_for_je=False).
	"""
	if not item_code or not is_vehicle_item(item_code):
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
				company = frappe.defaults.get_user_default("Company") or frappe.db.get_single_value(
					"Global Defaults", "default_company"
				)
				je_name, _ = create_or_update_fixed_costing_journal_entry(
					item_code,
					import_file=resolved,
					company=company,
					auto_submit=auto_submit_jv,
				)

		return {"car_costing": cc_name, "journal_entry": je_name, "import_file": resolved}
	finally:
		frappe.flags.in_fixed_costing_hook = False


def ensure_fixed_costing_for_items(item_codes, auto_submit_jv=False, import_file=None):
	"""Batch ensure: Car Costing always; Fixed JE only when Import File resolvable."""
	created_cc = []
	created_je = []
	errors = []

	for idx, item_code in enumerate(item_codes or [], start=1):
		if not item_code:
			continue
		try:
			res = ensure_fixed_expected_for_item(
				item_code,
				import_file=import_file,
				create_car_costing=True,
				create_journal_entry=True,
				auto_submit_jv=auto_submit_jv,
				require_import_file_for_je=True,
			)
			if res.get("car_costing"):
				created_cc.append(res["car_costing"])
			if res.get("journal_entry"):
				created_je.append(res["journal_entry"])
			# Commit every item — JE naming uses tabSeries FOR UPDATE; holding it
			# across hundreds of inserts deadlocks the whole site.
			frappe.db.commit()
		except Exception:
			frappe.db.rollback()
			frappe.log_error(
				title=f"Fixed Costing for Item {item_code}",
				message=frappe.get_traceback(),
			)
			errors.append(item_code)

	frappe.db.commit()
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
