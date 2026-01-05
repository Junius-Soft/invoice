import frappe
import json
import os
import re

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None

logger = frappe.logger("invoice.ai_validation", allow_site=frappe.local.site)

def repair_json(json_string):
    """
    JSON string'i düzeltmeye çalış - basit hataları düzelt
    """
    try:
        # Önce normal parse dene
        return json.loads(json_string)
    except json.JSONDecodeError:
        pass
    
    # JSON repair işlemleri
    repaired = json_string
    
    # 1. Trailing comma'ları kaldır (object/array sonunda)
    repaired = re.sub(r',(\s*[}\]])', r'\1', repaired)
    
    # 2. JSON block'unu izole et (ilk { ile son } arası)
    first_brace = repaired.find('{')
    last_brace = repaired.rfind('}')
    if first_brace >= 0 and last_brace > first_brace:
        repaired = repaired[first_brace:last_brace + 1]
    
    # Tekrar parse dene
    try:
        return json.loads(repaired)
    except json.JSONDecodeError:
        # Son çare: None döndür
        return None

def get_openai_client():
    """OpenAI client oluştur"""
    if OpenAI is None:
        frappe.throw("OpenAI paketi yüklü değil. Lütfen 'pip install openai' komutu ile yükleyin.")
    
    api_key = frappe.conf.get("openai_api_key") or os.getenv("OPENAI_API_KEY")

    if not api_key:
        frappe.throw("OpenAI API key bulunamadı. Lütfen 'openai_api_key' site config'e ekleyin veya OPENAI_API_KEY environment variable'ı ayarlayın.")
    return OpenAI(api_key=api_key)

def prepare_invoice_data_for_ai(invoice_doc):
    """Invoice DocType verilerini AI'ya göndermek için hazırla"""
    doctype = invoice_doc.doctype
    data = {}
    meta = frappe.get_meta(doctype)
    
    default_only_fields = ['supplier_email', 'supplier_phone']  
    
    for field in meta.fields:
        fieldname = field.fieldname
        if fieldname in ['name', 'doctype', 'owner', 'creation', 'modified', 'modified_by']:
            continue
        if field.fieldtype in ['Section Break', 'Column Break', 'Tab Break']:
            continue
        if field.fieldtype == 'Attach':
            continue 
        if field.hidden:
            continue
        
        value = invoice_doc.get(fieldname)
        if value is not None and value != "":
        
            if fieldname in default_only_fields and field.default and str(value) == str(field.default):
                data[fieldname] = f"{str(value)} (default - PDF'te olmayabilir)"
            elif field.fieldtype == 'Table':
                # Child table'ları serialize et - her item'ı dict'e çevir
                if isinstance(value, list):
                    serialized_items = []
                    for item in value:
                        if hasattr(item, 'as_dict'):
                            # Document objesi ise dict'e çevir
                            item_dict = item.as_dict()
                            # Sadece gerekli alanları al (name, doctype gibi meta alanları hariç)
                            clean_dict = {k: v for k, v in item_dict.items() 
                                        if k not in ['name', 'doctype', 'owner', 'creation', 'modified', 'modified_by', 'parent', 'parenttype', 'parentfield', 'idx']}
                            serialized_items.append(clean_dict)
                        elif isinstance(item, dict):
                            serialized_items.append(item)
                    data[fieldname] = json.dumps(serialized_items, ensure_ascii=False, default=str)
                else:
                    data[fieldname] = str(value)
            elif isinstance(value, (dict, list)):
                data[fieldname] = json.dumps(value, ensure_ascii=False, default=str)
            else:
                data[fieldname] = str(value)
    
    return data

