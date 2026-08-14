# Copyright (c) 2026, VV Systems Developer LTD and contributors
# For license information, please see license.txt

import datetime
import json
import time
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
	def before_insert(self):
		self.auto_detect_format()

	def validate(self):
		if self.excel_file and (not self.import_type or self.import_type == "Auto Detect" or self.is_new()):
			self.auto_detect_format()

	def auto_detect_format(self):
		if self.excel_file:
			try:
				file_path = get_file_path(self.excel_file)
				detected = detect_excel_format(file_path)
				self.import_type = detected
			except Exception:
				self.import_type = "Unknown Format"


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
			importer.db_set("import_type", detected_format)
		else:
			detected_format = selected_type

		create_lcv = bool(importer.get("create_lcv"))
		auto_submit_pi = bool(importer.get("auto_submit_purchase_invoice"))
		auto_submit_jv = bool(importer.get("auto_submit_journal_entry"))

		if detected_format == "Unknown Format":
			summary = "Import Failed: Excel file format is unrecognized (Unknown Format)."
			importer.db_set("import_status", "Failed")
			importer.db_set("import_log", summary)
			return

		if detected_format == "MKT Statement":
			res = process_mkt_statement(
				file_path,
				create_lcv=create_lcv,
				auto_submit_pi=auto_submit_pi,
				auto_submit_jv=auto_submit_jv,
				retry_failed_only=retry_failed_only,
				prev_failed_records=importer.get("failed_records"),
				docname=docname,
			)
			summary = res["summary"]
			status = "Completed" if res["errors"] == 0 else "Completed with Errors"
			failed_records_json = json.dumps(res["failed_records"], indent=2, cls=DateTimeEncoder)
		else:
			res = process_mukechi_import(file_path, docname=docname)
			summary = (
				f"Detected Format: Mukechi\n"
				f"Summary: Created {res['created']} Items, Updated {res['updated']} Items, Errors: {res['errors']}\n\n"
				+ "\n".join(res["log"])
			)
			status = "Completed" if res["errors"] == 0 else "Completed with Errors"
			failed_records_json = json.dumps(res.get("failed_records", []), indent=2, cls=DateTimeEncoder)

		tot_inv = res.get("total_invoices") or res.get("created_pi", 0) + res.get("updated_pi", 0) or importer.get("total_invoices") or 0
		tot_cars = res.get("total_cars") or res.get("updated_items", 0) or importer.get("total_cars") or 0

		importer.db_set("import_status", status)
		importer.db_set("import_log", summary)
		importer.db_set("failed_records", failed_records_json)
		importer.db_set("processed_invoices", tot_inv)
		importer.db_set("processed_cars", tot_cars)
		if tot_inv > 0 and not importer.get("total_invoices"):
			importer.db_set("total_invoices", tot_inv)
		if tot_cars > 0 and not importer.get("total_cars"):
			importer.db_set("total_cars", tot_cars)

		time_elapsed_str = res.get("time_elapsed_str", "")
		importer.db_set("import_status", status)
		importer.db_set("import_log", summary)
		importer.db_set("failed_records", failed_records_json)
		importer.db_set("processed_invoices", tot_inv)
		importer.db_set("processed_cars", tot_cars)
		if time_elapsed_str:
			importer.db_set("estimated_time", time_elapsed_str)
		if tot_inv > 0 and not importer.get("total_invoices"):
			importer.db_set("total_invoices", tot_inv)
		if tot_cars > 0 and not importer.get("total_cars"):
			importer.db_set("total_cars", tot_cars)

		publish_import_progress(
			docname,
			processed_invoices=tot_inv,
			total_invoices=importer.get("total_invoices") or tot_inv,
			processed_cars=tot_cars,
			total_cars=importer.get("total_cars") or tot_cars,
			active_step_text=f"Import finished with status: {status}",
			time_elapsed_str=time_elapsed_str,
			status=status,
			estimated_time=time_elapsed_str,
			update_db=True,
		)

	except Exception as exc:
		importer.db_set("import_status", "Failed")
		importer.db_set("import_log", f"Import Failed: {str(exc)}\n{frappe.get_traceback()}")
		frappe.log_error(title="Item Excel Import Failed", message=frappe.get_traceback())
		publish_import_progress(
			docname,
			processed_invoices=0,
			total_invoices=0,
			processed_cars=0,
			total_cars=0,
			active_step_text=f"Import Failed: {str(exc)}",
			status="Failed",
			update_db=True,
		)


def publish_import_progress(docname, processed_invoices=0, total_invoices=0, processed_cars=0, total_cars=0, active_step_text="", time_elapsed_str="", status="In Progress", estimated_time=None, update_db=True):
	percent = 0
	tot = (total_invoices or 0) + (total_cars or 0)
	if tot > 0:
		percent = min(100, int(((processed_invoices or 0) + (processed_cars or 0)) / tot * 100))

	if docname and update_db:
		try:
			db_updates = {}
			if processed_invoices is not None:
				db_updates["processed_invoices"] = processed_invoices
			if total_invoices is not None and total_invoices > 0:
				db_updates["total_invoices"] = total_invoices
			if processed_cars is not None:
				db_updates["processed_cars"] = processed_cars
			if total_cars is not None and total_cars > 0:
				db_updates["total_cars"] = total_cars

			if status in ["Completed", "Completed with Errors", "Failed"] and time_elapsed_str:
				db_updates["estimated_time"] = time_elapsed_str
			elif estimated_time:
				db_updates["estimated_time"] = estimated_time
			elif total_invoices or total_cars:
				est = round((total_invoices or 0) * 0.18 + (total_cars or 0) * 0.003, 1)
				if est > 0:
					db_updates["estimated_time"] = f"{est}s"

			if db_updates:
				frappe.db.set_value("Item Excel Importer", docname, db_updates, update_modified=False)
		except Exception:
			pass


	message = {
		"docname": docname,
		"percent": percent,
		"processed_invoices": processed_invoices or 0,
		"total_invoices": total_invoices or 0,
		"processed_cars": processed_cars or 0,
		"total_cars": total_cars or 0,
		"active_step_text": active_step_text,
		"time_elapsed_str": time_elapsed_str,
		"status": status,
	}

	try:
		frappe.publish_realtime(
			event=f"item_excel_import_progress_{docname}",
			message=message,
			user=frappe.session.user if hasattr(frappe, "session") else None,
		)
	except Exception:
		pass



def detect_excel_format(file_path):
	try:
		import openpyxl
		wb = openpyxl.load_workbook(file_path, read_only=True, data_only=True)
		has_mukechi_kw = False
		for sheet in wb.worksheets:
			for row in sheet.iter_rows(values_only=True):
				if not row:
					continue
				row_str = " ".join([str(c).upper() for c in row if c is not None])
				if any(kw in row_str for kw in [
					"ANNEXURE TO MARKET STATMENT", "FULL INVOICE VALUE", "INVOICE CARS",
					"RORO FULL INVOICE VALUE", "RORO CARS"
				]):
					return "MKT Statement"
				if any(kw in row_str for kw in ["MAKER", "CHASSIS", "MODEL CODE", "MUKECHI"]):
					has_mukechi_kw = True

		return "Mukechi" if has_mukechi_kw else "Unknown Format"
	except Exception:
		return "Unknown Format"



