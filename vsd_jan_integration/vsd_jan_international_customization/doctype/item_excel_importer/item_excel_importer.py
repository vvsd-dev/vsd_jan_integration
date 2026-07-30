# Copyright (c) 2026, VV Systems Developer LTD and contributors
# For license information, please see license.txt

import datetime
import json
import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils.file_manager import get_file_path


class DateTimeEncoder(json.JSONEncoder):
	"""JSON encoder that converts datetime/date objects to ISO strings."""
	def default(self, obj):
		if isinstance(obj, (datetime.datetime, datetime.date)):
			return obj.isoformat()
		return super().default(obj)


class ItemExcelImporter(Document):
	pass


@frappe.whitelist()
def enqueue_import(docname, retry_failed_only=False):
	importer = frappe.get_doc("Item Excel Importer", docname)
	if not importer.excel_file:
		frappe.throw(_("Please attach an Excel file before importing."))

	importer.db_set("import_status", "Queued")
	importer.db_set("import_log", "Job queued in background...")

	frappe.enqueue(
		"vsd_jan_integration.vsd_jan_international_customization.doctype.item_excel_importer.item_excel_importer.run_import_job",
		docname=docname,
		retry_failed_only=retry_failed_only,
		queue="default",
		timeout=3600,
	)

	return {
		"status": "Queued",
		"message": _("Import job queued in background."),
	}


def run_import_job(docname, retry_failed_only=False):
	importer = frappe.get_doc("Item Excel Importer", docname)
	importer.db_set("import_status", "In Progress")

	try:
		file_path = get_file_path(importer.excel_file)
		selected_type = importer.get("import_type") or "Auto Detect"

		if selected_type == "Auto Detect":
			detected_format = detect_excel_format(file_path)
		else:
			detected_format = selected_type

		create_lcv = bool(importer.get("create_lcv"))

		if detected_format == "MKT Statement":
			res = process_mkt_statement(file_path, create_lcv=create_lcv, retry_failed_only=retry_failed_only, prev_failed_records=importer.get("failed_records"))
			summary = (
				f"Detected Format: MKT Statement (Create LCV: {'Yes' if create_lcv else 'No'})\n"
				f"Summary: Created {res['created_pi']} Purchase Invoices, Updated {res['updated_pi']} Purchase Invoices, "
				f"Created {res['created_lcv']} Landed Cost Vouchers, Updated {res['updated_items']} Items, "
				f"Skipped/Errors: {res['errors']}\n\n"
				+ "\n".join(res['log'])
			)
			status = "Completed" if res['errors'] == 0 else "Completed with Errors"
			failed_records_json = json.dumps(res['failed_records'], indent=2, cls=DateTimeEncoder)
		else:
			res = process_mukechi_import(file_path)
			summary = (
				f"Detected Format: Mukechi\n"
				f"Summary: Created {res['created']} Items, Updated {res['updated']} Items, Errors: {res['errors']}\n\n"
				+ "\n".join(res['log'])
			)
			status = "Completed" if res['errors'] == 0 else "Completed with Errors"
			failed_records_json = json.dumps(res.get('failed_records', []), indent=2, cls=DateTimeEncoder)

		importer.db_set("import_status", status)
		importer.db_set("import_log", summary)
		importer.db_set("failed_records", failed_records_json)

	except Exception as exc:
		importer.db_set("import_status", "Failed")
		importer.db_set("import_log", f"Import Failed: {str(exc)}\n{frappe.get_traceback()}")
		frappe.log_error(title="Item Excel Import Failed", message=frappe.get_traceback())



def detect_excel_format(file_path):
	try:
		import openpyxl
		wb = openpyxl.load_workbook(file_path, read_only=True, data_only=True)
		for sheet in wb.worksheets:
			for row in sheet.iter_rows(values_only=True):
				if not row:
					continue
				row_str = " ".join([str(c).upper() for c in row if c is not None])
				if "ANNEXURE TO MARKET STATMENT" in row_str or "FULL INVOICE VALUE" in row_str or "INVOICE CARS" in row_str:
					return "MKT Statement"
		return "Mukechi"
	except Exception:
		return "Mukechi"


# ==========================================
# MUKECHI FORMAT IMPORT
# ==========================================

def process_mukechi_import(file_path):
	rows = parse_excel_file(file_path)
	log_lines = []
	created_count = 0
	updated_count = 0
	error_count = 0
	failed_records = []

	for idx, row in enumerate(rows, start=2):
		try:
			result, item_code = process_row(row)
			if result == "created":
				created_count += 1
				log_lines.append(f"Row {idx}: Created Item {item_code}")
			elif result == "updated":
				updated_count += 1
				log_lines.append(f"Row {idx}: Updated Item {item_code}")
		except Exception as e:
			error_count += 1
			failed_records.append({"row": idx, "data": row, "error": str(e)})
			frappe.log_error(title=f"Item Import Error at Row {idx}", message=frappe.get_traceback())
			log_lines.append(f"Row {idx} Error: {str(e)}")

	return {
		"created": created_count,
		"updated": updated_count,
		"errors": error_count,
		"log": log_lines,
		"failed_records": failed_records,
	}


