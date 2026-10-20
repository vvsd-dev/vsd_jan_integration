# Copyright (c) 2026, VV Systems Developer LTD and contributors
# For license information, please see license.txt

"""Find draft Fixed Costing JEs, recreate broken ones, then submit all.

Usage:
  bench --site <site> execute vsd_jan_integration.scripts.fix_submit_fixed_costing_jes.execute
"""

from __future__ import annotations

import sys

import frappe
from frappe.utils import flt


def _log(msg):
	print(msg, flush=True)
	sys.stdout.flush()


def _find_draft_fixed_jes():
	"""All draft Fixed Costing JEs by cheque_no / remark / FCJV name."""
	return frappe.db.sql(
		"""
		SELECT name, cheque_no, custom_item, import_file, company, user_remark, title
		FROM `tabJournal Entry`
		WHERE docstatus = 0
			AND (
				cheque_no LIKE 'FIXED|%%'
				OR IFNULL(user_remark, '') LIKE 'FIXED COSTING%%'
				OR IFNULL(user_remark, '') LIKE '%%Fixed Costing%%'
				OR name LIKE 'FCJV-%%'
				OR IFNULL(title, '') LIKE 'Fixed Costing%%'
			)
		ORDER BY name
		""",
		as_dict=True,
	)


def _item_from_je(row):
	if row.custom_item:
		return row.custom_item
	cheque = row.cheque_no or ""
	if cheque.startswith("FIXED|"):
		return cheque[6:]
	return None


def _items_needing_recreate(drafts):
	"""Bulk SQL: drafts whose credits still hit Creditors* or miss expected payables."""
	from vsd_jan_integration.vsd_jan_international_customization.utils.mkt_fixed_costing import (
		get_fixed_costing_heads,
	)

	names = [d.name for d in drafts]
	if not names:
		return []

	# Any credit on Creditors* → recreate
	creditor_parents = set()
	for i in range(0, len(names), 500):
		chunk = names[i : i + 500]
		rows = frappe.db.sql(
			"""
			SELECT DISTINCT parent
			FROM `tabJournal Entry Account`
			WHERE parent IN %(names)s
				AND credit > 0
				AND account LIKE 'Creditors%%'
			""",
			{"names": chunk},
		)
		creditor_parents.update(r[0] for r in rows)

	expected_payables = {
		h.payable_account
		for h in get_fixed_costing_heads()
		if h.payable_account
	}
	missing_payable_parents = set()
	if expected_payables:
		for i in range(0, len(names), 500):
			chunk = names[i : i + 500]
			# parents that don't have ALL expected payable credits
			have = frappe.db.sql(
				"""
				SELECT parent, account
				FROM `tabJournal Entry Account`
				WHERE parent IN %(names)s
					AND credit > 0
					AND account IN %(pays)s
				""",
				{"names": chunk, "pays": list(expected_payables)},
			)
			by_parent = {}
			for parent, acc in have:
				by_parent.setdefault(parent, set()).add(acc)
			for name in chunk:
				got = by_parent.get(name) or set()
				if not expected_payables.issubset(got):
					missing_payable_parents.add(name)

	need = creditor_parents | missing_payable_parents
	items = []
	for d in drafts:
		if d.name in need:
			item = _item_from_je(d)
			if item:
				items.append(item)
	return list(dict.fromkeys(items))


def _fill_cost_centers(je_name, company):
	cc = (
		frappe.db.get_value("Company", company, "cost_center")
		or frappe.db.get_value("Cost Center", {"company": company, "is_group": 0}, "name")
	)
	if not cc:
		return 0
	return frappe.db.sql(
		"""
		UPDATE `tabJournal Entry Account`
		SET cost_center = %s
		WHERE parent = %s AND IFNULL(cost_center, '') = ''
		""",
		(cc, je_name),
	)