# ==========================================
# MUKECHI FORMAT IMPORT
# ==========================================

def process_mukechi_import(file_path, docname=None):
	rows = parse_excel_file(file_path)
	log_lines = []
	created_count = 0
	updated_count = 0
	error_count = 0
	failed_records = []
	color_cache = {}
	start_time = time.time()

	total_rows = len(rows)
	for idx, row in enumerate(rows, start=2):
		try:
			result, item_code = process_row(row, color_cache=color_cache)
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

		if docname and idx % 10 == 0:
			elapsed = round(time.time() - start_time, 2)
			publish_import_progress(
				docname,
				processed_cars=idx,
				total_cars=total_rows,
				active_step_text=f"Processing Mukechi Row {idx} of {total_rows}...",
				time_elapsed_str=f"{elapsed}s",
			)

	time_elapsed = round(time.time() - start_time, 2)
	return {
		"created": created_count,
		"updated": updated_count,
		"errors": error_count,
		"log": log_lines,
		"failed_records": failed_records,
		"time_elapsed_str": f"{time_elapsed}s",
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


def process_row(row, color_cache=None):
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
	raw_color = clean_str(get_val(["COLOR", "Color", "COLOUR", "Colour"]))
	color = ensure_item_color(raw_color, cache=color_cache) if raw_color else None
	mileage = clean_str(get_val(["MILEAGE", "Mileage"]))
	price = parse_float(get_val(["PRICE", "Price"]))
	days_since_purchase = parse_int(get_val(["DAYS SINCE PURCHASE", "DAYS SINCE\nPURCHASE", "Days Since Purchase"]))
	loaded_docs_status = clean_str(get_val(["LOADED DOCS STATUS", "Loaded Docs Status"]))
	territory = clean_str(get_val(["TERRITORY", "Territory"]))
	bid_by = clean_str(get_val(["Bid By", "BID BY", "Bid by"]))
	remarks = clean_str(get_val(["Highest Bids Remarks", "HIGHEST BIDS REMARKS", "Remarks"]))

	item_fields = {
		"item_name": item_name,
		"item_group": final_item_group,
		"custom_purchase_date": purchase_date,
		"custom_auction_no": auction_no,
		"custom_auction_company": auction_company,
		"custom_purchase_company": purchase_company,
		"custom_exhibition_no": exhibition_no,
		"custom_mukechi": mukechi,
		"custom_chassis_no": chassis_no,
		"custom_model_code": model_code,
		"custom_maker": maker,
		"custom_model": model,
		"custom_color": color,
		"custom_mileage": mileage,
		"custom_price": price,
		"custom_days_since_purchase": days_since_purchase,
		"custom_loaded_docs_status": loaded_docs_status,
		"custom_territory": territory,
		"custom_bid_by": bid_by,
		"custom_highest_bids_remarks": remarks,
	}

	if frappe.db.exists("Item", item_code):
		frappe.db.set_value("Item", item_code, item_fields)
		action = "updated"
	else:
		doc = frappe.new_doc("Item")
		doc.item_code = item_code
		doc.stock_uom = "Nos"
		doc.update(item_fields)
		doc.insert(ignore_permissions=True)
		action = "created"

	return action, item_code


# ==========================================
# MKT STATEMENT FORMAT IMPORT (Containers & RORO)
# ==========================================

EXPENSE_FIELDS = [
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


def process_mkt_statement(file_path, create_lcv=False, auto_submit_pi=False, auto_submit_jv=False, retry_failed_only=False, prev_failed_records=None, docname=None):
	start_time = time.time()

	frappe.clear_cache(doctype="Purchase Invoice Item")
	frappe.clear_cache(doctype="Purchase Invoice")
	frappe.clear_cache(doctype="Journal Entry")
	frappe.clear_cache(doctype="Item")

	invoice_info, container_rows, car_rows = parse_mkt_statement_excel(file_path)

	total_container_full = len([c for c in container_rows if not c.get("is_roro")])
	total_container_cars = len([c for c in car_rows if not c.get("is_roro")])
	total_roro_full = len([c for c in container_rows if c.get("is_roro")])
	total_roro_cars = len([c for c in car_rows if c.get("is_roro")])

	# Pre-build invoice_containers_map and pre-assign containers to ALL cars before any retry filtering
	invoice_containers_map = {}
	for cont in container_rows:
		inv = normalize_inv_no(cont.get("invoice_no"))
		if inv:
			if inv not in invoice_containers_map:
				invoice_containers_map[inv] = []
			invoice_containers_map[inv].append(cont)

	full_invoice_cars_map = {}
	for car in car_rows:
		inv = normalize_inv_no(car["invoice_no"])
		if inv not in full_invoice_cars_map:
			full_invoice_cars_map[inv] = []
		full_invoice_cars_map[inv].append(car)

	for inv, cars in full_invoice_cars_map.items():
		conts = invoice_containers_map.get(inv, [])
		if not conts:
			is_roro_inv = any(c.get("is_roro") for c in cars)
			default_cont_name = "RORO" if is_roro_inv else "Unassigned"
			default_cont = {
				"container_no": default_cont_name,
				"cars": len(cars),
				"invoice_no": inv,
				"is_roro": is_roro_inv,
				"total": 0.0,
			}
			invoice_containers_map[inv] = [default_cont]
			conts = invoice_containers_map[inv]

		assign_containers_to_cars(cars, conts)


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

	invoice_cars_map = {}
	for car in car_rows:
		inv = normalize_inv_no(car["invoice_no"])
		if inv not in invoice_cars_map:
			invoice_cars_map[inv] = []
		invoice_cars_map[inv].append(car)

	total_invoices = len(invoice_cars_map)
	total_cars = len(car_rows)

	if docname:
		try:
			importer = frappe.get_doc("Item Excel Importer", docname)
			importer.db_set("total_invoices", total_invoices)
			importer.db_set("processed_invoices", 0)
			importer.db_set("total_cars", total_cars)
			importer.db_set("processed_cars", 0)
			est_secs = round(total_invoices * 0.18 + total_cars * 0.003, 1)
			importer.db_set("estimated_time", f"{est_secs}s")

		except Exception:
			pass

	inv_res = run_invoice_and_journal_job(
		docname=docname,
		invoice_cars_map=invoice_cars_map,
		invoice_containers_map=invoice_containers_map,
		invoice_info=invoice_info,
		create_lcv=create_lcv,
		auto_submit_pi=auto_submit_pi,
		auto_submit_jv=auto_submit_jv,
		total_invoices=total_invoices,
		start_time=start_time,
	)

	car_res = run_car_updating_job(
		docname=docname,
		car_rows=car_rows,
		invoice_info=invoice_info,
		invoice_containers_map=invoice_containers_map,
		total_cars=total_cars,
		start_time=start_time,
	)




	time_elapsed = round(time.time() - start_time, 2)
	time_elapsed_str = f"{time_elapsed}s"

	created_pi = inv_res["created_pi"]
	updated_pi = inv_res["updated_pi"]
	created_jv = inv_res["created_jv"]
	updated_jv = inv_res["updated_jv"]
	created_lcv = inv_res["created_lcv"]
	error_count = inv_res["errors"] + car_res["errors"]

	total_container_full = inv_res.get("container_full_count", 0)
	total_container_cars = inv_res.get("container_car_count", 0)
	total_roro_full = inv_res.get("roro_full_count", 0)
	total_roro_cars = inv_res.get("roro_car_count", 0)

	all_logs = []
	if inv_res["created_pi_logs"]:
		all_logs.append("--- Purchase Invoices & Journal Entries Created / Updated ---")
		all_logs.extend(inv_res["created_pi_logs"])
		all_logs.append("")

	if inv_res["not_created_pi_logs"]:
		all_logs.append("--- Purchase Invoices Not Created ---")
		all_logs.extend(inv_res["not_created_pi_logs"])
		all_logs.append("")

	if car_res["logs"]:
		all_logs.append("--- Car Items Updated ---")
		all_logs.extend(car_res["logs"])
		all_logs.append("")

	summary = (
		f"Detected Format: MKT Statement (Create LCV: {'Yes' if create_lcv else 'No'})\n"
		f"Breakdown Summary:\n"
		f"  - Container Full Invoices: {total_container_full} | Container Cars: {total_container_cars}\n"
		f"  - RORO Full Invoices: {total_roro_full} | RORO Cars: {total_roro_cars}\n"
		f"  - Purchase Invoices Created: {created_pi} | Updated: {updated_pi}\n"
		f"  - Journal Entries Created: {created_jv} | Updated: {updated_jv}\n"
		f"  - Landed Cost Vouchers: {created_lcv}\n"
		f"  - Time Elapsed: {time_elapsed_str}\n"
		f"  - Errors / Skipped: {error_count}\n\n"
		+ "\n".join(all_logs)
	)

	return {
		"created_pi": created_pi,
		"updated_pi": updated_pi,
		"created_jv": created_jv,
		"updated_jv": updated_jv,
		"created_lcv": created_lcv,
		"updated_items": car_res["updated_items"],
		"errors": error_count,
		"summary": summary,
		"log": all_logs,
		"failed_records": inv_res["failed_records"] + car_res["failed_records"],
		"time_elapsed_str": time_elapsed_str,
	}



# ==========================================
# SCHEDULER / WORKER 1: INVOICES & JOURNAL ENTRIES
# ==========================================

def run_invoice_and_journal_job(docname, invoice_cars_map, invoice_containers_map, invoice_info, create_lcv, auto_submit_pi, auto_submit_jv, total_invoices, start_time):
	supplier_name = ensure_supplier("JAN JAPAN")
	created_pi_logs = []
	not_created_pi_logs = []
	created_pi = 0
	updated_pi = 0
	created_jv = 0
	updated_jv = 0
	created_lcv = 0
	error_count = 0
	failed_records = []
	chassis_cache = {}

	# Bulk pre-fetch item chassis mappings in 1 query
	try:
		item_list = frappe.db.get_all("Item", fields=["name", "custom_chassis_no", "item_name"])
		for it in item_list:
			if it.custom_chassis_no:
				chassis_cache[str(it.custom_chassis_no).strip()] = it.name
			chassis_cache[str(it.name).strip()] = it.name
			if it.item_name:
				chassis_cache[str(it.item_name).strip()] = it.name
	except Exception:
		pass

	# Bulk pre-fetch existing Purchase Invoices by bill_no
	existing_pi_map = {}
	try:
		pi_records = frappe.db.get_all("Purchase Invoice", filters={"docstatus": ["!=", 2]}, fields=["bill_no", "name"])
		for r in pi_records:
			if r.bill_no:
				existing_pi_map[str(r.bill_no).strip()] = r.name
	except Exception:
		pass

	# Bulk pre-fetch existing Journal Entries by cheque_no
	existing_jv_map = {}
	try:
		jv_records = frappe.db.get_all("Journal Entry", filters={"docstatus": ["!=", 2]}, fields=["cheque_no", "name"])
		for r in jv_records:
			if r.cheque_no:
				existing_jv_map[str(r.cheque_no).strip()] = r.name
	except Exception:
		pass

	processed_count = 0

	for inv_no, cars in invoice_cars_map.items():
		processed_count += 1
		info = invoice_info.get(inv_no, {}) or invoice_info.get(normalize_inv_no(inv_no), {})
		bl_sw = info.get("bl_sw") or next((c.get("bl_sw") for c in cars if c.get("bl_sw")), "")

		inv_date = info.get("invoice_date") or (cars[0]["invoice_date"] if cars else frappe.utils.today())
		if not inv_date:
			inv_date = frappe.utils.today()

		conts = invoice_containers_map.get(inv_no, [])
		assign_containers_to_cars(cars, conts)

		existing_pi = existing_pi_map.get(inv_no) or frappe.db.get_value("Purchase Invoice", {"bill_no": inv_no, "docstatus": ["!=", 2]}, "name")


		missing_chassis = []
		valid_car_items = []
		for car in cars:
			chassis_no = car["chassis_no"]
			car_price = car["car_price"]
			car_container_no = car.get("container_no", "")
			item_name = find_item_by_chassis(chassis_no, cache=chassis_cache)
			if item_name:
				valid_car_items.append({
					"item_code": item_name,
					"chassis_no": chassis_no,
					"car_price": car_price,
					"container_no": car_container_no,
					"color": car.get("color"),
				})
			else:
				missing_chassis.append(chassis_no)
				failed_records.append({
					"chassis_no": chassis_no,
					"invoice_no": inv_no,
					"error": f"Item for Chassis No '{chassis_no}' not found in database.",
					"data": car,
				})

		if missing_chassis:
			error_count += len(missing_chassis)
			missing_str = ", ".join(f"'{c}'" for c in missing_chassis)
			reason = f"Item not found in database for Chassis No(s): {missing_str}"
			if existing_pi:
				not_created_pi_logs.append(f"Purchase Invoice '{existing_pi}' not updated for Supplier Invoice No: {inv_no}. Reason: {reason}")
			else:
				not_created_pi_logs.append(f"Purchase Invoice not created for Supplier Invoice No: {inv_no}. Reason: {reason}")
			continue

		try:
			elapsed_str = f"{round(time.time() - start_time, 1)}s"
			if docname:
				publish_import_progress(
					docname,
					processed_invoices=processed_count,
					total_invoices=total_invoices,
					active_step_text=f"Creating/Updating Purchase Invoice '{inv_no}' ({processed_count}/{total_invoices})...",
					time_elapsed_str=elapsed_str,
				)

			if existing_pi:
				pi_doc = frappe.get_doc("Purchase Invoice", existing_pi)
				is_new_pi = False
			else:
				pi_doc = frappe.new_doc("Purchase Invoice")
				pi_doc.supplier = supplier_name
				pi_doc.bill_no = inv_no
				is_new_pi = True

			if pi_doc.docstatus == 0:
				supplier_currency = frappe.db.get_value("Supplier", supplier_name, "default_currency") or "JPY"
				if supplier_currency:
					pi_doc.currency = supplier_currency
				pi_doc.bill_date = format_date(inv_date) or frappe.utils.today()
				pi_doc.posting_date = pi_doc.bill_date
				payable_acc = get_supplier_payable_account(supplier_name, pi_doc.company, pi_doc.currency)
				if payable_acc:
					pi_doc.credit_to = payable_acc
				if not getattr(pi_doc, "conversion_rate", None):
					pi_doc.conversion_rate = 1.0
				ensure_currency_exchange(pi_doc.currency, frappe.db.get_value("Company", pi_doc.company, "default_currency"), pi_doc.conversion_rate)
				try:
					pi_doc.set_missing_values()
				except Exception:
					pass

				pi_doc.update_stock = 1


			if hasattr(pi_doc, "custom_bl_sw"):
				pi_doc.custom_bl_sw = bl_sw

			pi_doc.items = []
			for car in valid_car_items:
				item_row = pi_doc.append("items", {
					"item_code": car["item_code"],
					"qty": 1,
					"rate": car["car_price"],
				})
				item_row.custom_container_no = car.get("container_no") or ("RORO" if car.get("is_roro") else "")
				item_row.custom_blsw = bl_sw
				item_row.custom_bl = bl_sw
				if hasattr(item_row, "blsw"):
					item_row.blsw = bl_sw

			pi_doc.taxes = []

			cont_chassis_map = {}
			for car_item in valid_car_items:
				c_no = car_item.get("container_no") or ("RORO" if car_item.get("is_roro") else "Unassigned")
				cont_chassis_map.setdefault(c_no, []).append(car_item.get("chassis_no", ""))

			if hasattr(pi_doc, "custom_container_breakdown"):
				pi_doc.custom_container_breakdown = []
				for cont in conts:
					cont_key = cont.get("container_no") or ("RORO" if cont.get("is_roro") else "Unassigned")
					cont_total = cont.get("total", 0)
					if not cont_total:
						cont_total = sum(cont.get(fn, 0) for fn in [
							"thc", "forwarding", "freight", "inspection", "jpn_expense",
							"repair_cost", "car_expense", "vanning", "transportation",
							"freight_and_other", "cont_other_value", "inv_other_charges", "car_value",
						])
					chassis_list = cont_chassis_map.get(cont_key, [])
					if not chassis_list and (cont_key == "RORO" or cont.get("is_roro")):
						chassis_list = [c.get("chassis_no") for c in valid_car_items if c.get("chassis_no")]
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
						"cars": cont.get("cars", 0) or len(valid_car_items),
						"car_value": cont.get("car_value", 0) or sum(c.get("car_price", 0) for c in valid_car_items),
						"cont_other_value": cont.get("cont_other_value", 0),
						"inv_other_charges": cont.get("inv_other_charges", 0),
						"cont_price": cont.get("cont_price", 0),
						"total": cont_total,
						"currency": pi_doc.currency or "JPY",
					})


			if pi_doc.docstatus == 0:
				pi_doc.flags.ignore_mandatory = True
				pi_doc.flags.ignore_links = True
				pi_doc.save(ignore_permissions=True)
				if auto_submit_pi:
					pi_doc.flags.ignore_mandatory = True
					pi_doc.submit()

			bl_sw_str = f" (BL/SW: {bl_sw})" if bl_sw else ""
			if is_new_pi:
				created_pi += 1
				created_pi_logs.append(f"Created Purchase Invoice '{pi_doc.name}' for Supplier Invoice No: {inv_no}{bl_sw_str}")
			else:
				updated_pi += 1
				created_pi_logs.append(f"Updated Purchase Invoice '{pi_doc.name}' for Supplier Invoice No: {inv_no}{bl_sw_str}")

			if docname:
				publish_import_progress(
					docname,
					processed_invoices=processed_count,
					total_invoices=total_invoices,
					active_step_text=f"Creating Journal Entry for Supplier Invoice '{inv_no}'...",
					time_elapsed_str=elapsed_str,
				)

			jv_doc, is_new_jv = create_or_update_expense_journal_entry(
				pi_doc=pi_doc,
				inv_no=inv_no,
				inv_date=inv_date,
				bl_sw=bl_sw,
				conts=conts,
				expense_fields=EXPENSE_FIELDS,
				auto_submit_jv=auto_submit_jv,
				existing_jv_map=existing_jv_map,
			)

			if jv_doc:
				if is_new_jv:
					created_jv += 1
					created_pi_logs.append(f"  - Created Journal Entry '{jv_doc.name}' for Supplier Invoice No: {inv_no}")
				else:
					updated_jv += 1
					created_pi_logs.append(f"  - Updated Journal Entry '{jv_doc.name}' for Supplier Invoice No: {inv_no}")

			if create_lcv:
				if pi_doc.docstatus == 0:
					pi_doc.submit()
					created_pi_logs.append(f"  - Submitted Purchase Invoice '{pi_doc.name}'")
				total_charges = sum(sum(c.get(fn, 0.0) for fn in [f[0] for f in EXPENSE_FIELDS]) for c in conts)
				if total_charges > 0:
					lcv = create_or_update_lcv(pi_doc, conts, EXPENSE_FIELDS)
					if lcv:
						created_lcv += 1
						created_pi_logs.append(f"  - Created Landed Cost Voucher '{lcv.name}' for Purchase Invoice '{pi_doc.name}'")

			if processed_count % 25 == 0:
				frappe.db.commit()

		except Exception as exc:

			error_count += 1
			reason = str(exc)
			if existing_pi:
				not_created_pi_logs.append(f"Purchase Invoice '{existing_pi}' not updated for Supplier Invoice No: {inv_no}. Reason: {reason}")
			else:
				not_created_pi_logs.append(f"Purchase Invoice not created for Supplier Invoice No: {inv_no}. Reason: {reason}")
			frappe.log_error(title=f"Error processing Purchase Invoice for {inv_no}", message=frappe.get_traceback())

	all_conts = [c for conts_list in invoice_containers_map.values() for c in conts_list]
	all_cars = [c for cars_list in invoice_cars_map.values() for c in cars_list]

	container_full_count = len([c for c in all_conts if not c.get("is_roro")])
	roro_full_count = len([c for c in all_conts if c.get("is_roro")])
	container_car_count = len([c for c in all_cars if not c.get("is_roro")])
	roro_car_count = len([c for c in all_cars if c.get("is_roro")])


	all_logs = []
	if created_pi_logs:
		all_logs.append("--- Purchase Invoices Created / Updated ---")
		all_logs.extend(created_pi_logs)
		all_logs.append("")

	if not_created_pi_logs:
		all_logs.append("--- Purchase Invoices Not Created ---")
		all_logs.extend(not_created_pi_logs)
		all_logs.append("")

	return {
		"created_pi": created_pi,
		"updated_pi": updated_pi,
		"created_jv": created_jv,
		"updated_jv": updated_jv,
		"created_lcv": created_lcv,
		"errors": error_count,
		"created_pi_logs": created_pi_logs,
		"not_created_pi_logs": not_created_pi_logs,
		"log": all_logs,
		"container_full_count": container_full_count,
		"roro_full_count": roro_full_count,
		"container_car_count": container_car_count,
		"roro_car_count": roro_car_count,
		"failed_records": failed_records,
	}



