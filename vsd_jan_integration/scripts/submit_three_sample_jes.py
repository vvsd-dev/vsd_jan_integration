import frappe
from frappe.utils import flt

def execute():
    CC = "Main - JIL"
    SAMPLES = ["T.TAN068/26MSC", "F.TAN032/26MSC", "K.TAN001/26MOLRORO"]

    je_names = set()
    for if_name in SAMPLES:
        inv = frappe.db.get_value("Import File", if_name, "supplier_invoice_no")
        je = frappe.db.get_value("Journal Entry", {"cheque_no": inv, "docstatus": ["<", 2]}, "name")
        if je:
            je_names.add(je)
        rows = frappe.db.sql(
            """SELECT pii.item_code FROM `tabPurchase Invoice Item` pii
            INNER JOIN `tabPurchase Invoice` pi ON pi.name=pii.parent WHERE pi.import_file=%s""",
            if_name,
        )
        for r in rows:
            fje = frappe.db.get_value(
                "Journal Entry", {"cheque_no": f"FIXED|{r[0]}", "docstatus": ["<", 2]}, "name"
            )
            if fje:
                je_names.add(fje)

    for je in je_names:
        frappe.db.sql(
            "UPDATE `tabJournal Entry Account` SET cost_center=%s WHERE parent=%s AND IFNULL(cost_center,'')=''",
            (CC, je),
        )
    frappe.db.commit()

    ok, fail = [], []
    for je in sorted(je_names):
        doc = frappe.get_doc("Journal Entry", je)
        if doc.docstatus != 0:
            print("skip", je, doc.docstatus)
            continue
        debit = sum(flt(r.debit) for r in doc.accounts)
        credit = sum(flt(r.credit) for r in doc.accounts)
        if debit and not flt(doc.total_debit):
            frappe.db.set_value(
                "Journal Entry",
                je,
                {"total_debit": debit, "total_credit": credit, "difference": abs(debit - credit)},
                update_modified=False,
            )
            doc.reload()
        for row in doc.accounts:
            if not row.cost_center:
                row.cost_center = CC
        doc.flags.ignore_permissions = True
        try:
            doc.submit()
            ok.append(je)
            print("OK", je, (doc.cheque_no or "")[:55], "debit", doc.total_debit)
            frappe.db.commit()
        except Exception as e:
            fail.append((je, str(e)[:350]))
            print("FAIL", je, str(e)[:350])
            frappe.db.rollback()

    print("RESULT ok", len(ok), "fail", len(fail))

    from vsd_jan_integration.vsd_jan_international_customization.doctype.import_file_cost_voucher.import_file_cost_voucher import (
        load_from_import_file,
    )

    for if_name in SAMPLES:
        ifcv_name = frappe.db.get_value("Import File Cost Voucher", {"import_file": if_name}, "name")
        data = load_from_import_file(if_name)
        print(if_name, "veh", len(data["vehicles"]), "exp", len(data["expenses"]))
        for e in data["expenses"][:4]:
            print("  exp", e.get("description") or e.get("expense_account"), e.get("amount"), e.get("currency"))
        if ifcv_name:
            doc = frappe.get_doc("Import File Cost Voucher", ifcv_name)
            if doc.docstatus == 0:
                doc.set("vehicles", [])
                doc.set("expenses", [])
                doc.set("allocations", [])
                for v in data["vehicles"]:
                    doc.append("vehicles", v)
                for e in data["expenses"]:
                    doc.append("expenses", e)
                doc.save(ignore_permissions=True)
                print(" refreshed", ifcv_name, "alloc", len(doc.allocations or []))
    frappe.db.commit()