def validate_invoice_with_ai(invoice_doctype, invoice_name):
    """Invoice'ı OpenAI ile doğrula"""
    try:
        invoice_doc = frappe.get_doc(invoice_doctype, invoice_name)
        
        # Invoice verilerini hazırla
        invoice_data = prepare_invoice_data_for_ai(invoice_doc)
        
        # OpenAI client
        client = get_openai_client()
        
        # Prompt hazırla (English for AI, results will be in Turkish)
        prompt = f"""You are an invoice validation expert. Compare the invoice data in JSON format below with the PDF content and perform accuracy validation.

Invoice DocType: {invoice_doctype}
Invoice Number: {invoice_doc.invoice_number}

Invoice data (extracted from DocType):
{json.dumps(invoice_data, indent=2, ensure_ascii=False)}

Task:
1. Analyze the PDF content thoroughly
2. Extract ALL important fields from the PDF (invoice number, dates, amounts, company info, addresses, fees, taxes, etc.)
3. Compare PDF data with DocType data in BOTH directions:
   a. For each field in DocType: Check if it exists in PDF and if values match
   b. For each important field in PDF: Check if it exists in DocType and if values match
4. Identify missing, incorrect, or mismatched fields:
   - "missing_fields": Fields that exist in PDF but are NOT in DocType (or have no value in DocType)
   - "incorrect_fields": Fields that exist in both but have mismatched values
   - "extras_in_pdf": Fields in PDF that are not expected/standard in DocType (informational only)
5. Provide an overall accuracy assessment

IMPORTANT COMPARISON RULES:
- For numerical values (amount, rate, etc.): Perform float comparison. For example, "2.70" and "2.7" or "9.00" and "9.0" should be considered the same. Ignore minor rounding differences (less than 0.01).
- Amount vs Rate/Percentage: ATTENTION! Fields ending with "_amount" are CURRENCY AMOUNTS (e.g., 2.70), fields ending with "_rate" or "_percent" are PERCENTAGES (e.g., 30). Do not confuse them! "admin_fee_amount" is an amount, "service_fee_rate" is a percentage. If the PDF shows "Admin Fee: €0.64" as an amount, compare it with the "_amount" field, not with a percentage.
- For date fields: Format differences are not important (e.g., "14-12-2025" and "2025-12-14" are the same).
- For text fields: Case differences and leading/trailing spaces are not important.
- Default values: If a field value is marked with "(default - may not be in PDF)", do NOT add this field to the "missing_fields" list if it's not in the PDF! These are system default values and are not mandatory in the PDF.

Response format (JSON):
{{
    "status": "Valid" | "Issues Found" | "Error",
    "confidence": 0.0-1.0 (accuracy confidence - MUST be calculated as: if all fields match=true AND no incorrect_fields AND no missing_fields, then confidence=1.0, otherwise calculate based on match ratio),
    "summary": "Short summary in Turkish (max 200 characters)",
    "details": {{
        "missing_fields": ["field1", "field2"],  // In PDF but not in DocType
        "incorrect_fields": ["field1", "field2"],  // Actually mismatched fields (numerical difference >0.01 or text difference) - ONLY fields where match=false
        "extras_in_pdf": ["field1", "field2"],  // In PDF but unexpected in DocType
        "field_comparisons": [
            {{
                "field": "invoice_number",
                "pdf_value": "...",
                "doctype_value": "...",
                "match": true/false  // For numerical values, perform float comparison
            }}
        ]
    }},
    "recommendations": ["recommendation1 in Turkish", "recommendation2 in Turkish"]
}}

CRITICAL CONFIDENCE CALCULATION RULES:
- If ALL field_comparisons have match=true AND incorrect_fields is empty AND missing_fields is empty: confidence MUST be 1.0 (100%)
- If any field has match=false, add it to incorrect_fields and calculate confidence based on: (number of match=true fields) / (total number of fields)
- Do NOT reduce confidence for format differences (dates, numbers) if they are logically equivalent
- Do NOT reduce confidence for default values marked with "(default - PDF'te olmayabilir)" if they match the PDF value

CRITICAL JSON FORMATTING RULES (MUST FOLLOW):
- Use double quotes (") for ALL strings, NEVER single quotes (')
- Escape ALL special characters in strings: use \\" for quotes inside strings, \\n for newlines, \\\\ for backslashes
- Ensure ALL strings are properly closed with closing quotes
- Add commas (,) between ALL JSON object properties and array elements
- Do NOT include trailing commas after the last item in objects or arrays
- Ensure ALL opening braces {{ and brackets [ have matching closing braces }} and brackets ]
- Do NOT include any text, explanations, or comments outside the JSON structure
- The response MUST be valid JSON that can be parsed directly by json.loads() without any modifications
- If a string value contains quotes, newlines, or special characters, you MUST escape them properly
- Example of proper escaping: "summary": "Fatura verileri \\"PDF\\" ile uyumlu" (note the escaped quotes)

IMPORTANT: Provide response in JSON format only, no additional text. The summary and recommendations should be in Turkish."""

        # PDF raw text'i al (PDF gönderimi yerine metin kullanıyoruz; API PDF'i image olarak kabul etmiyor)
        raw_text = invoice_doc.get("raw_text", "")
        if not raw_text:
            frappe.throw("PDF raw text bulunamadı. Önce fatura işlenmiş olmalı.")
        
        # OpenAI API çağrısı - PDF text'i ile analiz
        messages = [
            {
                "role": "system",
                "content": "You are an invoice validation expert. You compare PDF text with DocType data and perform accuracy analysis. Provide responses in Turkish for summary and recommendations fields, but use English for technical terms and field names."
            },
            {
                "role": "user",
                "content": f"""{prompt}

PDF Text (Raw):
{raw_text[:15000]}  # Max 15000 chars
"""
            }
        ]
        
        # OpenAI API çağrısı - JSON mode ile (geçerli JSON garantisi)
        try:
            response = client.chat.completions.create(
                model="gpt-4o",  # veya "gpt-4-turbo"
                messages=messages,
                temperature=0.3,
                max_tokens=2000,
                response_format={"type": "json_object"}  # JSON mode - geçerli JSON garantisi
            )
        except Exception as api_error:
            # Eğer model JSON mode desteklemiyorsa, normal modda dene
            logger.warning(f"JSON mode desteklenmiyor, normal modda denenecek: {str(api_error)}")
            response = client.chat.completions.create(
                model="gpt-4o",
                messages=messages,
                temperature=0.3,
                max_tokens=2000
            )
        
        response_text = response.choices[0].message.content.strip()
        
        # JSON'u parse et
        try:
            # Eğer yanıt ```json ... ``` formatındaysa temizle
            if "```json" in response_text:
                response_text = response_text.split("```json")[1].split("```")[0].strip()
            elif "```" in response_text:
                # Herhangi bir ``` bloğu varsa içindekini al
                parts = response_text.split("```")
                if len(parts) >= 3:
                    response_text = parts[1].strip()
                    # Eğer "json" ile başlıyorsa onu da temizle
                    if response_text.lower().startswith("json"):
                        response_text = response_text[4:].strip()
            
            # JSON dışı metinleri temizle (başta ve sonda)
            # Eğer { ile başlamıyorsa, ilk { karakterini bul
            first_brace = response_text.find('{')
            if first_brace > 0:
                response_text = response_text[first_brace:]
            
            # Son } karakterini bul
            last_brace = response_text.rfind('}')
            if last_brace > 0 and last_brace < len(response_text) - 1:
                response_text = response_text[:last_brace + 1]
            
            # JSON parse et - önce normal deneme
            validation_result = None
            try:
                validation_result = json.loads(response_text)
            except json.JSONDecodeError as parse_error:
                # İlk deneme başarısız oldu, JSON repair dene
                logger.warning(f"Normal JSON parse başarısız, repair deneniyor: {str(parse_error)}")
                try:
                    validation_result = repair_json(response_text)
                    if validation_result:
                        logger.info("JSON repair başarılı")
                except Exception as repair_error:
                    logger.warning(f"JSON repair başarısız: {str(repair_error)}")
                
                # Hala parse edilemediyse, daha agresif temizleme dene
                if not validation_result:
                    # Trailing comma'ları kaldır
                    cleaned = re.sub(r',(\s*[}\]])', r'\1', response_text)
                    try:
                        validation_result = json.loads(cleaned)
                        logger.info("Cleaned JSON parse başarılı")
                    except json.JSONDecodeError:
                        # Son çare: AI'dan tekrar iste (retry)
                        logger.warning("Tüm parse denemeleri başarısız, AI'dan tekrar isteniyor...")
                        try:
                            retry_response = client.chat.completions.create(
                                model="gpt-4o",
                                messages=[
                                    {
                                        "role": "system",
                                        "content": "You are a JSON-only response generator. You MUST respond with ONLY valid JSON, no explanations, no markdown, no code blocks. Your response must be parseable by json.loads() without any errors. Escape all special characters in strings properly."
                                    },
                                    {
                                        "role": "user",
                                        "content": f"Please fix this JSON and return ONLY the corrected JSON (no explanations, no markdown, no code blocks, just pure JSON):\n\n{response_text[:2000]}"
                                    }
                                ],
                                temperature=0.1,
                                max_tokens=2000,
                                response_format={"type": "json_object"}
                            )
                            retry_text = retry_response.choices[0].message.content.strip()
                            retry_first_brace = retry_text.find('{')
                            retry_last_brace = retry_text.rfind('}')
                            if retry_first_brace >= 0 and retry_last_brace > retry_first_brace:
                                retry_text = retry_text[retry_first_brace:retry_last_brace + 1]
                            validation_result = json.loads(retry_text)
                            logger.info("Retry JSON parse başarılı")
                        except Exception as retry_error:
                            logger.error(f"Retry parse başarısız: {str(retry_error)}")
                            # Tüm denemeler başarısız, orijinal hatayı fırlat
                            raise parse_error
        except json.JSONDecodeError as e:
            # Daha detaylı hata loglama
            error_pos = getattr(e, 'pos', None)
            error_msg = str(e)
            
            # Hata pozisyonu civarındaki metni göster
            error_line = None
            if error_pos:
                start = max(0, error_pos - 200)
                end = min(len(response_text), error_pos + 200)
                error_context = response_text[start:end]
                # Hata satırını bul
                error_line_start = response_text.rfind('\n', 0, error_pos) + 1
                error_line_end = response_text.find('\n', error_pos)
                if error_line_end == -1:
                    error_line_end = len(response_text)
                error_line = response_text[error_line_start:error_line_end]
                
                logger.error(
                    f"AI yanıtı parse edilemedi (pos {error_pos}):\n"
                    f"Error: {error_msg}\n"
                    f"Error line: {error_line}\n"
                    f"Context (200 chars around error):\n{error_context}\n"
                    f"Full response length: {len(response_text)}"
                )
            else:
                logger.error(
                    f"AI yanıtı parse edilemedi:\n"
                    f"Error: {error_msg}\n"
                    f"Response (first 1000 chars):\n{response_text[:1000]}\n"
                    f"Full response length: {len(response_text)}"
                )
            
            # Hata durumunda response_text'in tamamını kaydet (debug için)
            # İlk 5000 karakteri kaydet, eğer daha uzunsa son 2000 karakteri de ekle
            error_log_message = f"Error: {error_msg}\n\n"
            if len(response_text) > 5000:
                error_log_message += f"Response (first 5000 chars):\n{response_text[:5000]}\n\n"
                error_log_message += f"Response (last 2000 chars):\n{response_text[-2000:]}\n"
            else:
                error_log_message += f"Response (full):\n{response_text}\n"
            
            frappe.log_error(
                title="AI JSON Parse Error",
                message=error_log_message
            )
            
            # Kullanıcıya daha anlamlı hata mesajı
            user_error_msg = f"AI yanıtı parse edilemedi: {error_msg}"
            if error_pos:
                user_error_msg += f"\n\nHata pozisyonu: karakter {error_pos}"
                if error_line:
                    user_error_msg += f"\nHatalı satır: {error_line[:100]}"
            
            frappe.throw(user_error_msg)
        
        # Sonuçları invoice'a kaydet
        update_ai_validation_fields(invoice_doc, validation_result)
        
        return validation_result
        
    except Exception as e:
        logger.error(f"AI validation hatası: {str(e)}\n{frappe.get_traceback()}")
        frappe.log_error(
            title="AI Validation Error",
            message=f"Invoice: {invoice_doctype} / {invoice_name}\nError: {str(e)}\n{frappe.get_traceback()}"
        )
        
        # Hata durumunda status'u güncelle (submit edilmiş invoice'larda da çalışması için set_value kullan)
        try:
            frappe.db.set_value(invoice_doctype, invoice_name, {
                "ai_validation_status": "Error",
                "ai_validation_summary": f"Error: {str(e)}"[:200],
                "ai_validation_date": frappe.utils.now()
            }, update_modified=False)
            frappe.db.commit()
        except Exception as update_error:
            logger.error(f"Error field update hatası: {str(update_error)}")
        
        frappe.throw(f"AI validation hatası: {str(e)}")