# ==========================================
# SCHEDULER / WORKER 2: CARS & ITEMS UPDATER
# ==========================================

def run_car_updating_job(docname, car_rows, invoice_info, invoice_containers_map, total_cars, start_time):
	updated_items = 0
	error_count = 0
	logs = []
	failed_records = []
	chassis_cache = {}
	color_cache = {}

	# Bulk pre-fetch item mappings into chassis_cache in 1 query
	try:
		item_list = frappe.db.get_all("Item", fields=["name", "custom_chassis_no", "item_name"])
		for it in item_list:
			if it.custom_chassis_no:
				chassis_cache[str(it.custom_chassis_no).strip()] = it.name
			chassis_cache[str(it.name).strip()] = it.name
			if it.item_name:
				chassis_cache[str(it.item_name).strip()] = it.name
	except Exception:
		pass

	processed_count = 0

	for car in car_rows:
		processed_count += 1
		chassis_no = car.get("chassis_no")
		car_price = car.get("car_price", 0.0)
		inv_no = car.get("invoice_no")
		car_container_no = car.get("container_no") or ("RORO" if car.get("is_roro") else "")

		if not chassis_no:
			continue

		info = invoice_info.get(normalize_inv_no(inv_no), {}) if inv_no else {}
		bl_sw = car.get("bl_sw") or info.get("bl_sw") or ""

		item_name = find_item_by_chassis(chassis_no, cache=chassis_cache)
		if not item_name:
			error_count += 1
			failed_records.append({
				"chassis_no": chassis_no,
				"invoice_no": inv_no,
				"error": f"Item for Chassis No '{chassis_no}' not found in database.",
				"data": car,
			})
			continue

		try:
			if docname and processed_count % 10 == 0:
				elapsed_str = f"{round(time.time() - start_time, 1)}s"
				publish_import_progress(
					docname,
					processed_cars=processed_count,
					total_cars=total_cars,
					active_step_text=f"Updating Car Item '{chassis_no}' ({processed_count}/{total_cars})...",
					time_elapsed_str=elapsed_str,
				)

			item_updates = {"custom_price": car_price, "standard_rate": car_price}
			if bl_sw:
				item_updates["custom_bl"] = bl_sw
			if car_container_no:
				item_updates["custom_container_no"] = car_container_no
			if car.get("color"):
				color_doc = ensure_item_color(car["color"], cache=color_cache)
				if color_doc:
					item_updates["custom_color"] = color_doc

			frappe.db.set_value("Item", item_name, item_updates, update_modified=False)
			updated_items += 1

			if processed_count % 50 == 0:
				frappe.db.commit()

		except Exception as e:
			error_count += 1
			logs.append(f"Error updating Item '{item_name}': {str(e)}")
			frappe.log_error(title=f"Error updating Item {item_name}", message=frappe.get_traceback())

	frappe.db.commit()


	return {
		"updated_items": updated_items,
		"errors": error_count,
		"logs": logs,
		"failed_records": failed_records,
	}


