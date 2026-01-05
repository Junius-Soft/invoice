# -*- coding: utf-8 -*-
# Copyright (c) 2025, Invoice
# Chrome PDF Generator - Headless Chrome kullanarak PDF oluşturma
# Print format HTML'ini birebir PDF'e çevirir

import frappe
from frappe import _
import os
import tempfile
from pathlib import Path


# Override'ın uygulanıp uygulanmadığını takip et
_override_applied = False

def override_weasyprint_download_pdf():
	"""WeasyPrint download_pdf endpoint'ini override et - Chrome PDF generator kullan"""
	global _override_applied
	
	# Eğer zaten override edilmişse, tekrar etme
	if _override_applied:
		return
	
	# Log'u hem console'a hem de file'a yaz
	print("🔧 override_weasyprint_download_pdf called")
	frappe.logger("invoice").info("🔧 override_weasyprint_download_pdf called")
	
	try:
		from frappe.utils.weasyprint import download_pdf as original_weasyprint_download_pdf
		from frappe.utils.print_format import download_pdf as original_print_format_download_pdf
	except Exception as e:
		frappe.logger("invoice").error(f"Failed to import download_pdf functions: {e}", exc_info=True)
		return
	
	def weasyprint_download_pdf_override(doctype, name, print_format, letterhead=None):
		"""Chrome PDF generator kullanarak PDF oluştur"""
		frappe.logger("invoice").info(f"🔧 weasyprint_download_pdf_override called: doctype={doctype}, name={name}, print_format={print_format}")
		# Print format'ı kontrol et
		try:
			pf = frappe.get_doc("Print Format", print_format)
			frappe.logger("invoice").info(f"🔧 Print format pdf_generator: {pf.pdf_generator}")
		except Exception as e:
			frappe.logger("invoice").error(f"Failed to get print format: {e}", exc_info=True)
			return original_weasyprint_download_pdf(doctype, name, print_format, letterhead)
		
		# Eğer pdf_generator chrome ise, Chrome PDF generator kullan
		if pf.pdf_generator == "chrome":
			frappe.logger("invoice").info(f"🔧 Using Chrome PDF generator for print format: {print_format}")
			# HTML'i al
			from frappe.utils.weasyprint import get_html
			html = get_html(doctype, name, print_format, letterhead)
			
			# Chrome PDF generator ile PDF oluştur
			pdf_bytes = chrome_pdf_generator(
				print_format=print_format,
				html=html,
				options=None,
				output=None,
				pdf_generator="chrome"
			)
			
			# Response'u ayarla
			frappe.local.response.filename = "{name}.pdf".format(name=name.replace(" ", "-").replace("/", "-"))
			frappe.local.response.filecontent = pdf_bytes
			frappe.local.response.type = "pdf"
			return
		
		# Değilse, orijinal WeasyPrint'i kullan
		return original_weasyprint_download_pdf(doctype, name, print_format, letterhead)
	
	def print_format_download_pdf_override(doctype, name, format=None, doc=None, no_letterhead=0, language=None, letterhead=None, pdf_generator=None):
		"""Print Format download_pdf endpoint'ini override et - Chrome PDF generator kullan"""
		# Print format'tan pdf_generator'ı al
		if format and not pdf_generator:
			try:
				pf = frappe.get_doc("Print Format", format)
				if pf.pdf_generator == "chrome":
					pdf_generator = "chrome"
			except Exception as e:
				frappe.logger("invoice").warning(f"Failed to get print format pdf_generator: {e}")
		
		# pdf_generator chrome ise, Chrome PDF generator kullan
		if pdf_generator == "chrome":
			frappe.logger("invoice").info(f"🔧 Using Chrome PDF generator for print format: {format}")
			# HTML'i al
			from frappe.www.printview import get_rendered_template
			doc_obj = doc or frappe.get_doc(doctype, name)
			if format:
				pf = frappe.get_doc("Print Format", format)
			else:
				pf = None
			html = get_rendered_template(
				doc_obj,
				print_format=pf,
				no_letterhead=no_letterhead,
				letterhead=letterhead
			)
			
			# Chrome PDF generator ile PDF oluştur
			pdf_bytes = chrome_pdf_generator(
				print_format=format,
				html=html,
				options=None,
				output=None,
				pdf_generator="chrome"
			)
			
			# Response'u ayarla
			frappe.local.response.filename = "{name}.pdf".format(name=name.replace(" ", "-").replace("/", "-"))
			frappe.local.response.filecontent = pdf_bytes
			frappe.local.response.type = "pdf"
			return
		
		# Değilse, orijinal print_format download_pdf'i kullan
		return original_print_format_download_pdf(doctype, name, format, doc, no_letterhead, language, letterhead, pdf_generator)
	
	# Decorator'ları uygula
	weasyprint_download_pdf_override = frappe.whitelist()(weasyprint_download_pdf_override)
	print_format_download_pdf_override = frappe.whitelist(allow_guest=True)(print_format_download_pdf_override)
	
	# Override'ları uygula
	frappe.utils.weasyprint.download_pdf = weasyprint_download_pdf_override
	frappe.utils.print_format.download_pdf = print_format_download_pdf_override
	_override_applied = True
	frappe.logger("invoice").info("✅ PDF download endpoints override applied - Chrome PDF generator will be used when pdf_generator=chrome")


