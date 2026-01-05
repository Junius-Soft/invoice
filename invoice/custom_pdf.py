# -*- coding: utf-8 -*-
# Copyright (c) 2025, Invoice
# PDF Override - wkhtmltopdf network sorununu çözer ve CSS/image inline eder

import base64
import mimetypes
import os
from urllib.parse import parse_qs, urlparse

import frappe
from bs4 import BeautifulSoup
from frappe.core.doctype.file.utils import find_file_by_url
from frappe.utils import get_bench_path, get_assets_json


def inline_css_files(html) -> str:
	"""Convert external CSS links to inline styles to avoid network errors with wkhtmltopdf
	CSS'leri doğru sırada inline eder: önce external CSS'ler, print format'ın kendi CSS'i en sonda kalır
	"""
	import sys
	soup = BeautifulSoup(html, "html.parser")
	head = soup.find("head")
	if not head:
		print("[INVOICE-PDF] No <head> tag found in HTML", file=sys.stderr)
		sys.stderr.flush()
		return html
	
	# Get assets mapping for bundled files
	assets_json = get_assets_json()
	
	# Find all external stylesheet links
	links_to_replace = []
	css_links_found = 0
	for link in head.find_all("link", rel="stylesheet"):
		css_links_found += 1
		href = link.get("href", "")
		if not href:
			continue
		
		# Skip data URIs
		if href.startswith("data:"):
			continue
		
		# Extract path from URL if it's a full URL
		if href.startswith(("http://", "https://")):
			parsed = urlparse(href)
			href = parsed.path
		
		# Remove leading slash and query params
		href_clean = href.lstrip("/").split("?")[0]
		
		# Try to find the CSS file
		css_content = None
		possible_paths = []
		
		# Check if it's a bundled asset
		if ".bundle." in href_clean:
			# Try to get the actual bundled file path
			bundled_path = assets_json.get(href_clean)
			if bundled_path:
				possible_paths.append(bundled_path.lstrip("/"))
		
		# Add standard paths
		if href_clean.startswith("assets/"):
			possible_paths.append(href_clean)
			possible_paths.append(os.path.join(frappe.local.sites_path, href_clean))
		else:
			possible_paths.append(href_clean)
			possible_paths.append(os.path.join(frappe.local.sites_path, "assets", href_clean))
			# Try in app public folders
			for app in frappe.get_installed_apps():
				try:
					app_path = frappe.get_app_path(app, "public", href_clean)
					possible_paths.append(app_path)
				except Exception:
					pass
		
		# Try to read the CSS file
		for path in possible_paths:
			# Handle absolute paths
			if not os.path.isabs(path):
				# Try sites path first
				full_path = os.path.join(frappe.local.sites_path, path)
				if not os.path.exists(full_path):
					# Try bench root
					full_path = os.path.join(get_bench_path(), path)
			else:
				full_path = path
			
			if os.path.exists(full_path) and os.path.isfile(full_path):
				try:
					css_content = frappe.read_file(full_path)
					frappe.logger("invoice").debug(f"Inlined CSS file: {full_path}")
					break
				except Exception:
					frappe.logger("pdf").debug(f"Failed to read CSS file: {full_path}", exc_info=True)
		
		if css_content:
			# Create inline style tag
			style_tag = soup.new_tag("style")
			style_tag.string = css_content
			links_to_replace.append((link, style_tag))
		else:
			frappe.logger("invoice").warning(f"Could not find CSS file: {href_clean}")
	
	# ÖNEMLİ: External CSS'leri en başa ekle, print format'ın kendi CSS'i (template içindeki <style> tag'i) en sonda kalmalı
	# Mevcut <style> tag'lerini bul (print format'ın kendi CSS'i)
	existing_styles = head.find_all("style")
	
	debug_info = f"Found {len(existing_styles)} existing style tags, {len(links_to_replace)} CSS links to inline, {css_links_found} total CSS links found"
	frappe.logger("invoice").debug(debug_info)
	print(f"[INVOICE-PDF] {debug_info}", file=sys.stderr)
	sys.stderr.flush()
	
	# External CSS'leri en başa ekle
	for i, (link, style_tag) in enumerate(links_to_replace):
		# Link'i kaldır
		link.decompose()
		# Style'ı en başa ekle (mevcut style tag'lerinden önce)
		if existing_styles:
			existing_styles[0].insert_before(style_tag)
		else:
			# Eğer hiç style tag'i yoksa, head'in sonuna ekle
			head.append(style_tag)
		print(f"[INVOICE-PDF] Inlined CSS file {i+1}/{len(links_to_replace)}", file=sys.stderr)
		sys.stderr.flush()
	
	if len(links_to_replace) == 0:
		print("[INVOICE-PDF] ⚠️ No CSS files were inlined (no CSS links found or files not readable)", file=sys.stderr)
		sys.stderr.flush()
	
	return str(soup)