# ==========================================
# JOURNAL ENTRY HELPER FOR EXPENSES
# ==========================================

def create_or_update_expense_journal_entry(pi_doc, inv_no, inv_date, bl_sw, conts, expense_fields, auto_submit_jv=False, existing_jv_map=None):
	if not conts or not pi_doc:
		return None, False

	total_charges = sum(sum(c.get(fn, 0.0) for fn in [f[0] for f in expense_fields]) for c in conts)
	if total_charges <= 0:
		return None, False

	company = pi_doc.company
	currency = pi_doc.currency or "JPY"
	supplier_name = pi_doc.supplier or "JAN JAPAN"

	company_currency = frappe.db.get_value("Company", company, "default_currency") or "JPY"
	conversion_rate = frappe.utils.flt(getattr(pi_doc, "conversion_rate", 1.0)) or 1.0
	ensure_currency_exchange(currency, company_currency, conversion_rate)

	existing_jv_name = (existing_jv_map.get(str(inv_no)) if existing_jv_map is not None else None) or frappe.db.get_value("Journal Entry", {"cheque_no": str(inv_no), "company": company, "docstatus": ["!=", 2]}, "name")

	if existing_jv_name:
		jv_doc = frappe.get_doc("Journal Entry", existing_jv_name)
		if jv_doc.docstatus != 0:
			return jv_doc, False
		is_new = False
	else:
		jv_doc = frappe.new_doc("Journal Entry")
		jv_doc.voucher_type = "Journal Entry"
		jv_doc.company = company
		is_new = True

	jv_date = format_date(inv_date) or pi_doc.posting_date or frappe.utils.today()
	jv_doc.posting_date = jv_date
	jv_doc.cheque_no = str(inv_no)
	jv_doc.cheque_date = jv_date

	cont_list = list(set([str(c.get("container_no", "")).strip() for c in conts if c.get("container_no")]))
	cont_str = ", ".join(c for c in cont_list if c) if cont_list else "None"
	jv_doc.user_remark = f"Expense Charges for Supplier Invoice: {inv_no} | BL/SW: {bl_sw or 'N/A'} | Container(s): {cont_str} | Purchase Invoice: {pi_doc.name}"

	jv_doc.accounts = []
	total_debit = 0.0
	has_multi_curr = (currency != company_currency)

	for fieldname, charge_label in expense_fields:
		amt = sum(c.get(fieldname, 0.0) for c in conts)
		if amt > 0:
			tax_account = get_tax_expense_account(company, charge_label, currency)
			if not tax_account:
				tax_account = get_company_expense_account(company)

			acc_curr = frappe.db.get_value("Account", tax_account, "account_currency") or currency
			if acc_curr and acc_curr != company_currency:
				has_multi_curr = True
			rate = conversion_rate if acc_curr != company_currency else 1.0
			base_amt = amt * rate
			jv_doc.append("accounts", {
				"account": tax_account,
				"debit_in_account_currency": amt,
				"debit": base_amt,
				"account_currency": acc_curr,
				"exchange_rate": rate,
				"description": charge_label,
			})
			total_debit += amt

	if total_debit > 0:
		payable_acc = get_supplier_payable_account(supplier_name, company, currency)
		acc_curr = frappe.db.get_value("Account", payable_acc, "account_currency") or currency
		if acc_curr and acc_curr != company_currency:
			has_multi_curr = True
		rate = conversion_rate if acc_curr != company_currency else 1.0
		base_credit = total_debit * rate
		jv_doc.append("accounts", {
			"account": payable_acc,
			"party_type": "Supplier",
			"party": supplier_name,
			"credit_in_account_currency": total_debit,
			"credit": base_credit,
			"account_currency": acc_curr,
			"exchange_rate": rate,
			"description": f"Payable for expense charges on Invoice {inv_no}",
		})

		jv_doc.multi_currency = 1 if has_multi_curr else 0
		jv_doc.flags.ignore_mandatory = True
		jv_doc.flags.ignore_links = True
		jv_doc.save(ignore_permissions=True)

		if auto_submit_jv and jv_doc.docstatus == 0:
			jv_doc.flags.ignore_mandatory = True
			jv_doc.submit()

		return jv_doc, is_new

	return None, False




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
		for fieldname, charge_label in expense_fields:
			amt = sum(c.get(fieldname, 0.0) for c in conts)
			if amt > 0:
				tax_account = get_tax_expense_account(pi_doc.company, charge_label, pi_doc.currency)
				lcv.append("taxes", {
					"expense_account": tax_account,
					"description": charge_label,
					"amount": amt,
				})

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
		frappe.log_error(title=f"Error creating Landed Cost Voucher for {pi_doc.name}", message=frappe.get_traceback())
		return None


