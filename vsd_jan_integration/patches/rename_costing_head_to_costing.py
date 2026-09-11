# Copyright (c) 2026, VV Systems Developer LTD and contributors
# For license information, please see license.txt

"""Rename DocType Costing Head → Costing (must run before model sync)."""

import frappe


def execute():
	old = "Costing Head"
	new = "Costing"

	# 1) Rename DocType metadata if old still exists
	if frappe.db.exists("DocType", old) and not frappe.db.exists("DocType", new):
		frappe.rename_doc("DocType", old, new, force=True)
	elif frappe.db.exists("DocType", old) and frappe.db.exists("DocType", new):
		# Orphaned old DocType row — delete after data move
		pass

	# 2) Move rows if old table still has data and new is empty/missing rows
	_migrate_table_data(old, new)

	# 3) Fix Link field options/labels
	frappe.db.sql(
		"UPDATE `tabDocField` SET options=%s WHERE fieldtype='Link' AND options=%s",
		(new, old),
	)
	frappe.db.sql(
		"UPDATE `tabCustom Field` SET options=%s WHERE fieldtype='Link' AND options=%s",
		(new, old),
	)
	frappe.db.sql(
		"UPDATE `tabDocField` SET label=%s WHERE fieldtype='Link' AND options=%s AND label=%s",
		(new, new, old),
	)

	# 4) Drop leftover old DocType + table if safe
	if frappe.db.exists("DocType", old) and frappe.db.exists("DocType", new):
		frappe.delete_doc("DocType", old, force=1)
	if frappe.db.table_exists(old) and frappe.db.table_exists(new):
		# Only drop old table after copy
		old_count = frappe.db.sql(f"SELECT COUNT(*) FROM `tab{old}`")[0][0]
		new_count = frappe.db.sql(f"SELECT COUNT(*) FROM `tab{new}`")[0][0]
		if new_count >= old_count and old_count >= 0:
			frappe.db.sql_ddl(f"DROP TABLE IF EXISTS `tab{old}`")

	frappe.clear_cache()


def _migrate_table_data(old, new):
	if not frappe.db.table_exists(old):
		return
	if not frappe.db.table_exists(new):
		return

	old_count = frappe.db.sql(f"SELECT COUNT(*) FROM `tab{old}`")[0][0]
	new_count = frappe.db.sql(f"SELECT COUNT(*) FROM `tab{new}`")[0][0]
	if not old_count:
		return
	if new_count >= old_count:
		return

	# Common columns only
	old_cols = {c[0] for c in frappe.db.sql(f"SHOW COLUMNS FROM `tab{old}`")}
	new_cols = {c[0] for c in frappe.db.sql(f"SHOW COLUMNS FROM `tab{new}`")}
	cols = [c for c in old_cols & new_cols]
	col_list = ", ".join(f"`{c}`" for c in cols)
	frappe.db.sql(
		f"""
		INSERT IGNORE INTO `tab{new}` ({col_list})
		SELECT {col_list} FROM `tab{old}`
		"""
	)
	frappe.db.commit()