def _submit_one(je_name):
	"""Fix totals / cost centers / parties then submit. Returns (ok, err)."""
	from vsd_jan_integration.vsd_jan_international_customization.utils.mkt_fixed_costing import (
		ensure_journal_entry_payable_parties,
		resolve_supplier_for_fixed_je,
	)

	meta = frappe.db.get_value(
		"Journal Entry",
		je_name,
		["name", "docstatus", "company", "custom_item", "import_file", "cheque_no"],
		as_dict=True,
	)
	if not meta:
		return False, "missing"
	if meta.docstatus != 0:
		return False, f"docstatus={meta.docstatus}"

	item_code = meta.custom_item
	if not item_code and (meta.cheque_no or "").startswith("FIXED|"):
		item_code = meta.cheque_no[6:]

	supplier = resolve_supplier_for_fixed_je(
		import_file=meta.import_file, item_code=item_code
	)
	ensure_journal_entry_payable_parties(
		je_name,
		supplier=supplier,
		import_file=meta.import_file,
		item_code=item_code,
	)
	_fill_cost_centers(je_name, meta.company)

	doc = frappe.get_doc("Journal Entry", je_name)
	debit = sum(flt(r.debit) for r in doc.accounts)
	credit = sum(flt(r.credit) for r in doc.accounts)
	if debit and abs(flt(doc.total_debit) - debit) > 0.01:
		frappe.db.set_value(
			"Journal Entry",
			je_name,
			{
				"total_debit": debit,
				"total_credit": credit,
				"difference": abs(debit - credit),
			},
			update_modified=False,
		)
		doc.reload()

	cc = (
		frappe.db.get_value("Company", doc.company, "cost_center")
		or frappe.db.get_value(
			"Cost Center", {"company": doc.company, "is_group": 0}, "name"
		)
	)
	for row in doc.accounts:
		if not row.cost_center and cc:
			row.cost_center = cc

	doc.flags.ignore_permissions = True
	doc.flags.ignore_mandatory = True
	doc.submit()
	return True, None


def execute(limit=None, skip_recreate=False):
	"""Recreate broken draft Fixed JEs then submit all drafts."""
	from vsd_jan_integration.vsd_jan_international_customization.utils.mkt_fixed_costing import (
		ensure_fixed_costing_for_items,
	)

	frappe.set_user("Administrator")
	drafts = _find_draft_fixed_jes()
	found = len(drafts)
	_log(f"FOUND {found} draft Fixed Costing JE(s)")

	if limit:
		limit = int(limit)
		drafts = drafts[:limit]
		_log(f"LIMIT {limit}")

	fixed = 0
	items_to_ensure = []
	if not skip_recreate:
		items_to_ensure = _items_needing_recreate(drafts)
		_log(f"RECREATE needed for {len(items_to_ensure)} item(s)")
		CHUNK = 100
		for i in range(0, len(items_to_ensure), CHUNK):
			chunk = items_to_ensure[i : i + CHUNK]
			res = ensure_fixed_costing_for_items(chunk, auto_submit_jv=False)
			fixed += len(res.get("journal_entries") or [])
			errs = res.get("errors") or []
			if errs:
				_log(f"  ensure errors chunk@{i}: {errs[:10]}{'...' if len(errs) > 10 else ''}")
			frappe.db.commit()
			_log(f"  ensure progress {min(i + CHUNK, len(items_to_ensure))}/{len(items_to_ensure)}")
	else:
		_log("RECREATE skipped")

	# Re-fetch drafts after recreate
	drafts = _find_draft_fixed_jes()
	if limit:
		wanted = set()
		for d in _find_draft_fixed_jes():
			pass
		# keep limit on current drafts
		drafts = drafts[:limit]

	submitted = []
	failed = []
	_log(f"SUBMITTING {len(drafts)} draft(s)…")
	for idx, row in enumerate(drafts, start=1):
		je_name = row.name
		if not frappe.db.exists("Journal Entry", je_name):
			item = _item_from_je(row)
			cheque = f"FIXED|{item}"[:140] if item else None
			je_name = (
				frappe.db.get_value(
					"Journal Entry",
					{"cheque_no": cheque, "docstatus": 0},
					"name",
				)
				if cheque
				else None
			)
			if not je_name:
				failed.append((row.name, "deleted and not recreated"))
				continue

		try:
			ok, err = _submit_one(je_name)
			if ok:
				submitted.append(je_name)
				frappe.db.commit()
			else:
				failed.append((je_name, err or "submit returned false"))
				frappe.db.rollback()
		except Exception as e:
			failed.append((je_name, str(e)[:400]))
			frappe.db.rollback()

		if idx % 25 == 0 or idx == len(drafts):
			_log(f"  submit progress {idx}/{len(drafts)} ok={len(submitted)} fail={len(failed)}")

	_log("=" * 60)
	_log(
		f"COUNTS found={found} fixed/recreated≈{fixed} submitted={len(submitted)} failed={len(failed)}"
	)
	if failed:
		_log("FAILURES (first 30):")
		for name, err in failed[:30]:
			_log(f"  {name}: {err}")
	return {
		"found": found,
		"fixed": fixed,
		"submitted": len(submitted),
		"failed": len(failed),
		"failures": failed[:50],
	}