def get_company_cost_center(company):
	if not company:
		company = frappe.defaults.get_user_default("Company") or frappe.db.get_single_value("Global Defaults", "default_company")
	cc = frappe.db.get_value("Company", company, "cost_center")
	if not cc:
		cc = frappe.db.get_value("Cost Center", {"company": company, "is_group": 0}, "name")
	return cc


def get_tax_expense_account(company, tax_label, target_currency=None):
	if not company or not tax_label:
		return get_company_expense_account(company)

	tax_label_clean = str(tax_label).strip().lower()

	try:
		company_doc = frappe.get_doc("Company", company)
		mappings = getattr(company_doc, "custom_tax_expense_accounts", []) or []

		if target_currency:
			for row in mappings:
				row_tax = str(row.tax_name or "").strip().lower()
				if row_tax == tax_label_clean and row.account:
					acc_curr = row.account_currency or frappe.db.get_value("Account", row.account, "account_currency")
					if acc_curr == target_currency:
						return ensure_tax_expense_account_exists(company, row.account, target_currency, tax_label)

		for row in mappings:
			row_tax = str(row.tax_name or "").strip().lower()
			if row_tax == tax_label_clean and row.account:
				acc_curr = row.account_currency or frappe.db.get_value("Account", row.account, "account_currency")
				if not acc_curr or not target_currency or acc_curr == target_currency:
					return ensure_tax_expense_account_exists(company, row.account, target_currency, tax_label)
	except Exception:
		pass

	company_abbr = frappe.db.get_value("Company", company, "abbr") or ""
	acc_candidates = [
		f"{tax_label} - {company_abbr}" if company_abbr else tax_label,
		f"{tax_label} {target_currency} - {company_abbr}" if (company_abbr and target_currency) else None,
		tax_label,
	]
	for cand in acc_candidates:
		if cand and frappe.db.exists("Account", cand):
			return cand

	return get_company_expense_account(company)