def _get_base64_image_from_path(src):
	"""Return base64 version of image from file path (for public images like logos)"""
	try:
		parsed_url = urlparse(src)
		path = parsed_url.path
		query = parse_qs(parsed_url.query)
		
		# Check if it's an image
		mime_type = mimetypes.guess_type(path)[0]
		if mime_type is None or not mime_type.startswith("image/"):
			return None
		
		# Try to find file in database first
		filename = (query.get("fid") and query["fid"][0]) or None
		file = find_file_by_url(path, name=filename)
		if file:
			# File found in database, use it
			b64_encoded_image = base64.b64encode(file.get_content()).decode()
			return f"data:{mime_type};base64,{b64_encoded_image}"
		
		# Try to read from file system
		path_clean = path.lstrip("/")
		possible_paths = [
			os.path.join(frappe.local.sites_path, path_clean),
			os.path.join(frappe.local.sites_path, "public", path_clean),
			os.path.join(get_bench_path(), "sites", path_clean),
		]
		
		# Also try with files/ prefix
		if not path_clean.startswith("files/"):
			possible_paths.extend([
				os.path.join(frappe.local.sites_path, "public", "files", path_clean),
				os.path.join(frappe.local.sites_path, "files", path_clean),
			])
		
		for file_path in possible_paths:
			if os.path.exists(file_path) and os.path.isfile(file_path):
				try:
					with open(file_path, "rb") as f:
						image_content = f.read()
					b64_encoded_image = base64.b64encode(image_content).decode()
					return f"data:{mime_type};base64,{b64_encoded_image}"
				except Exception:
					frappe.logger("pdf").debug(f"Failed to read image file: {file_path}", exc_info=True)
		
		return None
	except Exception:
		frappe.logger("pdf").debug("Failed to convert image from path to base64", exc_info=True)
		return None


def inline_all_images(html) -> str:
	"""Convert all images (both private and public) to base64 to avoid network errors"""
	from frappe.utils.pdf import _get_base64_image
	
	soup = BeautifulSoup(html, "html.parser")
	for img in soup.find_all("img"):
		src = img.get("src", "")
		if not src:
			continue
		
		# Skip if already base64
		if src.startswith("data:"):
			continue
		
		# Try to get base64 version (private images first, then public)
		if b64 := _get_base64_image(src):
			img["src"] = b64
		elif b64 := _get_base64_image_from_path(src):
			img["src"] = b64
	return str(soup)


