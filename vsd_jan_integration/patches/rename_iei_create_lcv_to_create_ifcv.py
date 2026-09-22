import frappe
from frappe.model.utils.rename_field import rename_field


def execute():
	"""Item Excel Importer: Create Landed Cost Voucher → Create Import File Cost Voucher."""
	if not frappe.db.exists("DocType", "Item Excel Importer"):
		return

	has_old = frappe.db.has_column("Item Excel Importer", "create_lcv")
	has_new = frappe.db.has_column("Item Excel Importer", "create_ifcv")

	if has_old and not has_new:
		rename_field("Item Excel Importer", "create_lcv", "create_ifcv")
		return

	if has_old and has_new:
		frappe.db.sql(
			"""
			UPDATE `tabItem Excel Importer`
			SET create_ifcv = IFNULL(NULLIF(create_ifcv, 0), create_lcv)
			"""
		)
		frappe.db.commit()
		frappe.db.sql_ddl("ALTER TABLE `tabItem Excel Importer` DROP COLUMN `create_lcv`")