def parse_excel_file(file_path):
	try:
		import openpyxl
		wb = openpyxl.load_workbook(file_path, data_only=True)
		sheet = wb.active
		headers = None
		data = []

		for row in sheet.iter_rows(values_only=True):
			if not row or all(cell is None for cell in row):
				continue

			if headers is None:
				row_str_values = [str(c).strip().upper() if c is not None else "" for c in row]
				if any("CHASSIS" in s or "MAKER" in s for s in row_str_values):
					headers = [str(c).strip() if c is not None else f"col_{i}" for i, c in enumerate(row)]
				continue

			row_dict = {}
			for i, val in enumerate(row):
				if i < len(headers):
					row_dict[headers[i]] = val
			if any(v is not None for v in row_dict.values()):
				data.append(row_dict)

		return data
	except Exception as e:
		frappe.throw(_("Error reading Excel file with openpyxl: {0}").format(str(e)))


def process_row(row):
	def get_val(keys):
		if isinstance(keys, str):
			keys = [keys]
		for key in keys:
			for k, v in row.items():
				if k.strip().lower() == key.lower():
					return v
		return None

	maker = clean_str(get_val(["MAKER", "Maker"]))
	chassis_no = clean_str(get_val(["CHASSIS NO", "CHASSIS NO.", "Chassis No", "CHASSIS_NO"]))
	model_code = clean_str(get_val(["MODEL CODE", "Model Code", "MODEL_CODE"]))

	if not maker or not chassis_no:
		raise ValueError(f"Missing required fields Maker ('{maker}') or Chassis No ('{chassis_no}')")

	maker_group = ensure_item_group(maker, is_group=1)
	model_group_name = model_code if model_code else f"{maker} Models"
	final_item_group = ensure_item_group(model_group_name, parent_item_group=maker_group, is_group=0)

	item_code = f"{maker} - {chassis_no}"
	item_name = item_code

	purchase_date = format_date(get_val(["PURCHASE DATE", "Purchase Date"]))
	auction_no = clean_str(get_val(["AUCTION NO", "Auction No"]))
	auction_company = clean_str(get_val(["AUCTION COMPANY", "Auction Company"]))
	purchase_company = clean_str(get_val(["PURCHASE COMPANY", "Purchase Company"]))
	exhibition_no = clean_str(get_val(["EXHIBITION NO", "Exhibition No"]))
	mukechi = clean_str(get_val(["MUKECHI", "Mukechi"]))
	model = clean_str(get_val(["MODEL", "Model"]))
	color = clean_str(get_val(["COLOR", "Color"]))
	mileage = clean_str(get_val(["MILEAGE", "Mileage"]))
	price = parse_float(get_val(["PRICE", "Price"]))
	days_since_purchase = parse_int(get_val(["DAYS SINCE PURCHASE", "DAYS SINCE\nPURCHASE", "Days Since Purchase"]))
	loaded_docs_status = clean_str(get_val(["LOADED DOCS STATUS", "Loaded Docs Status"]))
	territory = clean_str(get_val(["TERRITORY", "Territory"]))
	bid_by = clean_str(get_val(["Bid By", "BID BY", "Bid by"]))
	remarks = clean_str(get_val(["Highest Bids Remarks", "HIGHEST BIDS REMARKS", "Remarks"]))

	if frappe.db.exists("Item", item_code):
		doc = frappe.get_doc("Item", item_code)
		action = "updated"
	else:
		doc = frappe.new_doc("Item")
		doc.item_code = item_code
		doc.stock_uom = "Nos"
		action = "created"

	doc.item_name = item_name
	doc.item_group = final_item_group

	doc.custom_purchase_date = purchase_date
	doc.custom_auction_no = auction_no
	doc.custom_auction_company = auction_company
	doc.custom_purchase_company = purchase_company
	doc.custom_exhibition_no = exhibition_no
	doc.custom_mukechi = mukechi
	doc.custom_chassis_no = chassis_no
	doc.custom_model_code = model_code
	doc.custom_maker = maker
	doc.custom_model = model
	doc.custom_color = color
	doc.custom_mileage = mileage
	doc.custom_price = price
	doc.custom_days_since_purchase = days_since_purchase
	doc.custom_loaded_docs_status = loaded_docs_status
	doc.custom_territory = territory
	doc.custom_bid_by = bid_by
	doc.custom_highest_bids_remarks = remarks

	doc.save(ignore_permissions=True)
	return action, item_code


