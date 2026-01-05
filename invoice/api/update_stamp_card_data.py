#!/usr/bin/env python3
"""
Update existing Lieferando Invoices with stamp card (loyalty program) data
Extracts stamp_card_orders and stamp_card_amount from raw_text if available
"""

import frappe
import re
from frappe.utils import flt
from invoice.api.constants import DOCTYPE_LIEFERANDO_INVOICE

logger = frappe.logger("invoice.stamp_card", allow_site=frappe.local.site)

def _extract_decimal_from_match(match, group_index=1):
    """Extract decimal value from regex match"""
    if not match:
        return None
    try:
        amount_str = match.group(group_index).replace('.', '').replace(',', '.')
        return float(amount_str)
    except (ValueError, IndexError, AttributeError):
        return None

def extract_stamp_card_from_text(raw_text):
    """Extract stamp card data from raw PDF text"""
    if not raw_text:
        return None, None
    
    # Extract stamp card (Stempelkarte) orders and amount
    # Pattern: "davon mit Stempelkarte bezahlt **: 1 Bestellung im Wert von € 12,69"
    stamp_card_patterns = [
        r'davon mit Stempelkarte bezahlt\s*\*\*\s*:\s*(\d+)\s+Bestellung[^€]*€\s*([\d,\.]+)',  # With colon
        r'davon mit Stempelkarte bezahlt\s*\*\*\s+(\d+)\s+Bestellung[^€]*€\s*([\d,\.]+)',  # Without colon
        r'Stempelkarte bezahlt\s*\*\*\s*:\s*(\d+)\s+Bestellung[^€]*€\s*([\d,\.]+)',  # Alternative format
    ]
    
    for pattern in stamp_card_patterns:
        stamp_card_match = re.search(pattern, raw_text, re.IGNORECASE)
        if stamp_card_match:
            orders = int(stamp_card_match.group(1))
            amount = _extract_decimal_from_match(stamp_card_match, group_index=2)
            if amount is not None:
                return orders, amount
    
    return None, None

def update_invoice_stamp_card_data(invoice_name):
    """Update a single invoice with stamp card data"""
    try:
        invoice = frappe.get_doc(DOCTYPE_LIEFERANDO_INVOICE, invoice_name)
        
        # Skip if already has stamp card data
        if invoice.stamp_card_orders and invoice.stamp_card_orders > 0:
            logger.debug(f"{invoice.invoice_number}: Zaten stamp_card verisi var (orders: {invoice.stamp_card_orders})")
            return False
        
        # Extract from raw_text
        if not invoice.raw_text:
            logger.warning(f"{invoice.invoice_number}: raw_text yok, atlanıyor")
            return False
        
        orders, amount = extract_stamp_card_from_text(invoice.raw_text)
        
        if orders is not None and amount is not None:
            invoice.stamp_card_orders = orders
            invoice.stamp_card_amount = flt(amount)
            invoice.save(ignore_permissions=True)
            frappe.db.commit()
            logger.info(f"{invoice.invoice_number}: Güncellendi (orders: {orders}, amount: €{amount:.2f})")
            return True
        else:
            logger.debug(f"{invoice.invoice_number}: PDF'de stamp_card verisi bulunamadı")
            return False
            
    except Exception as e:
        logger.error(f"{invoice_name}: Hata - {str(e)}")
        frappe.log_error(
            title="Stamp Card Update Error",
            message=f"Invoice: {invoice_name}\nError: {str(e)}"
        )
        return False

def update_all_invoices():
    """Update all Lieferando Invoices with stamp card data"""
    logger.info("=" * 80)
    logger.info("STAMP CARD (LOYALTY PROGRAM) VERİLERİNİ GÜNCELLEME")
    logger.info("=" * 80)
    
    # Get all invoices
    invoices = frappe.get_all(
        DOCTYPE_LIEFERANDO_INVOICE,
        fields=["name", "invoice_number"],
        filters={},
        order_by="creation desc"
    )
    
    total = len(invoices)
    updated = 0
    skipped = 0
    errors = 0
    
    logger.info(f"Toplam {total} fatura bulundu.")
    
    for inv in invoices:
        result = update_invoice_stamp_card_data(inv.name)
        if result:
            updated += 1
        elif inv.name:
            skipped += 1
        else:
            errors += 1
    
    logger.info("=" * 80)
    logger.info("ÖZET:")
    logger.info(f"  Toplam: {total}")
    logger.info(f"  Güncellenen: {updated}")
    logger.info(f"  Atlanan: {skipped}")
    logger.info(f"  Hata: {errors}")
    logger.info("=" * 80)

def update_single_invoice(invoice_number):
    """Update a single invoice by invoice number"""
    logger.info("=" * 80)
    logger.info(f"FATURA GÜNCELLEME: {invoice_number}")
    logger.info("=" * 80)
    
    invoice = frappe.get_all(
        DOCTYPE_LIEFERANDO_INVOICE,
        fields=["name"],
        filters={"invoice_number": invoice_number},
        limit=1
    )
    
    if not invoice:
        logger.error(f"Fatura bulunamadı: {invoice_number}")
        return
    
    result = update_invoice_stamp_card_data(invoice[0].name)
    
    if result:
        logger.info(f"Fatura başarıyla güncellendi: {invoice_number}")
    else:
        logger.warning(f"Fatura güncellenemedi: {invoice_number}")

def update_single(invoice_number):
    """Update single invoice - for bench execute"""
    update_single_invoice(invoice_number)
    frappe.db.commit()

def update_all():
    """Update all invoices - for bench execute"""
    update_all_invoices()
    frappe.db.commit()

