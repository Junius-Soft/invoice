"""
Otomatik email sync için scheduled tasks
"""

import frappe

logger = frappe.logger("invoice.email_tasks", allow_site=frappe.local.site)

def sync_gmail_invoices():
    """
    Her 5 dakikada bir Gmail'den email'leri çeker
    Cron: */5 * * * * (her 5 dakika)
    """
    try:
        logger.info(f"Email sync başlatılıyor... {frappe.utils.now()}")
        
        # Tüm aktif Email Account'ları al
        email_accounts = frappe.get_all("Email Account",
            filters={
                "enable_incoming": 1  # Sadece gelen email aktif olan hesapları al
            },
            fields=["name", "email_id"]
        )
        
        if not email_accounts:
            logger.warning("Aktif Email Account bulunamadı")
            return
        
        # Her hesap için email çek
        for account in email_accounts:
            try:
                logger.info(f"Email çekiliyor: {account.email_id} ({account.name})")
                
                email_doc = frappe.get_doc("Email Account", account.name)
                
                # Email'leri çek
                email_doc.receive()
                
                logger.info(f"{account.email_id} için email'ler çekildi")
                
            except Exception as e:
                logger.error(f"{account.name} hatası: {str(e)}")
                frappe.log_error(
                    title=f"Email Sync Error - {account.name}",
                    message=str(e)
                )
        
        frappe.db.commit()
        logger.info(f"Email sync tamamlandı! {frappe.utils.now()}")
        
    except Exception as e:
        logger.error(f"Genel hata: {str(e)}")
        frappe.log_error(
            title="Scheduler Email Sync Error",
            message=str(e)
        )