def ensure_tax_expense_account_exists(company, account_name, currency=None, tax_label=None):
	if not account_name:
		return get_company_expense_account(company)

	if frappe.db.exists("Account", account_name):
		return account_name

	company_abbr = frappe.db.get_value("Company", company, "abbr") or ""
	acc_title = account_name
	if company_abbr and account_name.endswith(f" - {company_abbr}"):
		acc_title = account_name[:-len(f" - {company_abbr}")].strip()

	parent_acc = frappe.db.get_value("Account", {"company": company, "account_type": "Expenses Included In Valuation", "is_group": 1}, "name")
	if not parent_acc:
		parent_acc = frappe.db.get_value("Account", {"company": company, "root_type": "Expense", "is_group": 1}, "name")

	if parent_acc:
		try:
			new_acc = frappe.new_doc("Account")
			new_acc.account_name = acc_title
			new_acc.parent_account = parent_acc
			new_acc.company = company
			new_acc.account_type = "Expenses Included In Valuation"
			new_acc.account_currency = currency or frappe.db.get_value("Company", company, "default_currency") or "JPY"
			new_acc.insert(ignore_permissions=True)
			return new_acc.name
		except Exception:
			pass


	return get_company_expense_account(company)




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

			if "RORO FULL INVOICE VALUE" in line_text or ("RORO" in line_text and "FULL INVOICE VALUE" in line_text):
				current_section = "RORO_FULL_INVOICE_VALUE"
				current_headers = None
				continue
			elif ("RORO CARS" in line_text or ("RORO" in line_text and "CARS" in line_text)) and "VALUE" not in line_text and "INVOICE" not in line_text:
				current_section = "RORO_CARS"
				current_headers = None
				continue
			elif "INVOICE CARS" in line_text and "NOT INVOICED" not in line_text and "RORO" not in line_text and "CONTAINER" not in line_text and "VALUE" not in line_text:
				current_section = "INVOICE_CARS"
				current_headers = None
				continue
			elif "FULL INVOICE VALUE" in line_text and "RORO" not in line_text:
				current_section = "FULL_INVOICE_VALUE"
				current_headers = None
				continue

			elif "ANNEXURE TO MARKET" in line_text or any(kw in line_text for kw in [
				"CONTAINER PRICE", "RORO CHARGES", "CONTAINERS OTHER",
				"NOT INVOICED", "STOCK IN JAPAN", "TT RECEIPT ON THE WAY",
				"ON THE WAY ADJUSTMENTS"
			]):
				current_section = "OTHER"
				current_headers = None
				continue

			# Table 1: Full Invoice Value (Container)
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

					bl_sw_val = get_cell_by_headers(row_dict, BL_SEARCH_KEYS)
					target_inv_blsw = normalize_inv_no(inv_no or current_invoice_no)
					if target_inv_blsw and bl_sw_val:
						if target_inv_blsw not in invoice_info:
							invoice_info[target_inv_blsw] = {}
						invoice_info[target_inv_blsw]["bl_sw"] = invoice_info[target_inv_blsw].get("bl_sw") or bl_sw_val

					if cont_no and cont_no.lower() not in ("total", "sr#", "inv text", "container no."):
						inv_other_charges_val = parse_float(get_cell_by_headers(row_dict, ["INV OTHER CHARGES", "INV. OTHER CHARGES", "OTHER CHARGES", "INV OTHER VALUE"]))

						if cont_no.lower() in ("inv other charges", "inv. other charges", "other charges"):
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
								"is_roro": False,
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
								"is_roro": False,
							})
					continue

			# Table 2: Invoice Cars (Container)
			if current_section == "INVOICE_CARS":
				if current_headers is None:
					if any("CHASSIS" in s.upper() for s in row_str_cells) and any("INVOICE" in s.upper() for s in row_str_cells):
						current_headers = [clean_str(c) for c in row]
					continue
				else:
					row_dict = dict(zip(current_headers, row_str_cells))
					chassis_no = get_cell_by_headers(row_dict, ["CHASSIS NO", "CHASSIS NO.", "CHASSIS_NO", "CHASSIS"])
					inv_no = get_cell_by_headers(row_dict, ["INVOICE NO", "INVOICE NO.", "INVOICE_NO", "INVOICE"])

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
							"is_roro": False,
						})
					continue

			# Table 3: RORO Full Invoice Value
			if current_section == "RORO_FULL_INVOICE_VALUE":
				if current_headers is None:
					if any("INVOICE" in s.upper() for s in row_str_cells) and any("FREIGHT" in s.upper() or "INSPECTION" in s.upper() or "SHIPPING" in s.upper() or "EXPENSE" in s.upper() for s in row_str_cells):
						current_headers = [clean_str(c) for c in row]
					continue
				else:
					row_dict = dict(zip(current_headers, row_str_cells))
					inv_no = get_cell_by_headers(row_dict, ["INVOICE NO", "INVOICE NO.", "INVOICE_NO", "INVOICE"])
					inv_date = format_date(get_cell_by_headers(row_dict, ["INVOICE DATE", "INVOICE_DATE", "DATE"]))
					if inv_no and inv_no.lower() not in ("total", "sr#", "inv text", "invoice no."):
						inspection_amt = parse_float(get_cell_by_headers(row_dict, ["INSPECTION CHARGES", "INSPECTION", "INSP. CHARGES"]))
						freight_amt = parse_float(get_cell_by_headers(row_dict, ["OCEAN FREIGHT", "FREIGHT", "FREIGHT CHARGES"]))
						thc_amt = parse_float(get_cell_by_headers(row_dict, ["SHIPPING CHARGES", "SHIPPING", "THC"]))
						forw_amt = parse_float(get_cell_by_headers(row_dict, ["FORWARDING", "FORW. CHARGES"]))
						jpn_exp = parse_float(get_cell_by_headers(row_dict, ["JAPAN EXPENSE", "JPN EXPENSE"]))
						repair_cost = parse_float(get_cell_by_headers(row_dict, ["REPAIR COST"]))
						car_exp = parse_float(get_cell_by_headers(row_dict, ["CAR EXPENSE"]))
						vanning_amt = parse_float(get_cell_by_headers(row_dict, ["VANNING"]))
						trans_amt = parse_float(get_cell_by_headers(row_dict, ["TRANSPORTATION"]))
						freight_other = parse_float(get_cell_by_headers(row_dict, ["FREIGHT & OTHER", "FREIGHT AND OTHER"]))
						inv_other_charges_val = parse_float(get_cell_by_headers(row_dict, ["INV OTHER CHARGES", "INV. OTHER CHARGES", "OTHER CHARGES"]))
						cars_count = parse_int(get_cell_by_headers(row_dict, ["CARS"]))
						car_val = parse_float(get_cell_by_headers(row_dict, ["RORO CARS VALUE", "CAR VALUE"]))
						cont_other_val = parse_float(get_cell_by_headers(row_dict, ["CONT. OTHER VALUE", "CONT OTHER VALUE"]))
						cont_price = parse_float(get_cell_by_headers(row_dict, ["CONT. PRICE", "CONT PRICE"]))
						total_amt = parse_float(get_cell_by_headers(row_dict, ["TOTAL"]))
						bl_sw_val = clean_str(get_cell_by_headers(row_dict, BL_SEARCH_KEYS))

						sum_expenses = (thc_amt + forw_amt + inspection_amt + freight_amt + jpn_exp + repair_cost + car_exp + vanning_amt + trans_amt + freight_other + inv_other_charges_val)

						container_rows.append({
							"container_no": "RORO",
							"thc": thc_amt,
							"forwarding": forw_amt,
							"freight": freight_amt,
							"inspection": inspection_amt,
							"jpn_expense": jpn_exp,
							"repair_cost": repair_cost,
							"car_expense": car_exp,
							"vanning": vanning_amt,
							"transportation": trans_amt,
							"freight_and_other": freight_other,
							"inv_other_charges": inv_other_charges_val,
							"cars": cars_count,
							"car_value": car_val,
							"cont_other_value": cont_other_val,
							"cont_price": cont_price,
							"total": total_amt or (sum_expenses + car_val),
							"invoice_no": inv_no,
							"is_roro": True,
						})
						if inv_no:
							norm_inv = normalize_inv_no(inv_no)
							if norm_inv not in invoice_info:
								invoice_info[norm_inv] = {}
							if inv_date:
								invoice_info[norm_inv]["invoice_date"] = invoice_info[norm_inv].get("invoice_date") or inv_date
							if bl_sw_val:
								invoice_info[norm_inv]["bl_sw"] = invoice_info[norm_inv].get("bl_sw") or bl_sw_val
					continue


			# Table 4: RORO Cars
			if current_section == "RORO_CARS":
				if current_headers is None:
					if any("CHASSIS" in s.upper() for s in row_str_cells) and any("INVOICE" in s.upper() for s in row_str_cells):
						current_headers = [clean_str(c) for c in row]
					continue
				else:
					row_dict = dict(zip(current_headers, row_str_cells))
					chassis_no = get_cell_by_headers(row_dict, ["CHASSIS NO", "CHASSIS NO.", "CHASSIS_NO", "CHASSIS"])
					inv_no = get_cell_by_headers(row_dict, ["INVOICE NO", "INVOICE NO.", "INVOICE_NO", "INVOICE"])
					inv_date = format_date(get_cell_by_headers(row_dict, ["INVOICE DATE", "INVOICE_DATE", "DATE"]))
					if chassis_no and inv_no and chassis_no.lower() not in ("chassis no.", "chassis no"):
						car_rows.append({
							"stock_id": clean_str(get_cell_by_headers(row_dict, ["STOCK ID", "STOCK_ID"])),
							"chassis_no": chassis_no,
							"car_price": parse_float(get_cell_by_headers(row_dict, ["CAR PRICE", "PRICE"])),
							"invoice_no": inv_no,
							"invoice_date": inv_date,
							"container_no": "RORO",
							"is_roro": True,
							"bl_sw": "",
						})
						if inv_no and inv_date:
							norm_inv = normalize_inv_no(inv_no)
							if norm_inv not in invoice_info:
								invoice_info[norm_inv] = {}
							invoice_info[norm_inv]["invoice_date"] = invoice_info[norm_inv].get("invoice_date") or inv_date
					continue

			# Header Mapping
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