def chrome_pdf_generator(print_format=None, html=None, options=None, output=None, pdf_generator=None):
	"""
	Chrome PDF Generator Hook Fonksiyonu
	Headless Chrome kullanarak PDF oluşturur
	"""
	if pdf_generator != "chrome":
		return None
	
	try:
		from playwright.sync_api import sync_playwright
	except ImportError:
		frappe.logger("invoice").error("Playwright not installed. Install with: pip install playwright && playwright install chromium")
		raise frappe.ValidationError(_("Playwright not installed. Please install it first."))
	
	frappe.logger("invoice").info(f"🔧 Chrome PDF Generator called for print format: {print_format}")
	
	# Base URL'i al
	base_url = frappe.utils.get_url()
	
	# Playwright ile PDF oluştur
	with sync_playwright() as p:
		# Chromium browser'ı başlat
		browser = p.chromium.launch(headless=True)
		
		# Context oluştur ve base URL'i ayarla
		context = browser.new_context(base_url=base_url)
		page = context.new_page()
		
		# HTML'i doğrudan set_content ile yükle
		# Base URL context'te ayarlandığı için CSS ve image'lar çalışacak
		page.set_content(html, wait_until="networkidle")
		
		# PDF seçeneklerini hazırla
		pdf_options = {
			"format": "A4",
			"print_background": True,
			"margin": {
				"top": "0mm",
				"right": "0mm",
				"bottom": "0mm",
				"left": "0mm"
			}
		}
		
		# Print format'tan margin ayarlarını al
		if print_format:
			try:
				pf = frappe.get_doc("Print Format", print_format)
				if pf.margin_top:
					pdf_options["margin"]["top"] = f"{pf.margin_top}mm"
				if pf.margin_right:
					pdf_options["margin"]["right"] = f"{pf.margin_right}mm"
				if pf.margin_bottom:
					pdf_options["margin"]["bottom"] = f"{pf.margin_bottom}mm"
				if pf.margin_left:
					pdf_options["margin"]["left"] = f"{pf.margin_left}mm"
				
				# Page size ayarı
				print_settings = frappe.get_doc("Print Settings")
				if print_settings.pdf_page_size:
					pdf_options["format"] = print_settings.pdf_page_size
			except Exception as e:
				frappe.logger("invoice").warning(f"Failed to get print format settings: {e}")
		
		# PDF oluştur
		pdf_bytes = page.pdf(**pdf_options)
		
		# Browser'ı kapat
		browser.close()
	
	frappe.logger("invoice").info("✅ Chrome PDF generated successfully")
	
	# Output varsa, PDF'i output'a ekle
	if output:
		from pypdf import PdfReader
		from io import BytesIO
		reader = PdfReader(BytesIO(pdf_bytes))
		output.append_pages_from_reader(reader)
		return output
	
	# PDF bytes'ı döndür
	return pdf_bytes