# ==========================================
# MKT STATEMENT FORMAT IMPORT
# ==========================================

def process_mkt_statement(file_path, create_lcv=False, retry_failed_only=False, prev_failed_records=None):
	frappe.clear_cache(doctype="Purchase Invoice Item")
	frappe.clear_cache(doctype="Purchase Invoice")
	frappe.clear_cache(doctype="Item")
	invoice_info, container_rows, car_rows = parse_mkt_statement_excel(file_path)

	log_lines = []
	created_pi = 0
	updated_pi = 0
	created_lcv = 0
	updated_items = 0
	error_count = 0
	failed_records = []

	# Filter by failed records if retrying
	retry_chassis = set()
	if retry_failed_only and prev_failed_records:
		try:
			parsed_failed = json.loads(prev_failed_records) if isinstance(prev_failed_records, str) else prev_failed_records
			if isinstance(parsed_failed, list):
				for rec in parsed_failed:
					if isinstance(rec, dict) and rec.get("chassis_no"):
						retry_chassis.add(rec["chassis_no"])
		except Exception:
			pass

	if retry_chassis:
		car_rows = [c for c in car_rows if c.get("chassis_no") in retry_chassis]
		log_lines.append(f"Retrying import for {len(car_rows)} previously failed car records.")

	# Group cars and containers by invoice_no (normalized)
	invoice_cars_map = {}
	for car in car_rows:
		inv = normalize_inv_no(car["invoice_no"])
		if inv not in invoice_cars_map:
			invoice_cars_map[inv] = []
		invoice_cars_map[inv].append(car)

	invoice_containers_map = {}
	for cont in container_rows:
		inv = normalize_inv_no(cont.get("invoice_no"))
		if inv:
			if inv not in invoice_containers_map:
				invoice_containers_map[inv] = []
			invoice_containers_map[inv].append(cont)

	supplier_name = ensure_supplier("JAN JAPAN")

	# Process per Invoice No.
	for inv_no, cars in invoice_cars_map.items():
		info = invoice_info.get(inv_no, {}) or invoice_info.get(normalize_inv_no(inv_no), {})
		bl_sw = info.get("bl_sw") or next((c.get("bl_sw") for c in cars if c.get("bl_sw")), "")

		inv_date = info.get("invoice_date") or (cars[0]["invoice_date"] if cars else frappe.utils.today())
		if not inv_date:
			inv_date = frappe.utils.today()

		conts = invoice_containers_map.get(inv_no, [])

		# Assign container numbers per car (handles multi-container invoices)
		assign_containers_to_cars(cars, conts)

		# 1. Update ONLY existing Items by Chassis No (Do NOT create new Item if missing!)
		valid_car_items = []
		for car in cars:
			chassis_no = car["chassis_no"]
			car_price = car["car_price"]
			car_container_no = car.get("container_no", "")
			try:
				item_name = find_item_by_chassis(chassis_no)
				if item_name:
					item_doc = frappe.get_doc("Item", item_name)
					item_doc.custom_price = car_price
					item_doc.standard_rate = car_price
					if bl_sw:
						item_doc.custom_bl = bl_sw
						if hasattr(item_doc, "custom_bl_sw"):
							item_doc.custom_bl_sw = bl_sw
					if car_container_no:
						item_doc.custom_container_no = car_container_no
					item_doc.save(ignore_permissions=True)

					# Force persistence to db for Item custom fields
					item_updates = {"custom_price": car_price, "standard_rate": car_price}
					if bl_sw:
						item_updates["custom_bl"] = bl_sw
					if car_container_no:
						item_updates["custom_container_no"] = car_container_no
					frappe.db.set_value("Item", item_name, item_updates)

					updated_items += 1
					valid_car_items.append({
						"item_code": item_name,
						"chassis_no": chassis_no,
						"car_price": car_price,
						"container_no": car_container_no,
					})
					log_lines.append(f"Updated Item '{item_name}' (Chassis: {chassis_no}) - Price: {car_price}, Container: {car_container_no}, BL/SW: {bl_sw}")

				else:
					error_count += 1
					failed_records.append({"chassis_no": chassis_no, "invoice_no": inv_no, "error": f"Item for Chassis No '{chassis_no}' not found in database."})
					log_lines.append(f"Skipped Chassis No '{chassis_no}': Item not found in database (Items will NOT be auto-created).")
			except Exception as e:
				error_count += 1
				failed_records.append({"chassis_no": chassis_no, "invoice_no": inv_no, "error": str(e)})
				frappe.log_error(title=f"Error updating Item for Chassis {chassis_no}", message=frappe.get_traceback())
				log_lines.append(f"Error updating Item {chassis_no}: {str(e)}")

		if not valid_car_items:
			log_lines.append(f"No existing Items found for Invoice '{inv_no}'. Skipping Purchase Invoice creation.")
			continue

		# 2. Create / Update Purchase Invoice
		try:
			existing_pi = frappe.db.get_value("Purchase Invoice", {"bill_no": inv_no, "docstatus": ["!=", 2]}, "name")
			if existing_pi:
				pi_doc = frappe.get_doc("Purchase Invoice", existing_pi)
				is_new_pi = False
			else:
				pi_doc = frappe.new_doc("Purchase Invoice")
				pi_doc.supplier = supplier_name
				pi_doc.bill_no = inv_no
				is_new_pi = True

			if pi_doc.docstatus == 0:
				pi_doc.bill_date = format_date(inv_date) or frappe.utils.today()
				pi_doc.posting_date = pi_doc.bill_date
				pi_doc.update_stock = 1
			if hasattr(pi_doc, "custom_bl_sw"):
				pi_doc.custom_bl_sw = bl_sw


			# Items table contains ONLY the car items with container_no and blsw set on child table
			pi_doc.items = []
			for car in valid_car_items:
				item_row = pi_doc.append("items", {
					"item_code": car["item_code"],
					"qty": 1,
					"rate": car["car_price"],
				})
				item_row.custom_container_no = car.get("container_no", "")
				item_row.custom_blsw = bl_sw
				item_row.custom_bl = bl_sw
				if hasattr(item_row, "blsw"):
					item_row.blsw = bl_sw




			expense_fields = [
				("thc", "THC"),
				("forwarding", "Forwarding"),
				("freight", "Freight"),
				("inspection", "Inspection"),
				("jpn_expense", "JPN Expense"),
				("repair_cost", "Repair Cost"),
				("car_expense", "Car Expense"),
				("vanning", "Vanning"),
				("transportation", "Transportation"),
				("freight_and_other", "Freight & Other"),
				("cont_other_value", "Cont. Other Value"),
				("inv_other_charges", "Inv Other Charges"),
			]

			# Always add charges to Purchase Invoice taxes table
			pi_doc.taxes = []
			company_expense_account = get_company_expense_account(pi_doc.company)
			for fieldname, charge_label in expense_fields:
				total_charge = sum(c.get(fieldname, 0.0) for c in conts)
				if total_charge > 0:
					pi_doc.append("taxes", {
						"charge_type": "Actual",
						"account_head": company_expense_account,
						"description": charge_label,
						"tax_amount": total_charge,
						"category": "Valuation and Total",
					})


			# Build chassis_nos per container from the valid car items
			cont_chassis_map = {}
			for car_item in valid_car_items:
				c_no = car_item.get("container_no", "") or "Unassigned"
				cont_chassis_map.setdefault(c_no, []).append(car_item.get("chassis_no", ""))

			# Container Breakdown Child Table
			if hasattr(pi_doc, "custom_container_breakdown"):
				pi_doc.custom_container_breakdown = []
				for cont in conts:
					# Auto-calculate total: sum all expense fields + car_value if Excel total is 0
					cont_total = cont.get("total", 0)
					if not cont_total:
						cont_total = sum(cont.get(fn, 0) for fn in [
							"thc", "forwarding", "freight", "inspection", "jpn_expense",
							"repair_cost", "car_expense", "vanning", "transportation",
							"freight_and_other", "cont_other_value", "inv_other_charges", "car_value",
						])
					cont_key = cont.get("container_no", "")
					chassis_list = cont_chassis_map.get(cont_key, [])
					chassis_nos_str = ", ".join(c for c in chassis_list if c)
					pi_doc.append("custom_container_breakdown", {
						"container_no": cont_key,
						"chassis_nos": chassis_nos_str,
						"thc": cont.get("thc", 0),
						"forwarding": cont.get("forwarding", 0),
						"freight": cont.get("freight", 0),
						"inspection": cont.get("inspection", 0),
						"jpn_expense": cont.get("jpn_expense", 0),
						"repair_cost": cont.get("repair_cost", 0),
						"car_expense": cont.get("car_expense", 0),
						"vanning": cont.get("vanning", 0),
						"transportation": cont.get("transportation", 0),
						"freight_and_other": cont.get("freight_and_other", 0),
						"cars": cont.get("cars", 0),
						"car_value": cont.get("car_value", 0),
						"cont_other_value": cont.get("cont_other_value", 0),
						"inv_other_charges": cont.get("inv_other_charges", 0),
						"cont_price": cont.get("cont_price", 0),
						"total": cont_total,
					})

			if pi_doc.docstatus == 0:
				pi_doc.flags.ignore_mandatory = True
				pi_doc.save(ignore_permissions=True)


			if bl_sw:
				pi_doc.custom_bl_sw = bl_sw


			if is_new_pi:
				created_pi += 1
				log_lines.append(f"Created Purchase Invoice '{pi_doc.name}' for Supplier Invoice No: {inv_no} (BL/SW: {bl_sw})")
			else:
				updated_pi += 1
				log_lines.append(f"Updated Purchase Invoice '{pi_doc.name}' for Supplier Invoice No: {inv_no} (BL/SW: {bl_sw})")

			# 3. Submit PI and create Landed Cost Voucher if create_lcv is ticked
			if create_lcv:
				if pi_doc.docstatus == 0:
					pi_doc.submit()
					log_lines.append(f"Submitted Purchase Invoice '{pi_doc.name}'")
				total_charges = sum(sum(c.get(fn, 0.0) for fn in [f[0] for f in expense_fields]) for c in conts)
				if total_charges > 0:
					lcv = create_or_update_lcv(pi_doc, conts, expense_fields)
					if lcv:
						created_lcv += 1
						log_lines.append(f"Created/Updated Landed Cost Voucher '{lcv.name}' for Purchase Invoice '{pi_doc.name}'")
				else:
					log_lines.append(f"No charges found for LCV on Invoice '{pi_doc.name}' — LCV skipped.")



		except Exception as exc:
			error_count += 1
			frappe.log_error(title=f"Error processing Purchase Invoice for {inv_no}", message=frappe.get_traceback())
			log_lines.append(f"Error processing Purchase Invoice for {inv_no}: {str(exc)}")

	frappe.db.commit()
	frappe.clear_cache()

	return {
		"created_pi": created_pi,
		"updated_pi": updated_pi,
		"created_lcv": created_lcv,
		"updated_items": updated_items,
		"errors": error_count,
		"log": log_lines,
		"failed_records": failed_records,
	}