def convert_grid_to_float_layout(html):
	"""wkhtmltopdf CSS Grid desteği olmadığı için grid layout'ları float-based layout'a dönüştür
	Bu yaklaşım print format'taki hizalamayı korur"""
	import re
	from bs4 import BeautifulSoup
	import sys
	
	soup = BeautifulSoup(html, "html.parser")
	
	# Tüm style tag'lerini bul
	style_tags = soup.find_all("style")
	
	# Spesifik grid class'ları ve column tanımları
	# Bu değerler print format HTML'indeki grid-template-columns değerlerinden alınmıştır
	grid_configs = {
		'service-fee-row': {'columns': ['1fr', '18px', '70px'], 'gap': 8},
		'amount-row': {'columns': ['1fr', '18px', '70px'], 'gap': 8},
		'payout-section': {'columns': ['1fr', '18px', '80px'], 'gap': 8},
		'supplier-details': {'columns': ['1fr', '1.15fr', '1.6fr', '1.3fr'], 'gap': 10},
		'invoice-details-inline': {'columns': ['1fr', '1fr'], 'gap': 0},
	}
	
	for style_tag in style_tags:
		if not style_tag.string:
			continue
		
		css_content = style_tag.string
		original_css = css_content
		
		# Spesifik grid class'ları için float-based layout kuralları ekle
		additional_rules = []
		
		for class_name, config in grid_configs.items():
			columns = config['columns']
			gap = config['gap']
			
			# Grid container'ı block yap ve clearfix ekle
			container_rule = f".{class_name} {{ display: block !important; width: 100% !important; overflow: hidden !important; }}"
			container_rule += f"\n.{class_name}::after {{ content: ''; display: table; clear: both; }}"
			
			# Fixed width'leri hesapla
			fixed_widths = []
			fr_values = []
			for col in columns:
				if 'fr' in col:
					fr_val = float(re.search(r'[\d.]+', col).group() if re.search(r'[\d.]+', col) else '1')
					fr_values.append(fr_val)
					fixed_widths.append(None)
				else:
					match = re.search(r'[\d.]+', col)
					if match:
						fixed_widths.append(float(match.group()))
					else:
						fixed_widths.append(None)
					fr_values.append(None)
			
			# Toplam fixed width ve fr değerlerini hesapla
			total_fixed = sum(fw for fw in fixed_widths if fw is not None)
			total_fr = sum(fr for fr in fr_values if fr is not None)
			
			# Gap'ları hesaba kat (n-1 gap, n column)
			total_gaps = gap * (len(columns) - 1)
			
			# Her column için float ve width ekle
			child_rules = []
			for i, (col_value, fw, fr) in enumerate(zip(columns, fixed_widths, fr_values), 1):
				if fw is not None:
					# Sabit genişlik
					width = col_value
				elif fr is not None:
					# fr değeri - kalan alanı orantılı dağıt
					if total_fr > 0:
						if total_fixed > 0:
							available = f'calc(100% - {total_fixed}px - {total_gaps}px)'
						else:
							available = f'calc(100% - {total_gaps}px)'
						
						fr_cols = [fr for fr in fr_values if fr is not None]
						if len(fr_cols) == 1:
							width = available
						else:
							width = f'calc({available} * {fr} / {total_fr})'
					else:
						width = 'auto'
				else:
					width = 'auto'
				
				# Margin-right ekle (gap yerine) - son child hariç
				margin_right = f'{gap}px' if i < len(columns) else '0'
				
				child_rule = f".{class_name} > *:nth-child({i}) {{ float: left !important; width: {width} !important; margin-right: {margin_right} !important; }}"
				child_rules.append(child_rule)
			
			additional_rules.append(container_rule)
			additional_rules.extend(child_rules)
		
		# Genel grid dönüştürmesi: display: grid -> display: block
		css_content = re.sub(
			r'display\s*:\s*grid',
			'display: block',
			css_content,
			flags=re.IGNORECASE
		)
		
		# grid-template-columns'u kaldır
		css_content = re.sub(r'grid-template-columns\s*:\s*[^;]+;?\s*', '', css_content, flags=re.IGNORECASE)
		# column-gap'ı kaldır
		css_content = re.sub(r'column-gap\s*:\s*[^;]+;?\s*', '', css_content, flags=re.IGNORECASE)
		# align-items'i kaldır (float için gerekli değil)
		css_content = re.sub(r'align-items\s*:\s*[^;]+;?\s*', '', css_content, flags=re.IGNORECASE)
		
		# Ek kuralları ekle
		if additional_rules:
			css_content += "\n/* Grid to float conversion rules for wkhtmltopdf */\n" + "\n".join(additional_rules)
		
		if css_content != original_css:
			style_tag.string = css_content
			print(f"[INVOICE-PDF] Converted CSS Grid to float layout for {len(grid_configs)} grid classes", file=sys.stderr)
			sys.stderr.flush()
	
	# HTML'deki grid container'ları da float'a dönüştür (fallback)
	grid_classes = list(grid_configs.keys())
	for element in soup.find_all(class_=lambda x: x and any(cls in str(x) for cls in grid_classes)):
		classes = element.get('class', [])
		matching_class = next((cls for cls in classes if cls in grid_classes), None)
		if matching_class:
			config = grid_configs[matching_class]
			gap = config['gap']
			
			# Container'ı block yap
			current_style = element.get('style', '')
			if 'display: block' not in current_style and 'display: grid' not in current_style:
				element['style'] = (current_style + '; display: block !important; width: 100% !important; overflow: hidden !important;').lstrip('; ')
			
			# Child elementleri float yap
			children = list(element.find_all(recursive=False))
			columns = config['columns']
			for i, child in enumerate(children):
				if i < len(columns):
					child_style = child.get('style', '')
					if 'float: left' not in child_style:
						margin_right = gap if i < len(columns) - 1 else 0
						child['style'] = (child_style + f'; float: left !important; margin-right: {margin_right}px !important;').lstrip('; ')
	
	return str(soup)