def find_item_by_chassis(chassis_no, cache=None):
	if not chassis_no:
		return None
	chassis_no = str(chassis_no).strip()

	if cache is not None and chassis_no in cache:
		return cache[chassis_no]

	# 1. Custom Chassis No
	name = frappe.db.get_value("Item", {"custom_chassis_no": chassis_no}, "name")
	if not name:
		# 2. Exact item_code
		if frappe.db.exists("Item", chassis_no):
			name = chassis_no
		else:
			# 3. Item Name contains chassis_no
			name = frappe.db.get_value("Item", [["Item", "item_name", "like", f"%{chassis_no}%"]], "name")

	if cache is not None and name:
		cache[chassis_no] = name

	return name


def ensure_item_color(color_name, cache=None):
	if not color_name:
		return None

	raw_str = str(color_name).strip()
	if not raw_str:
		return None

	# Format to Title Case Abc e.g. "Silver Blue", "Dark Grey", "Pearl White"
	formatted = " ".join(word.capitalize() for word in raw_str.split())
	if not formatted:
		return None

	if cache is not None and formatted in cache:
		return cache[formatted]

	# Check if Item Color already exists by color_name
	existing = frappe.db.get_value("Item Color", {"color_name": formatted}, "name")
	if not existing:
		existing = frappe.db.get_value("Item Color", [["Item Color", "color_name", "like", formatted]], "name")

	if existing:
		if cache is not None:
			cache[formatted] = existing
		return existing

	try:
		doc = frappe.new_doc("Item Color")
		doc.color_name = formatted
		doc.insert(ignore_permissions=True)
		res = doc.name
	except Exception:
		res = frappe.db.get_value("Item Color", {"color_name": formatted}, "name") or formatted

	if cache is not None:
		cache[formatted] = res
	return res