def create_or_update_lcv(pi_doc, conts, expense_fields):
	try:
		lcv_name = frappe.db.get_value(
			"Landed Cost Purchase Receipt",
			{"receipt_document": pi_doc.name, "docstatus": ["!=", 2]},
			"parent",
		)
		if lcv_name:
			lcv = frappe.get_doc("Landed Cost Voucher", lcv_name)
		else:
			lcv = frappe.new_doc("Landed Cost Voucher")
			lcv.company = pi_doc.company
			lcv.distribute_charges_based_on = "Amount"

		lcv.purchase_receipts = []
		lcv.append("purchase_receipts", {
			"receipt_document_type": "Purchase Invoice",
			"receipt_document": pi_doc.name,
			"grand_total": pi_doc.grand_total,
		})

		lcv.taxes = []
		company_expense_account = get_company_expense_account(pi_doc.company)
		for fieldname, charge_label in expense_fields:
			amt = sum(c.get(fieldname, 0.0) for c in conts)
			if amt > 0:
				lcv.append("taxes", {
					"expense_account": company_expense_account,
					"description": charge_label,
					"amount": amt,
				})

		# Populate items directly from Purchase Invoice
		cost_center = get_company_cost_center(pi_doc.company)
		lcv.items = []
		for item in pi_doc.items:
			lcv.append("items", {
				"receipt_document_type": "Purchase Invoice",
				"receipt_document": pi_doc.name,
				"item_code": item.item_code,
				"description": item.description or item.item_name or item.item_code,
				"qty": frappe.utils.flt(item.qty),
				"rate": frappe.utils.flt(item.rate),
				"amount": frappe.utils.flt(item.amount) or (frappe.utils.flt(item.qty) * frappe.utils.flt(item.rate)),
				"cost_center": item.cost_center or cost_center,

			})

		lcv.flags.ignore_mandatory = True
		lcv.save(ignore_permissions=True)
		return lcv
	except Exception as e:
		print("LCV CREATION EXCEPTION:", e, frappe.get_traceback())
		frappe.log_error(title=f"Error creating Landed Cost Voucher for {pi_doc.name}", message=frappe.get_traceback())
		return None