def extract_page_margins_from_css(html):
	"""Print format HTML'inden @page margin ayarlarını çıkar"""
	import re
	from bs4 import BeautifulSoup
	
	soup = BeautifulSoup(html, "html.parser")
	
	# Tüm style tag'lerini bul
	style_tags = soup.find_all("style")
	
	margins = {}
	
	for style_tag in style_tags:
		if not style_tag.string:
			continue
		
		# @page kuralını ara
		page_rule_match = re.search(r'@page\s*\{([^}]+)\}', style_tag.string, re.IGNORECASE | re.DOTALL)
		if not page_rule_match:
			continue
		
		page_rules = page_rule_match.group(1)
		
		# margin ayarlarını bul
		# margin: 10mm 12mm 12mm 12mm; veya margin-top: 10mm; gibi
		margin_match = re.search(r'margin\s*:\s*([^;]+)', page_rules, re.IGNORECASE)
		if margin_match:
			margin_values = margin_match.group(1).strip().split()
			if len(margin_values) == 4:
				# margin: top right bottom left
				margins["margin-top"] = margin_values[0]
				margins["margin-right"] = margin_values[1]
				margins["margin-bottom"] = margin_values[2]
				margins["margin-left"] = margin_values[3]
			elif len(margin_values) == 2:
				# margin: top/bottom left/right
				margins["margin-top"] = margin_values[0]
				margins["margin-bottom"] = margin_values[0]
				margins["margin-left"] = margin_values[1]
				margins["margin-right"] = margin_values[1]
			elif len(margin_values) == 1:
				# margin: all
				margins["margin-top"] = margin_values[0]
				margins["margin-right"] = margin_values[0]
				margins["margin-bottom"] = margin_values[0]
				margins["margin-left"] = margin_values[0]
		
		# Ayrı ayrı margin özelliklerini de kontrol et
		for margin_type in ["margin-top", "margin-right", "margin-bottom", "margin-left"]:
			specific_match = re.search(rf'{margin_type}\s*:\s*([^;]+)', page_rules, re.IGNORECASE)
			if specific_match:
				margins[margin_type] = specific_match.group(1).strip()
	
	return margins


