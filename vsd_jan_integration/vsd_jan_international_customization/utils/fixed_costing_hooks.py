# Copyright (c) 2026, VV Systems Developer LTD and contributors
# For license information, please see license.txt

"""Doc event hooks for draft Car Costing + Fixed expected JEs."""

from __future__ import annotations

import frappe

from vsd_jan_integration.vsd_jan_international_customization.utils.mkt_fixed_costing import (
	ensure_fixed_expected_for_item,
	is_vehicle_item,
	pick_import_file,
)


def _safe_ensure(item_code, **kwargs):
	if not item_code:
		return
	try:
		ensure_fixed_expected_for_item(item_code, **kwargs)
	except Exception:
		frappe.log_error(
			title=f"Fixed Costing hook failed for {item_code}",
			message=frappe.get_traceback(),
		)


# ---------------------------------------------------------------------------
# Item
# ---------------------------------------------------------------------------


def item_after_insert(doc, method=None):
	"""Vehicle create → draft Car Costing only. Fixed JE only if Import File already known."""
	if frappe.flags.get("in_fixed_costing_hook") or frappe.flags.get("skip_fixed_costing_hooks"):
		return
	if not is_vehicle_item(doc):
		return

	resolved = pick_import_file(doc.name)
	_safe_ensure(
		doc.name,
		import_file=resolved,
		prefer_source="item_insert",
		create_car_costing=True,
		# JE only when BL (or PI) already ties the car to an Import File at create time
		create_journal_entry=bool(resolved),
		require_import_file_for_je=True,
	)


def item_on_update(doc, method=None):
	"""When BL appears / changes and resolves to Import File → Fixed JE (+ refresh CC)."""
	if frappe.flags.get("in_fixed_costing_hook") or frappe.flags.get("skip_fixed_costing_hooks"):
		return
	if not is_vehicle_item(doc):
		return

	bl_changed = False
	try:
		bl_changed = doc.has_value_changed("custom_bl")
	except Exception:
		bl_changed = True

	chassis_changed = False
	try:
		chassis_changed = doc.has_value_changed("custom_chassis_no") or doc.has_value_changed("custom_maker")
	except Exception:
		chassis_changed = False

	# Becoming a vehicle mid-life (rare) → ensure draft Car Costing
	if chassis_changed and not bl_changed:
		_safe_ensure(
			doc.name,
			create_car_costing=True,
			create_journal_entry=False,
		)

	if not bl_changed:
		return

	resolved = pick_import_file(doc.name)
	if not resolved:
		# BL set but Import File not created yet — Car Costing only; Import File hook will finish JE
		_safe_ensure(
			doc.name,
			create_car_costing=True,
			create_journal_entry=False,
		)
		return

	_safe_ensure(
		doc.name,
		import_file=resolved,
		prefer_source="item_bl",
		create_car_costing=True,
		create_journal_entry=True,
		require_import_file_for_je=True,
	)


# ---------------------------------------------------------------------------
# Sales Invoice → Selling Costing JEs
# ---------------------------------------------------------------------------


def sales_invoice_on_submit(doc, method=None):
	"""Post Selling / Both costing Journal Entries from vehicle SI lines."""
	if frappe.flags.get("skip_selling_costing_hooks"):
		return
	try:
		from vsd_jan_integration.vsd_jan_international_customization.utils.selling_costing import (
			process_sales_invoice_selling_costing,
		)

		process_sales_invoice_selling_costing(doc)
	except Exception:
		frappe.log_error(
			title=f"Selling Costing hook failed for SI {doc.name}",
			message=frappe.get_traceback(),
		)


def sales_invoice_on_cancel(doc, method=None):
	"""Cancel Selling Costing JEs created for this Sales Invoice."""
	if frappe.flags.get("skip_selling_costing_hooks"):
		return
	try:
		from vsd_jan_integration.vsd_jan_international_customization.utils.selling_costing import (
			cancel_selling_journal_entries_for_si,
		)

		cancel_selling_journal_entries_for_si(doc)
	except Exception:
		frappe.log_error(
			title=f"Selling Costing cancel hook failed for SI {doc.name}",
			message=frappe.get_traceback(),
		)


# ---------------------------------------------------------------------------
# Purchase Invoice (covers cars without BL)
# ---------------------------------------------------------------------------


def _pi_import_file(doc):
	return (getattr(doc, "import_file", None) or getattr(doc, "custom_import_file", None) or "").strip() or None


def _pi_item_codes(doc):
	codes = []
	for row in doc.get("items") or []:
		code = (row.get("item_code") or "").strip()
		if code and code not in codes:
			codes.append(code)
	return codes


def purchase_invoice_after_save(doc, method=None):
	"""When PI has Import File, ensure Fixed expected for each vehicle line item."""
	if frappe.flags.get("in_fixed_costing_hook") or frappe.flags.get("skip_fixed_costing_hooks"):
		return
	if doc.docstatus == 2:
		return

	import_file = _pi_import_file(doc)
	if not import_file:
		return

	for item_code in _pi_item_codes(doc):
		if not is_vehicle_item(item_code):
			continue
		_safe_ensure(
			item_code,
			import_file=import_file,
			prefer_source=f"Purchase Invoice {doc.name}",
			create_car_costing=True,
			create_journal_entry=True,
			require_import_file_for_je=True,
		)


# ---------------------------------------------------------------------------
# Import File (BL set on IF after Items already have custom_bl — common MKT order)
# ---------------------------------------------------------------------------


def import_file_after_save(doc, method=None):
	"""When Import File is saved, catch Items linked by BL and by Purchase Invoice."""
	if frappe.flags.get("in_fixed_costing_hook") or frappe.flags.get("skip_fixed_costing_hooks"):
		return
	if doc.docstatus == 2:
		return

	item_codes = set()

	bl = (doc.get("bl_number") or "").strip()
	inv = (doc.get("supplier_invoice_no") or "").strip()
	if bl and frappe.db.has_column("Item", "custom_bl"):
		item_codes.update(
			frappe.get_all("Item", filters={"custom_bl": bl}, pluck="name")
		)
	if inv and frappe.db.has_column("Item", "custom_bl"):
		item_codes.update(
			frappe.get_all("Item", filters={"custom_bl": inv}, pluck="name")
		)

	# Items already on PIs pointing at this Import File (no-BL cars)
	if frappe.db.has_column("Purchase Invoice", "import_file"):
		pi_items = frappe.db.sql(
			"""
			SELECT DISTINCT pii.item_code
			FROM `tabPurchase Invoice Item` pii
			INNER JOIN `tabPurchase Invoice` pi ON pi.name = pii.parent
			WHERE pi.import_file = %s
				AND pi.docstatus < 2
				AND IFNULL(pii.item_code, '') != ''
			""",
			doc.name,
		)
		item_codes.update(r[0] for r in pi_items)

	for item_code in item_codes:
		if not is_vehicle_item(item_code):
			continue
		_safe_ensure(
			item_code,
			import_file=doc.name,
			prefer_source=f"Import File {doc.name}",
			create_car_costing=True,
			create_journal_entry=True,
			require_import_file_for_je=True,
		)