def get_company_cost_center(company):
	if not company:
		company = frappe.defaults.get_user_default("Company") or frappe.db.get_single_value("Global Defaults", "default_company")
	cc = frappe.db.get_value("Company", company, "cost_center")
	if not cc:
		cc = frappe.db.get_value("Cost Center", {"company": company, "is_group": 0}, "name")
	return cc





def get_company_expense_account(company):
	if not company:
		company = frappe.defaults.get_user_default("Company") or frappe.db.get_single_value("Global Defaults", "default_company")
	
	account = frappe.db.get_value("Company", company, "default_expense_account")
	if not account:
		account = frappe.db.get_value("Account", {"company": company, "account_type": "Expenses Included in Valuation", "is_group": 0}, "name")
	if not account:
		account = frappe.db.get_value("Account", {"company": company, "root_type": "Expense", "is_group": 0}, "name")
	return account


BL_SEARCH_KEYS = ["BL/SW", "BL / SW", "BL_SW", "BL", "B/L", "B/L NO", "B/L NO.", "BL NO", "BL NO.", "BILL OF LADING"]


def parse_mkt_statement_excel(file_path):

	import openpyxl
	wb = openpyxl.load_workbook(file_path, data_only=True)

	invoice_info = {}
	container_rows = []
	car_rows = []

	for sheet in wb.worksheets:
		current_section = None
		current_headers = None
		current_invoice_no = None

		for row in sheet.iter_rows(values_only=True):
			if not row or all(c is None for c in row):
				continue

			row_str_cells = [clean_str(c) for c in row]
			line_text = " ".join(row_str_cells).upper()

			# Section headers
			if "INVOICE CARS" in line_text and "NOT INVOICED" not in line_text and "RORO" not in line_text and "CONTAINER" not in line_text:
				current_section = "INVOICE_CARS"
				current_headers = None
				continue
			elif "FULL INVOICE VALUE" in line_text and "RORO" not in line_text:
				current_section = "FULL_INVOICE_VALUE"
				current_headers = None
				continue
			elif "ANNEXURE TO MARKET" in line_text or any(kw in line_text for kw in [
				"CONTAINER PRICE", "RORO CARS", "RORO CHARGES", "CONTAINERS OTHER",
				"NOT INVOICED", "STOCK IN JAPAN", "TT RECEIPT ON THE WAY",
				"RORO FULL INVOICE VALUE", "ON THE WAY ADJUSTMENTS"
			]):
				current_section = "OTHER"
				current_headers = None
				continue

			# Table 1: Full Invoice Value
			if current_section == "FULL_INVOICE_VALUE":
				if current_headers is None:
					if any("CONTAINER" in s.upper() for s in row_str_cells):
						current_headers = [clean_str(c) for c in row]
					continue
				else:
					row_dict = dict(zip(current_headers, row_str_cells))
					cont_no = get_cell_by_headers(row_dict, ["CONTAINER NO", "CONTAINER NO.", "CONTAINER_NO", "CONTAINER"])
					inv_no = get_cell_by_headers(row_dict, ["INVOICE NO", "INVOICE NO.", "INVOICE_NO", "INVOICE"])
					if inv_no:
						current_invoice_no = inv_no

					# Always try to extract BL/SW from any row that has invoice info (not just container rows)
					bl_sw_val = get_cell_by_headers(row_dict, BL_SEARCH_KEYS)
					target_inv_blsw = normalize_inv_no(inv_no or current_invoice_no)
					if target_inv_blsw and bl_sw_val:
						if target_inv_blsw not in invoice_info:
							invoice_info[target_inv_blsw] = {}
						invoice_info[target_inv_blsw]["bl_sw"] = invoice_info[target_inv_blsw].get("bl_sw") or bl_sw_val

					if cont_no and cont_no.lower() not in ("total", "sr#", "inv text", "container no."):
						inv_other_charges_val = parse_float(get_cell_by_headers(row_dict, ["INV OTHER CHARGES", "INV. OTHER CHARGES", "OTHER CHARGES", "INV OTHER VALUE"]))

						if cont_no.lower() in ("inv other charges", "inv. other charges", "other charges"):
							# Extract all expense fields - the amount can be in any standard expense column
							container_rows.append({
								"container_no": cont_no,
								"thc": parse_float(get_cell_by_headers(row_dict, ["THC"])),
								"forwarding": parse_float(get_cell_by_headers(row_dict, ["FORWARDING", "FORW. CHARGES"])),
								"freight": parse_float(get_cell_by_headers(row_dict, ["FREIGHT", "OCEAN FREIGHT"])),
								"inspection": parse_float(get_cell_by_headers(row_dict, ["INSPECTION", "INSP. CHARGES"])),
								"jpn_expense": parse_float(get_cell_by_headers(row_dict, ["JPN EXPENSE", "JAPAN EXPENSE"])),
								"repair_cost": parse_float(get_cell_by_headers(row_dict, ["REPAIR COST"])),
								"car_expense": parse_float(get_cell_by_headers(row_dict, ["CAR EXPENSE"])),
								"vanning": parse_float(get_cell_by_headers(row_dict, ["VANNING"])),
								"transportation": parse_float(get_cell_by_headers(row_dict, ["TRANSPORTATION"])),
								"freight_and_other": parse_float(get_cell_by_headers(row_dict, ["FREIGHT & OTHER", "FREIGHT AND OTHER"])),
								"cont_other_value": parse_float(get_cell_by_headers(row_dict, ["CONT. OTHER VALUE", "CONT OTHER VALUE"])),
								"inv_other_charges": inv_other_charges_val or parse_float(get_cell_by_headers(row_dict, ["TOTAL", "CONT PRICE", "CAR VALUE", "AMOUNT"])),
								"cars": 0,
								"invoice_no": inv_no or current_invoice_no,
							})
						else:
							container_rows.append({
								"container_no": cont_no,
								"thc": parse_float(get_cell_by_headers(row_dict, ["THC"])),
								"forwarding": parse_float(get_cell_by_headers(row_dict, ["FORWARDING", "FORW. CHARGES"])),
								"freight": parse_float(get_cell_by_headers(row_dict, ["FREIGHT", "OCEAN FREIGHT"])),
								"inspection": parse_float(get_cell_by_headers(row_dict, ["INSPECTION", "INSP. CHARGES"])),
								"jpn_expense": parse_float(get_cell_by_headers(row_dict, ["JPN EXPENSE", "JAPAN EXPENSE"])),
								"repair_cost": parse_float(get_cell_by_headers(row_dict, ["REPAIR COST"])),
								"car_expense": parse_float(get_cell_by_headers(row_dict, ["CAR EXPENSE"])),
								"vanning": parse_float(get_cell_by_headers(row_dict, ["VANNING"])),
								"transportation": parse_float(get_cell_by_headers(row_dict, ["TRANSPORTATION"])),
								"freight_and_other": parse_float(get_cell_by_headers(row_dict, ["FREIGHT & OTHER", "FREIGHT AND OTHER"])),
								"inv_other_charges": inv_other_charges_val,
								"cars": parse_int(get_cell_by_headers(row_dict, ["CARS"])),
								"car_value": parse_float(get_cell_by_headers(row_dict, ["CAR VALUE"])),
								"cont_other_value": parse_float(get_cell_by_headers(row_dict, ["CONT. OTHER VALUE", "CONT OTHER VALUE"])),
								"cont_price": parse_float(get_cell_by_headers(row_dict, ["CONT. PRICE", "CONT PRICE"])),
								"total": parse_float(get_cell_by_headers(row_dict, ["TOTAL"])),
								"invoice_no": inv_no or current_invoice_no,
							})
					continue

			# Table 2: Invoice Cars
			if current_section == "INVOICE_CARS":
				if current_headers is None:
					if any("CHASSIS" in s.upper() for s in row_str_cells) and any("INVOICE" in s.upper() for s in row_str_cells):
						current_headers = [clean_str(c) for c in row]
					continue
				else:
					row_dict = dict(zip(current_headers, row_str_cells))
					chassis_no = get_cell_by_headers(row_dict, ["CHASSIS NO", "CHASSIS NO.", "CHASSIS_NO", "CHASSIS"])
					inv_no = get_cell_by_headers(row_dict, ["INVOICE NO", "INVOICE NO.", "INVOICE_NO", "INVOICE"])

					# Always try to capture BL/SW from any row with invoice info
					bl_sw_val = get_cell_by_headers(row_dict, BL_SEARCH_KEYS)
					if inv_no and bl_sw_val:
						target_inv_blsw = normalize_inv_no(inv_no)
						if target_inv_blsw not in invoice_info:
							invoice_info[target_inv_blsw] = {}
						invoice_info[target_inv_blsw]["bl_sw"] = invoice_info[target_inv_blsw].get("bl_sw") or bl_sw_val

					if chassis_no and inv_no and chassis_no.lower() not in ("chassis no.", "chassis no"):
						car_rows.append({
							"stock_id": clean_str(get_cell_by_headers(row_dict, ["STOCK ID", "STOCK_ID"])),
							"chassis_no": chassis_no,
							"car_price": parse_float(get_cell_by_headers(row_dict, ["CAR PRICE", "PRICE"])),
							"invoice_no": inv_no,
							"invoice_date": format_date(get_cell_by_headers(row_dict, ["INVOICE DATE", "INVOICE_DATE", "DATE"])),
							"bl_sw": bl_sw_val,
						})
					continue


			# Table 0 / Header Mapping (Invoice No -> BL/SW & Date)
			if current_section in (None, "HEADER_MAPPING") and any(k in s.upper() for s in row_str_cells for k in ["BL/SW", "BL", "B/L", "BILL OF LADING"]) and any("INVOICE" in s.upper() for s in row_str_cells):
				current_headers = [clean_str(c) for c in row]
				current_section = "HEADER_MAPPING"
				continue
			elif current_section == "HEADER_MAPPING":
				if current_headers:
					row_dict = dict(zip(current_headers, row_str_cells))
					inv_no = get_cell_by_headers(row_dict, ["INVOICE NO", "INVOICE NO.", "INVOICE_NO", "INVOICE"])
					bl_sw = get_cell_by_headers(row_dict, BL_SEARCH_KEYS)
					inv_date = format_date(get_cell_by_headers(row_dict, ["INVOICE DATE", "INVOICE_DATE", "DATE"]))
					if inv_no and inv_no.lower() not in ("invoice no.", "invoice no"):
						norm_inv = normalize_inv_no(inv_no)
						if norm_inv not in invoice_info:
							invoice_info[norm_inv] = {}
						invoice_info[norm_inv]["invoice_date"] = inv_date
						invoice_info[norm_inv]["bl_sw"] = bl_sw

	return invoice_info, container_rows, car_rows


