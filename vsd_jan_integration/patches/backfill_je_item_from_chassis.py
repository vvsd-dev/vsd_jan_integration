# Copyright (c) 2026, VV Systems Developer LTD and contributors
# For license information, please see license.txt

"""Backfill Journal Entry.custom_item from chassis in user_remark/title when unique."""

import frappe


def execute():
	if not frappe.db.has_column("Journal Entry", "custom_item"):
		return

	items = frappe.get_all(
		"Item",
		filters={"disabled": 0, "custom_chassis_no": ["is", "set"]},
		fields=["name", "custom_chassis_no"],
	)
	chassis_map = {}
	for it in items:
		ch = (it.custom_chassis_no or "").strip().upper()
		if not ch:
			continue
		chassis_map.setdefault(ch, []).append(it.name)

	jes = frappe.db.sql(
		"""
		SELECT name, user_remark, title, import_file, custom_item
		FROM `tabJournal Entry`
		WHERE docstatus != 2
			AND IFNULL(custom_item, '') = ''
			AND (
				IFNULL(user_remark, '') != ''
				OR IFNULL(title, '') != ''
			)
		""",
		as_dict=True,
	)

	updated = 0
	for je in jes:
		hint = f"{je.user_remark or ''} {je.title or ''}".upper()
		matches = []
		for ch, item_names in chassis_map.items():
			if ch and ch in hint:
				matches.extend(item_names)
		# Only unique item match
		matches = list(dict.fromkeys(matches))
		if len(matches) != 1:
			continue
		item_code = matches[0]
		chassis = frappe.db.get_value("Item", item_code, "custom_chassis_no")
		frappe.db.set_value("Journal Entry", je.name, "custom_item", item_code, update_modified=False)
		if frappe.db.has_column("Journal Entry", "custom_chassis_no") and chassis:
			frappe.db.set_value(
				"Journal Entry", je.name, "custom_chassis_no", chassis, update_modified=False
			)
		updated += 1

	frappe.db.commit()
	frappe.logger().info(f"backfill_je_item_from_chassis: updated {updated} Journal Entries")