def ensure_supplier(supplier_name="JAN JAPAN"):
	if frappe.db.exists("Supplier", supplier_name):
		return supplier_name
	doc = frappe.new_doc("Supplier")
	doc.supplier_name = supplier_name
	doc.supplier_group = "All Supplier Groups"
	doc.default_currency = "JPY"
	doc.insert(ignore_permissions=True)
	return doc.name


def ensure_payable_account(company, currency):
	if not company or not currency:
		return None
	# 1. Existing Payable account matching company and currency
	acc = frappe.db.get_value("Account", {"company": company, "account_type": "Payable", "account_currency": currency, "is_group": 0}, "name")
	if acc:
		return acc
	# 2. Existing Payable account with blank/null currency (allows any currency)
	acc = frappe.db.get_value("Account", {"company": company, "account_type": "Payable", "account_currency": ["in", ["", None]], "is_group": 0}, "name")
	if acc:
		return acc
	# 3. Create a new Payable Account for foreign currency
	company_currency = frappe.db.get_value("Company", company, "default_currency")
	if company_currency and company_currency != currency:
		parent_payable = frappe.db.get_value("Account", {"company": company, "account_type": "Payable", "is_group": 1}, "name")
		if not parent_payable:
			parent_payable = frappe.db.get_value("Account", {"company": company, "root_type": "Liability", "is_group": 1}, "name")
		if parent_payable:
			company_abbr = frappe.db.get_value("Company", company, "abbr") or ""
			acc_name = f"Creditors {currency}"
			target_name = f"{acc_name} - {company_abbr}" if company_abbr else acc_name
			if frappe.db.exists("Account", target_name):
				return target_name
			try:
				new_acc = frappe.new_doc("Account")
				new_acc.account_name = acc_name
				new_acc.parent_account = parent_payable
				new_acc.company = company
				new_acc.account_type = "Payable"
				new_acc.account_currency = currency
				new_acc.insert(ignore_permissions=True)
				return new_acc.name
			except Exception:
				pass
	return None


def get_supplier_payable_account(supplier_name, company, currency):
	if not supplier_name or not company:
		return ensure_payable_account(company, currency)

	try:
		supplier_doc = frappe.get_doc("Supplier", supplier_name)
		for row in getattr(supplier_doc, "accounts", []):
			if row.company == company and row.account:
				acc_curr = getattr(row, "account_currency", None) or frappe.db.get_value("Account", row.account, "account_currency")
				if not acc_curr or not currency or acc_curr == currency:
					return row.account

		for row in getattr(supplier_doc, "accounts", []):
			if row.company == company and row.account:
				return row.account
	except Exception:
		pass

	return ensure_payable_account(company, currency)


def ensure_currency_exchange(from_currency, to_currency, rate=1.0):
	if not from_currency or not to_currency or from_currency == to_currency:
		return
	existing = frappe.db.get_value("Currency Exchange", {
		"from_currency": from_currency,
		"to_currency": to_currency,
		"for_buying": 1
	}, "name")
	if not existing:
		try:
			ce = frappe.new_doc("Currency Exchange")
			ce.from_currency = from_currency
			ce.to_currency = to_currency
			ce.exchange_rate = rate or 1.0
			ce.for_buying = 1
			ce.for_selling = 1
			ce.date = frappe.utils.today()
			ce.insert(ignore_permissions=True)
		except Exception:
			pass




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


@frappe.whitelist()
def download_errored_rows(docname):
	doc = frappe.get_doc("Item Excel Importer", docname)
	if not doc.failed_records:
		frappe.throw(_("No errored rows found for this importer."))

	try:
		failed_records = json.loads(doc.failed_records) if isinstance(doc.failed_records, str) else doc.failed_records
	except Exception:
		failed_records = []

	if not failed_records or not isinstance(failed_records, list):
		frappe.throw(_("No errored rows found to export."))

	xlsx_content = generate_errored_rows_xlsx(failed_records)

	file_name = f"Errored_Rows_{doc.name}.xlsx"
	frappe.response["filename"] = file_name
	frappe.response["filecontent"] = xlsx_content
	frappe.response["type"] = "binary"


def generate_errored_rows_xlsx(failed_records):
	import io
	import openpyxl
	from openpyxl.styles import Alignment, Font, PatternFill
	from openpyxl.utils import get_column_letter

	wb = openpyxl.Workbook()
	ws = wb.active
	ws.title = "Errored Rows"

	data_keys = []
	for rec in failed_records:
		if isinstance(rec, dict):
			data_dict = rec.get("data")
			if isinstance(data_dict, dict):
				for k in data_dict.keys():
					if k not in data_keys and str(k).lower() not in ("row", "error", "import error"):
						data_keys.append(k)

	headers = []
	has_row = any(isinstance(rec, dict) and "row" in rec for rec in failed_records)
	has_inv = any(isinstance(rec, dict) and "invoice_no" in rec for rec in failed_records) and not any(str(k).lower() == "invoice_no" for k in data_keys)
	has_chassis = any(isinstance(rec, dict) and "chassis_no" in rec for rec in failed_records) and not any(str(k).lower() == "chassis_no" for k in data_keys)

	if has_row:
		headers.append("Row")
	if has_inv:
		headers.append("Invoice No")
	if has_chassis:
		headers.append("Chassis No")

	headers.extend(data_keys)
	headers.append("Import Error")

	ws.append(headers)

	header_fill = PatternFill(start_color="1F497D", end_color="1F497D", fill_type="solid")
	header_font = Font(bold=True, color="FFFFFF", size=11)
	header_align = Alignment(horizontal="center", vertical="center", wrap_text=True)

	for cell in ws[1]:
		cell.fill = header_fill
		cell.font = header_font
		cell.alignment = header_align

	error_fill = PatternFill(start_color="FCE4D6", end_color="FCE4D6", fill_type="solid")
	error_font = Font(color="C00000")

	for rec in failed_records:
		if not isinstance(rec, dict):
			continue

		row_data = []
		data_dict = rec.get("data") if isinstance(rec.get("data"), dict) else {}

		if has_row:
			row_data.append(rec.get("row", ""))
		if has_inv:
			row_data.append(rec.get("invoice_no") or data_dict.get("invoice_no", ""))
		if has_chassis:
			row_data.append(rec.get("chassis_no") or data_dict.get("chassis_no", ""))

		for key in data_keys:
			val = data_dict.get(key, "")
			row_data.append(val if val is not None else "")

		err_msg = rec.get("error", "")
		row_data.append(str(err_msg))

		ws.append(row_data)

		last_cell = ws.cell(row=ws.max_row, column=len(row_data))
		last_cell.fill = error_fill
		last_cell.font = error_font

	for col in ws.columns:
		max_len = max(len(str(cell.value or "")) for cell in col)
		col_letter = get_column_letter(col[0].column)
		ws.column_dimensions[col_letter].width = min(max(max_len + 4, 12), 60)

	output = io.BytesIO()
	wb.save(output)
	output.seek(0)
	return output.getvalue()