def assign_containers_to_cars(cars_list, containers_list):
	cont_idx = 0
	cont_rem = containers_list[0].get("cars", 0) if containers_list else 0

	for car in cars_list:
		if car.get("container_no"):
			continue

		if containers_list and cont_idx < len(containers_list):
			car["container_no"] = containers_list[cont_idx].get("container_no", "")
			cont_rem -= 1
			if cont_rem <= 0:
				cont_idx += 1
				if cont_idx < len(containers_list):
					cont_rem = containers_list[cont_idx].get("cars", 0)
		else:
			car["container_no"] = ""


def normalize_inv_no(inv_no):
	if not inv_no:
		return ""
	# Normalize: strip whitespace, collapse internal spaces
	return " ".join(str(inv_no).strip().split())



def get_cell_by_headers(row_dict, search_keys):
	for key, val in row_dict.items():
		key_clean = str(key).strip().upper().replace("/", "").replace(".", "").replace("_", "").replace(" ", "")
		for sk in search_keys:
			sk_clean = sk.strip().upper().replace("/", "").replace(".", "").replace("_", "").replace(" ", "")
			if key_clean == sk_clean:
				return val
	return None


def find_item_by_chassis(chassis_no):
	if not chassis_no:
		return None
	chassis_no = str(chassis_no).strip()

	# 1. Custom Chassis No
	name = frappe.db.get_value("Item", {"custom_chassis_no": chassis_no}, "name")
	if name:
		return name

	# 2. Exact item_code
	if frappe.db.exists("Item", chassis_no):
		return chassis_no

	# 3. Item Name contains chassis_no
	name = frappe.db.get_value("Item", [["Item", "item_name", "like", f"%{chassis_no}%"]], "name")
	if name:
		return name

	return None