def get_pdf_override(html, options=None, output=None):
	"""Override frappe.utils.pdf.get_pdf to inline CSS and images"""
	from frappe.utils.pdf import scrub_urls
	from frappe.utils.pdf import get_file_data_from_writer, cleanup, read_options_from_html, get_cookie_options
	from pypdf import PdfWriter, PdfReader
	from io import BytesIO
	import pdfkit
	from packaging.version import Version
	from frappe.utils.pdf import get_wkhtmltopdf_version, PDF_CONTENT_ERRORS
	from frappe import _
	import sys
	
	# DEBUG: Log that override is being called - hem logger hem console'a yaz
	debug_msg = "🔧 get_pdf_override called - inlining CSS and images"
	frappe.logger("invoice").info(debug_msg)
	print(f"[INVOICE-PDF] {debug_msg}", file=sys.stderr)
	sys.stderr.flush()
	
	# ÖNEMLİ: Önce CSS'leri inline et (read_options_from_html'den ÖNCE)
	# Böylece print format'ın kendi CSS'i (template içindeki <style> tag'i) en sonda kalır
	print("[INVOICE-PDF] Starting CSS inline process...", file=sys.stderr)
	sys.stderr.flush()
	html = inline_css_files(html)
	print("[INVOICE-PDF] CSS inline process completed", file=sys.stderr)
	sys.stderr.flush()
	
	# Print format HTML'inden @page margin ayarlarını çıkar
	print("[INVOICE-PDF] Extracting @page margins from CSS...", file=sys.stderr)
	sys.stderr.flush()
	page_margins = extract_page_margins_from_css(html)
	if page_margins:
		print(f"[INVOICE-PDF] Found @page margins: {page_margins}", file=sys.stderr)
		sys.stderr.flush()
	
	# Şimdi scrub_urls yap
	html = scrub_urls(html)
	
	# Prepare options manually (skip inline_private_images, we'll do it ourselves)
	if not options:
		options = {}
	
	options.update({
		"print-media-type": None,
		"background": None,
		"images": None,
		"quiet": None,
		"encoding": "UTF-8",
	})
	
	# ÖNEMLİ: Print format HTML'inden çıkarılan margin ayarlarını kullan
	# Eğer @page margin ayarları bulunduysa, bunları kullan
	if page_margins:
		for margin_type, margin_value in page_margins.items():
			if not options.get(margin_type):
				options[margin_type] = margin_value
				print(f"[INVOICE-PDF] Applied {margin_type}: {margin_value}", file=sys.stderr)
		sys.stderr.flush()
	else:
		# Fallback: Varsayılan margin ayarları
		if not options.get("margin-right"):
			options["margin-right"] = "15mm"
		if not options.get("margin-left"):
			options["margin-left"] = "15mm"
	
	# Read options from HTML (bu HTML'i parse eder ve değiştirir)
	# NOT: read_options_from_html HTML'i parse eder ama CSS sıralamasını bozmaz
	html, html_options = read_options_from_html(html)
	# HTML'den gelen options'ları güncelle, ama @page margin'lerini koru
	for key, value in (html_options or {}).items():
		if key.startswith("margin-") and key in page_margins:
			# @page margin'lerini koru, HTML options'dan gelen margin'leri kullanma
			continue
		options[key] = value
	
	# cookies
	options.update(get_cookie_options())
	
	# Inline all images (private and public) - our custom version
	html = inline_all_images(html)
	
	# page size
	pdf_page_size = (
		options.get("page-size") or frappe.db.get_single_value("Print Settings", "pdf_page_size") or "A4"
	)
	
	if pdf_page_size == "Custom":
		options["page-height"] = options.get("page-height") or frappe.db.get_single_value(
			"Print Settings", "pdf_page_height"
		)
		options["page-width"] = options.get("page-width") or frappe.db.get_single_value(
			"Print Settings", "pdf_page_width"
		)
	else:
		options["page-size"] = pdf_page_size
	
	options.update({"disable-javascript": "", "disable-local-file-access": ""})
	
	filedata = ""
	if Version(get_wkhtmltopdf_version()) > Version("0.12.3"):
		options.update({"disable-smart-shrinking": ""})
	
	try:
		# Set filename property to false, so no file is actually created
		filedata = pdfkit.from_string(html, options=options or {}, verbose=True)
		
		# create in-memory binary streams from filedata and create a PdfReader object
		reader = PdfReader(BytesIO(filedata))
	except Exception as e:
		if any([error in str(e) for error in PDF_CONTENT_ERRORS]):
			if not filedata:
				frappe.throw(_("PDF generation failed because of broken image links"))
			
			# allow pdfs with missing images if file got created
			if output:
				output.append_pages_from_reader(reader)
		else:
			raise
	finally:
		cleanup(options)
	
	if "password" in options:
		password = options["password"]
	
	if output:
		output.append_pages_from_reader(reader)
		return output
	
	writer = PdfWriter()
	writer.append_pages_from_reader(reader)
	
	if "password" in options:
		writer.encrypt(password)
	
	filedata = get_file_data_from_writer(writer)
	
	return filedata