def update_ai_validation_fields(invoice_doc, validation_result):
    """AI validation sonuçlarını invoice alanlarına yaz"""
    status = validation_result.get("status", "Error")
    summary = validation_result.get("summary", "")[:200]  # Max 200 karakter
    confidence = (validation_result.get("confidence", 0) * 100) if validation_result.get("confidence") else None
    result_json = json.dumps(validation_result, indent=2, ensure_ascii=False)
    validation_date = frappe.utils.now()
    
    # Submit edilmiş invoice'larda da çalışması için set_value kullan
    frappe.db.set_value(invoice_doc.doctype, invoice_doc.name, {
        "ai_validation_status": status,
        "ai_validation_summary": summary,
        "ai_validation_confidence": confidence,
        "ai_validation_result": result_json,
        "ai_validation_date": validation_date
    }, update_modified=False)
    frappe.db.commit()

@frappe.whitelist()
def recheck_invoice_with_ai(doctype, name, show_message=True):
    """Server method: Invoice'ı AI ile tekrar kontrol et
    
    Args:
        doctype: Invoice doctype
        name: Invoice name
        show_message: If True, show success message (default: True)
    """
    try:
        result = validate_invoice_with_ai(doctype, name)
        if show_message:
            frappe.msgprint(
                f"AI Validation tamamlandı: {result.get('status')} (Confidence: {result.get('confidence', 0)*100:.1f}%)",
                indicator="green" if result.get("status") == "Valid" else "orange"
            )
        return result
    except Exception as e:
        if show_message:
            frappe.msgprint(f"Hata: {str(e)}", indicator="red")
        frappe.throw(str(e))

