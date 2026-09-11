# Create Car Costings for all cars on Import File N.TAN039/26MSC
import frappe
from frappe.utils import flt

from vsd_jan_integration.vsd_jan_international_customization.doctype.car_costing.car_costing import (
	load_from_item,
)
from vsd_jan_integration.vsd_jan_international_customization.utils.costing_engine import (
	recalculate_car_costing,
)

IMPORT_FILE = "N.TAN039/26MSC"

# From 1 BL COST.xlsx for BL MEDUW3445865
EXCEL = {
	"ZRR70-0198971": {
		"m3": 14.733,
		"tra_duty": 9600000,
		"tpa": 141176,
		"icd": 191.529,
		"shipping_line": 1384.902,
	},
	"NSP140-9011378": {
		"m3": 11.396,
		"tra_duty": 8600000,
		"tpa": 141176,
		"icd": 148.148,
		"shipping_line": 1071.224,
	},
	"RT1-1006295": {
		"m3": 12.508,
		"tra_duty": 9423484.8,
		"tpa": 141176,
		"icd": 162.604,
		"shipping_line": 1175.752,
	},
	"GRS180-0026901": {
		"m3": 12.664,
		"tra_duty": 10000000,
		"tpa": 141176,
		"icd": 164.632,
		"shipping_line": 1190.416,
	},
	"ANH20-8050726": {
		"m3": 16.991,
		"tra_duty": 11600000,
		"tpa": 141176,
		"icd": 220.883,
		"shipping_line": 1597.154,
	},
	"ANH15-0044728": {
		"m3": 17.165,
		"tra_duty": 10700000,
		"tpa": 141176,
		"icd": 223.145,
		"shipping_line": 1613.51,
	},
	"TRN215-0021658": {
		"m3": 16.502,
		"tra_duty": 21500000,
		"tpa": 141176,
		"icd": 214.526,
		"shipping_line": 1551.188,
	},
}


def run():
	imp = frappe.get_doc("Import File", IMPORT_FILE)
	items = frappe.get_all(
		"Item",
		filters={"custom_bl": imp.bl_number, "disabled": 0},
		fields=["name", "custom_chassis_no"],
		order_by="name asc",
	)
	print(f"Import File={imp.name} BL={imp.bl_number} cars={len(items)}")

	created = []
	for it in items:
		chassis = it.custom_chassis_no
		data = EXCEL.get(chassis) or {}

		if data.get("m3"):
			frappe.db.set_value("Item", it.name, "custom_m3", data["m3"])

		for n in frappe.get_all(
			"Car Costing", filters={"item": it.name, "docstatus": 0}, pluck="name"
		):
			frappe.delete_doc("Car Costing", n, force=1)

		name = load_from_item(item=it.name, import_file=IMPORT_FILE)
		doc = frappe.get_doc("Car Costing", name)
		doc.import_file = IMPORT_FILE
		if data.get("m3"):
			doc.m3 = data["m3"]
		doc.yen_exchange_rate = 155
		if not flt(doc.exchange_rate):
			doc.exchange_rate = 2700

		for row in doc.tz_costing_lines:
			if row.costing_code == "tra_duty" and data.get("tra_duty") is not None:
				row.projected_amount = data["tra_duty"]
			elif row.costing_code == "tpa" and data.get("tpa") is not None:
				row.projected_amount = data["tpa"]

		for row in doc.japan_costing_lines:
			if row.costing_code == "icd" and data.get("icd") is not None:
				row.projected_amount = data["icd"]
			elif row.costing_code == "shipping_line" and data.get("shipping_line") is not None:
				row.projected_amount = data["shipping_line"]

		recalculate_car_costing(doc)
		doc.save()
		created.append(doc.name)
		print(
			f"OK {doc.name} | {chassis} | m3={doc.m3} | cost={flt(doc.cost, 2)} | import={doc.import_file}"
		)

	frappe.db.commit()
	print(f"DONE {len(created)} Car Costings for {IMPORT_FILE}")
	return created


if __name__ == "__main__":
	run()