_patched = False

def patch_pdf_functions(*args, **kwargs):
	"""Monkey patch frappe.utils.pdf functions - sadece bir kez uygula
	Bu fonksiyon hem boot_session hem de before_request hook'larından çağrılabilir
	"""
	global _patched
	import sys
	import traceback
	
	if _patched:
		msg = "[INVOICE-PDF] Patch already applied, skipping..."
		frappe.logger("invoice").debug(msg)
		print(msg, file=sys.stderr)
		sys.stderr.flush()
		return
	
	try:
		# ÖNEMLİ: get_print fonksiyonunu da patch et
		# Çünkü get_print fonksiyonu get_pdf'i import ediyor ve bu import patch'ten önce yapılıyor olabilir
		import frappe.utils.print_utils as print_utils_module
		import frappe.utils.pdf as pdf_module
		
		# Önce get_pdf'i patch et
		original_get_pdf = pdf_module.get_pdf
		pdf_module.get_pdf = get_pdf_override
		
		# get_print fonksiyonunu da patch et - get_pdf import'unu override et
		# get_print fonksiyonu içinde "from frappe.utils.pdf import get_pdf" var
		# Bu import'u override etmek için get_print'in içindeki get_pdf referansını değiştirmeliyiz
		# Ama bu zor, bunun yerine get_print'i wrapper ile sarmalayabiliriz
		
		_patched = True
		
		# Log to both invoice logger and print to console for debugging
		success_msg = "✅ PDF functions patched for invoice app"
		frappe.logger("invoice").info(success_msg)
		print(f"[INVOICE-PDF] {success_msg}", file=sys.stderr)
		sys.stderr.flush()
		
		# DEBUG: Verify patch was applied
		if pdf_module.get_pdf == get_pdf_override:
			verify_msg = "✅ Patch verified: get_pdf is now get_pdf_override"
			frappe.logger("invoice").info(verify_msg)
			print(f"[INVOICE-PDF] {verify_msg}", file=sys.stderr)
			sys.stderr.flush()
		else:
			error_msg = "❌ Patch failed: get_pdf is still original function"
			frappe.logger("invoice").error(error_msg)
			print(f"[INVOICE-PDF] {error_msg}", file=sys.stderr)
			sys.stderr.flush()
			
	except Exception as e:
		# Log error but don't prevent app from loading
		error_msg = f"❌ Failed to patch PDF functions: {e}"
		traceback_str = traceback.format_exc()
		frappe.logger("invoice").error(f"{error_msg}\n{traceback_str}", exc_info=True)
		print(f"[INVOICE-PDF] {error_msg}", file=sys.stderr)
		print(f"[INVOICE-PDF] Traceback:\n{traceback_str}", file=sys.stderr)
		sys.stderr.flush()


def boot_session_with_patch(bootinfo):
	"""boot_session hook'u için wrapper - patch'i uygula ve bootinfo'yu döndür"""
	import sys
	
	# Patch'i uygula
	patch_pdf_functions()
	
	# bootinfo'yu değiştirmeden döndür
	return bootinfo


