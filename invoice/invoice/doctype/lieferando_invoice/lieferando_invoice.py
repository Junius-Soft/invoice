# Copyright (c) 2025, invoice and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from invoice.api.constants import DOCTYPE_LIEFERANDO_INVOICE_ANALYSIS


class LieferandoInvoice(Document):
	def on_update(self):
		"""Keep linked Lieferando Invoice Analysis in sync after PDF re-parse / manual corrections.

		- Updates `invoice_data_json` (used by Analysis print formats).
		- Best-effort updates a few key mirror fields to avoid stale values in Analysis.
		- Never blocks saving the invoice; errors are logged.
		"""
		try:
			analysis_name = frappe.db.get_value(
				DOCTYPE_LIEFERANDO_INVOICE_ANALYSIS,
				{"lieferando_invoice": self.name},
				"name",
			)
			if not analysis_name:
				return

			# Prepare all updates in one dict (JSON + mirror fields)
			invoice_dict = self.as_dict(convert_dates_to_str=True)
			fields_to_update = {
				"invoice_data_json": frappe.as_json(invoice_dict, indent=2),
				"restaurant_name": getattr(self, "restaurant_name", "") or "",
				"customer_number": getattr(self, "customer_number", "") or "",
				"customer_tax_number": getattr(self, "customer_tax_number", "") or "",
				"invoice_number": getattr(self, "invoice_number", "") or "",
				"period_start": getattr(self, "period_start", None),
				"period_end": getattr(self, "period_end", None),
				"total_orders": getattr(self, "total_orders", 0) or 0,
				"total_revenue": getattr(self, "total_revenue", 0) or 0,
				"online_paid_orders": getattr(self, "online_paid_orders", 0) or 0,
				"online_paid_amount": getattr(self, "online_paid_amount", 0) or 0,
				"cash_paid_orders": getattr(self, "cash_paid_orders", 0) or 0,
				"cash_paid_amount": getattr(self, "cash_paid_amount", 0) or 0,
				"cash_service_fee_amount": getattr(self, "cash_service_fee_amount", 0) or 0,
				"chargeback_orders": getattr(self, "chargeback_orders", 0) or 0,
				"chargeback_amount": getattr(self, "chargeback_amount", 0) or 0,
				"tips_amount": getattr(self, "tips_amount", 0) or 0,
				"stamp_card_amount": getattr(self, "stamp_card_amount", 0) or 0,
				"pending_online_payments_g": getattr(self, "ausstehende_onlinebezahlungen_betrag", 0) or 0,
				"service_fee_rate": getattr(self, "service_fee_rate", 0) or 0,
			}

			# Single DB call to update all fields at once
			frappe.db.set_value(
				DOCTYPE_LIEFERANDO_INVOICE_ANALYSIS,
				analysis_name,
				fields_to_update,
				update_modified=False,
			)
		except Exception:
			frappe.log_error(
				title="Lieferando Analysis Sync Error",
				message=f"Failed to sync Analysis for invoice {self.name}\n{frappe.get_traceback()}",
			)

