# -*- coding: utf-8 -*-
# Copyright (c) 2025, Invoice
# WeasyPrint Override - Custom format HTML'i kullanması için

import frappe
from frappe import _
import os


def override_weasyprint_get_main_html():
	"""WeasyPrint'in get_main_html fonksiyonunu override et - custom format HTML'i kullan"""
	# Lazy import - sınıf henüz yüklenmemiş olabilir
	try:
		from frappe.utils.weasyprint import PrintFormatGenerator
	except ImportError:
		frappe.logger("invoice").warning("PrintFormatGenerator not found, skipping override")
		return
	
	from frappe.www.printview import get_print_format
	
	# Eğer zaten override edilmişse, tekrar etme
	if hasattr(PrintFormatGenerator.get_main_html, '_overridden_by_invoice'):
		frappe.logger("invoice").debug("WeasyPrint override already applied")
		return
	
	# Orijinal fonksiyonu sakla
	original_get_main_html = PrintFormatGenerator.get_main_html
	
	# DEBUG: Override'ın uygulanacağını logla
	frappe.logger("invoice").info("🔧 Applying WeasyPrint get_main_html override...")
	
	def get_main_html_override(self):
		"""Custom format HTML'i kullan - print format HTML dosyasını direkt kullan"""
		# DEBUG: Override'ın çağrıldığını logla
		frappe.logger("invoice").info(f"🔧 get_main_html_override called for print format: {self.print_format.name}, custom_format: {self.print_format.custom_format}")
		
		# Eğer custom_format ise, custom HTML'i kullan
		# format_data kontrolü kaldırıldı - custom_format varsa HTML kullan
		if self.print_format.custom_format:
			try:
				# Custom HTML'i al - get_print_format fonksiyonunu kullan
				# Bu fonksiyon print format HTML dosyasını okur
				html_content = get_print_format(self.doc.doctype, self.print_format)
				
				if html_content:
					# Jinja template olarak render et
					from frappe.utils.jinja import get_jenv
					jenv = get_jenv()
					template = jenv.from_string(html_content)
					
					# Context'i hazırla - print format HTML'inde kullanılan tüm değişkenler
					# Print format HTML'i zaten tam bir HTML dosyası (DOCTYPE, html, head, body var)
					# Bu yüzden sadece doc ve diğer context değişkenlerini ekle
					render_context = {
						"doc": self.doc,
						"frappe": frappe,
						"_": _,
					}
					
					# Frappe utils'leri de ekle (format_date, format_currency vb. için)
					import frappe.utils
					render_context["utils"] = frappe.utils
					
					# Template'i render et
					rendered_html = template.render(**render_context)
					
					frappe.logger("invoice").info(f"✅ Using custom HTML for print format: {self.print_format.name}")
					return rendered_html
				else:
					frappe.logger("invoice").warning(f"No HTML content found for print format: {self.print_format.name}")
			except Exception as e:
				frappe.logger("invoice").error(f"Failed to use custom HTML, falling back to original: {e}", exc_info=True)
				import traceback
				frappe.logger("invoice").error(traceback.format_exc())
				# Hata olursa orijinal fonksiyonu kullan
				return original_get_main_html(self)
		
		# Custom format değilse, orijinal fonksiyonu kullan
		return original_get_main_html(self)
	
	# Override'ı uygula
	PrintFormatGenerator.get_main_html = get_main_html_override
	# Override marker ekle
	PrintFormatGenerator.get_main_html._overridden_by_invoice = True
	
	frappe.logger("invoice").info("✅ WeasyPrint get_main_html override applied - custom format HTML will be used")


def override_weasyprint_render_pdf():
	"""WeasyPrint'in render_pdf metodunu override et - custom format HTML'i kullan"""
	try:
		from frappe.utils.weasyprint import PrintFormatGenerator
		from frappe.www.printview import get_print_format
		from weasyprint import HTML
	except ImportError as e:
		frappe.logger("invoice").warning(f"Failed to import WeasyPrint modules: {e}")
		return
	
	# Eğer zaten override edilmişse, tekrar etme
	if hasattr(PrintFormatGenerator.render_pdf, '_overridden_by_invoice'):
		frappe.logger("invoice").debug("WeasyPrint render_pdf override already applied")
		return
	
	# Orijinal render_pdf metodunu sakla
	original_render_pdf = PrintFormatGenerator.render_pdf
	
	def render_pdf_override(self):
		"""Custom format HTML'i kullanarak PDF oluştur"""
		# Eğer custom_format ise, custom HTML'i kullan
		if self.print_format.custom_format:
			try:
				frappe.logger("invoice").info(f"🔧 render_pdf_override called for print format: {self.print_format.name}")
				
				# Custom HTML'i al
				html_content = get_print_format(self.doc.doctype, self.print_format)
				
				if html_content:
					# Jinja template olarak render et
					from frappe.utils.jinja import get_jenv
					jenv = get_jenv()
					template = jenv.from_string(html_content)
					
					# Context'i hazırla
					render_context = {
						"doc": self.doc,
						"frappe": frappe,
						"_": _,
					}
					import frappe.utils
					render_context["utils"] = frappe.utils
					
					# Template'i render et
					rendered_html = template.render(**render_context)
					
					frappe.logger("invoice").info(f"✅ Using custom HTML for WeasyPrint PDF: {self.print_format.name}")
					
					# WeasyPrint ile PDF oluştur
					HTML, _CSS = frappe.utils.weasyprint.import_weasyprint()
					html = HTML(string=rendered_html, base_url=self.base_url)
					pdf = html.write_pdf()
					
					return pdf
			except Exception as e:
				frappe.logger("invoice").error(f"Failed to use custom HTML in render_pdf, falling back to original: {e}", exc_info=True)
				import traceback
				frappe.logger("invoice").error(traceback.format_exc())
		
		# Custom format değilse veya hata olursa, orijinal metodu kullan
		return original_render_pdf(self)
	
	# Override'ı uygula
	PrintFormatGenerator.render_pdf = render_pdf_override
	PrintFormatGenerator.render_pdf._overridden_by_invoice = True
	
	frappe.logger("invoice").info("✅ WeasyPrint render_pdf override applied")


def apply_weasyprint_override():
	"""WeasyPrint override'ını uygula - before_request hook'u için"""
	# DEBUG: Override'ın çağrıldığını logla
	frappe.logger("invoice").info("🔧 apply_weasyprint_override called")
	
	try:
		override_weasyprint_get_main_html()
		override_weasyprint_render_pdf()
		frappe.logger("invoice").info("✅ WeasyPrint override applied successfully")
	except Exception as e:
		frappe.logger("invoice").error(f"❌ Failed to apply WeasyPrint override: {e}", exc_info=True)
		import traceback
		frappe.logger("invoice").error(traceback.format_exc())