def get_print_override_full(
	doctype=None,
	name=None,
	print_format=None,
	style=None,
	as_pdf=False,
	doc=None,
	output=None,
	no_letterhead=0,
	password=None,
	pdf_options=None,
	letterhead=None,
	pdf_generator=None,
):
	"""Tamamen override edilmiş get_print - get_pdf_override kullanır"""
	import sys
	import copy
	from frappe.website.serve import get_response_without_exception_handling
	
	# Patch'i uygula (eğer uygulanmadıysa)
	patch_pdf_functions()
	
	# DEBUG: Fonksiyonun çağrıldığını logla
	debug_msg = f"🔧 get_print_override_full called - doctype={doctype}, name={name}, as_pdf={as_pdf}"
	frappe.logger("invoice").info(debug_msg)
	print(f"[INVOICE-PDF] {debug_msg}", file=sys.stderr)
	sys.stderr.flush()
	
	local = frappe.local
	if "pdf_generator" not in local.form_dict:
		# if arg is passed, use that, else get setting from print format
		if pdf_generator is None:
			pdf_generator = (
				frappe.get_cached_value("Print Format", print_format, "pdf_generator") or "wkhtmltopdf"
			)
		local.form_dict.pdf_generator = pdf_generator

	original_form_dict = copy.deepcopy(local.form_dict)
	try:
		local.form_dict.doctype = doctype
		local.form_dict.name = name
		local.form_dict.format = print_format
		local.form_dict.style = style
		local.form_dict.doc = doc
		local.form_dict.no_letterhead = no_letterhead
		local.form_dict.letterhead = letterhead

		pdf_options = pdf_options or {}
		if password:
			pdf_options["password"] = password

		response = get_response_without_exception_handling("printview", 200)
		html = str(response.data, "utf-8")
	finally:
		local.form_dict = original_form_dict

	if not as_pdf:
		return html

	if local.form_dict.pdf_generator != "wkhtmltopdf":
		hook_func = frappe.get_hooks("pdf_generator")
		for hook in hook_func:
			"""
			check pdf_generator value in your hook function.
			if it matches run and return pdf else return None
			"""
			pdf = frappe.call(
				hook,
				print_format=print_format,
				html=html,
				options=pdf_options,
				output=output,
				pdf_generator=local.form_dict.pdf_generator,
			)
			# if hook returns a value, assume it was the correct pdf_generator and return it
			if pdf:
				return pdf

	for hook in frappe.get_hooks("on_print_pdf"):
		frappe.call(hook, doctype=doctype, name=name, print_format=print_format)

	# ÖNEMLİ: get_pdf yerine get_pdf_override kullan
	return get_pdf_override(html, options=pdf_options, output=output)


def override_get_print():
	"""frappe.utils.print_utils.get_print fonksiyonunu tamamen override et"""
	import sys
	
	# ÖNEMLİ: Önce patch_pdf_functions'ı çağır (get_pdf override'ını uygula)
	patch_pdf_functions()
	
	# get_print'i override et - hem print_utils_module hem de frappe modülünde
	import frappe.utils.print_utils as print_utils_module
	print_utils_module.get_print = get_print_override_full
	
	# ÖNEMLİ: frappe.get_print de override et (frappe.__init__.py'de import edilmiş)
	import frappe as frappe_module
	frappe_module.get_print = get_print_override_full
	
	# DEBUG: Override'ın uygulandığını doğrula
	if frappe_module.get_print == get_print_override_full:
		verify_msg = "✅ frappe.get_print override verified"
		frappe.logger("invoice").info(verify_msg)
		print(f"[INVOICE-PDF] {verify_msg}", file=sys.stderr)
		sys.stderr.flush()
	else:
		error_msg = "❌ frappe.get_print override FAILED"
		frappe.logger("invoice").error(error_msg)
		print(f"[INVOICE-PDF] {error_msg}", file=sys.stderr)
		sys.stderr.flush()
	
	frappe.logger("invoice").info("✅ get_print function completely overridden (both print_utils and frappe module)")
	print("[INVOICE-PDF] ✅ get_print function completely overridden (both print_utils and frappe module)", file=sys.stderr)
	sys.stderr.flush()