def ensure_supplier(supplier_name="JAN JAPAN"):
	if frappe.db.exists("Supplier", supplier_name):
		return supplier_name
	doc = frappe.new_doc("Supplier")
	doc.supplier_name = supplier_name
	doc.supplier_group = "All Supplier Groups"
	doc.insert(ignore_permissions=True)
	return doc.name


# ==========================================
# COMMON UTILITY FUNCTIONS
# ==========================================

def ensure_item_group(group_name, parent_item_group=None, is_group=0):
	if not group_name:
		group_name = "All Item Groups"
		
	if frappe.db.exists("Item Group", group_name):
		return group_name

	if not parent_item_group:
		parent_item_group = "All Item Groups"
	elif not frappe.db.exists("Item Group", parent_item_group):
		ensure_item_group(parent_item_group, parent_item_group="All Item Groups", is_group=1)

	doc = frappe.new_doc("Item Group")
	doc.item_group_name = group_name
	doc.parent_item_group = parent_item_group
	doc.is_group = is_group
	doc.insert(ignore_permissions=True)
	return doc.name


def clean_str(val):
	if val is None:
		return ""
	val_str = str(val).strip()
	return "" if val_str.lower() in ("none", "nan", "null") else val_str


def parse_float(val):
	if val is None:
		return 0.0
	try:
		s = str(val).replace(",", "").strip()
		return float(s)
	except ValueError:
		return 0.0


def parse_int(val):
	if val is None:
		return 0
	try:
		s = str(val).replace(",", "").strip()
		return int(float(s))
	except ValueError:
		return 0


def format_date(val):
	if not val:
		return None
	if isinstance(val, (datetime.date, datetime.datetime)):
		return val.strftime("%Y-%m-%d")
	val_str = str(val).strip()
	for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%m/%d/%Y"):
		try:
			dt = datetime.datetime.strptime(val_str, fmt)
			return dt.strftime("%Y-%m-%d")
		except ValueError:
			continue
	return None
