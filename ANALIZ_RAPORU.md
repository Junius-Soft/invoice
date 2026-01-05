# Invoice App - Kapsamlı Analiz Raporu

**Tarih:** 2025-01-27  
**Versiyon:** Frappe Framework 15+  
**Dil:** Python 3.10+

---

## 📋 İçindekiler

1. [Genel Bakış](#genel-bakış)
2. [Mimari Yapı](#mimari-yapı)
3. [Ana Bileşenler](#ana-bileşenler)
4. [İş Akışı Analizi](#iş-akışı-analizi)
5. [DocType Yapıları](#doctype-yapıları)
6. [API Fonksiyonları](#api-fonksiyonları)
7. [Özellikler ve Yetenekler](#özellikler-ve-yetenekler)
8. [Güçlü Yönler](#güçlü-yönler)
9. [İyileştirme Önerileri](#iyileştirme-önerileri)
10. [Teknik Detaylar](#teknik-detaylar)

---

## 🎯 Genel Bakış

Invoice app, yemek sipariş platformlarından (Lieferando, Wolt, Uber Eats) gelen PDF faturalarını otomatik olarak işleyen, analiz eden ve doğrulayan bir Frappe/ERPNext uygulamasıdır.

### Temel Amaç
- Email üzerinden gelen PDF faturalarını otomatik yakalama
- PDF'lerden veri çıkarma (OCR/Text Extraction)
- Platform bazlı fatura kayıtları oluşturma
- Fatura analizi ve hesaplamalar yapma
- AI destekli doğrulama yapma
- Raporlama ve print formatları oluşturma

### Desteklenen Platformlar
1. **Lieferando** (yourdelivery GmbH)
2. **Wolt** (Wolt Enterprises Deutschland GmbH)
3. **Uber Eats** (Uber Eats Germany GmbH)

---

## 🏗️ Mimari Yapı

### Dizin Yapısı
```
invoice/
├── invoice/
│   ├── api/                    # API fonksiyonları
│   │   ├── constants.py        # Sabitler ve magic numbers
│   │   ├── invoice_email_handler.py  # Email işleme ana modülü
│   │   ├── email_tasks.py      # Scheduled tasks
│   │   ├── invoice_ai_validation.py  # AI doğrulama
│   │   └── update_stamp_card_data.py # Stamp card güncelleme
│   ├── invoice/
│   │   ├── doctype/            # DocType tanımları
│   │   │   ├── lieferando_invoice/
│   │   │   ├── lieferando_invoice_analysis/
│   │   │   ├── lieferando_invoice_order_item/
│   │   │   ├── lieferando_invoice_tip_item/
│   │   │   ├── wolt_invoice/
│   │   │   └── uber_eats_invoice/
│   │   └── print_format/       # Print format şablonları
│   ├── tools/                  # Yardımcı scriptler
│   └── hooks.py                # App konfigürasyonu
├── pyproject.toml              # Python dependencies
└── README.md
```

### Mimari Katmanlar

1. **Presentation Layer**: Frappe DocType'ları ve UI
2. **Business Logic Layer**: Python controller dosyaları
3. **Data Extraction Layer**: PDF parsing ve regex extraction
4. **Integration Layer**: Email handlers, scheduled tasks
5. **Validation Layer**: AI validation, data validation
6. **Storage Layer**: Frappe database (MariaDB/PostgreSQL)

---

## 🔧 Ana Bileşenler

### 1. Email İşleme Sistemi (`invoice_email_handler.py`)

**Amaç:** Communication DocType'ına gelen email'leri yakalar ve PDF eklerini işler.

**Özellikler:**
- Email subject'ine göre platform tespiti
- PDF attachment'larını filtreleme
- Duplicate kontrolü (invoice_number bazlı)
- Platform-spesifik işleme (Lieferando/Wolt/Uber Eats)
- Real-time bildirimler

**İş Akışı:**
```
Communication DocType → process_invoice_email() → 
Platform Tespiti → PDF Extraction → 
Invoice DocType Oluşturma → PDF Attachment → 
Bildirim Gönderme
```

**Kritik Fonksiyonlar:**
- `process_invoice_email()`: Ana email handler (doc_events hook)
- `create_invoice_from_pdf()`: Platform tespiti ve routing
- `extract_invoice_data_from_pdf()`: PDF'den veri çıkarma
- `detect_platform_from_filename()`: Dosya adından platform tespiti
- `detect_invoice_platform()`: PDF içeriğinden platform tespiti

### 2. PDF Veri Çıkarma Sistemi

**Kullanılan Teknoloji:** PyPDF2 (text extraction)

**Yaklaşım:** Regex pattern matching ile PDF text'inden veri çıkarma

**Platform-Spesifik Extraction:**
- `extract_lieferando_fields()`: Lieferando fatura alanları
- `extract_wolt_fields()`: Wolt fatura alanları
- `extract_uber_eats_fields()`: Uber Eats fatura alanları

**Çıkarılan Veri Tipleri:**
- Fatura bilgileri (numarası, tarihi, dönem)
- Müşteri/Tedarikçi bilgileri
- Sipariş istatistikleri (toplam, online, nakit)
- Ücret ve komisyon bilgileri
- Vergi bilgileri
- Ödeme bilgileri
- Sipariş detayları (order_items)
- Bahşiş bilgileri (tip_items)

### 3. DocType Yapıları

#### A. Lieferando Invoice
**Amaç:** Lieferando platformundan gelen faturaları saklar.

**Ana Alanlar:**
- Fatura bilgileri (invoice_number, invoice_date, period_start, period_end)
- Tedarikçi bilgileri (supplier_name, supplier_ust_idnr, supplier_iban, vb.)
- Müşteri bilgileri (restaurant_name, customer_number, customer_tax_number, vb.)
- Sipariş istatistikleri (total_orders, total_revenue, online_paid_orders, vb.)
- Ücretler (service_fee_rate, service_fee_amount, admin_fee_amount)
- Vergi (tax_rate, tax_amount)
- Ödemeler (paid_online_payments, outstanding_amount, payout_amount)
- Metadata (pdf_file, email_subject, raw_text, extraction_confidence)

**Özel Özellikler:**
- `invoice_number` field'ı aynı zamanda document name (autoname)
- Child tables: `order_items`, `tip_items` (opsiyonel)
- AI validation alanları (ai_validation_status, ai_validation_result)

#### B. Lieferando Invoice Analysis
**Amaç:** Lieferando faturalarını analiz eder ve komisyon hesaplamaları yapar.

**Ana Hesaplamalar:**
- Service fee calculations
- Management fee calculations
- Culinary commission calculations
- Payment to restaurant calculations
- Reference values (varsayılan komisyon oranına göre)

**İş Mantığı:**
1. `load_from_invoice()`: Lieferando Invoice'dan veri yükleme
2. `validate_data()`: Veri doğrulama (negatif değerler, mantıksal tutarlılık)
3. `calculate_all_amounts()`: Tüm hesaplamalar

**Kritik Hesaplamalar:**
- C: Subtotal (Service Fee + Management Fee + Additional Service Fee)
- D: VAT Amount (C × Tax Rate)
- E: Total Invoice Amount (C + D)
- Culinary Commission Profit
- H: Payment to Restaurant (G - E - Culinary Commission)

#### C. Wolt Invoice
**Amaç:** Wolt platformundan gelen faturaları saklar.

**Özel Özellikler:**
- Netting report desteği (netting_report_pdf field)
- VAT breakdown (7% ve 19% ayrımı)
- Distribution fees
- Netprice calculations

#### D. Uber Eats Invoice
**Amaç:** Uber Eats platformundan gelen faturaları saklar.

**Özel Özellikler:**
- Commission breakdown (own delivery, pickup)
- Uber Eats fee
- Cash collected
- Total payout

### 4. AI Doğrulama Sistemi (`invoice_ai_validation.py`)

**Teknoloji:** OpenAI GPT-4o

**Amaç:** PDF içeriği ile DocType verilerini karşılaştırarak doğruluk kontrolü yapar.

**Özellikler:**
- PDF text ile DocType data karşılaştırması
- Eksik/yanlış alan tespiti
- Confidence score hesaplama
- Öneriler sunma
- Sonuçları DocType'a kaydetme

**Kullanım:**
- `validate_invoice_with_ai()`: Ana validation fonksiyonu
- `recheck_invoice_with_ai()`: Whitelisted server method (UI'dan çağrılabilir)

**Karşılaştırma Kuralları:**
- Numeric values: Float comparison (0.01 tolerance)
- Date fields: Format farklılıkları önemli değil
- Text fields: Case insensitive, trim spaces
- Amount vs Rate: Doğru field type eşleştirmesi

### 5. Scheduled Tasks (`email_tasks.py`)

**Amaç:** Periyodik olarak email'leri çeker ve işler.

**Konfigürasyon:**
- `scheduler_events`: `"all"` event'inde çalışır
- Fonksiyon: `sync_gmail_invoices()`
- Sıklık: Her 5 dakikada bir (cron: `*/5 * * * *`)

**İşleyiş:**
1. Aktif Email Account'ları bulur (enable_incoming=1)
2. Her hesap için `email_doc.receive()` çağırır
3. Yeni email'ler Communication DocType'a kaydedilir
4. `process_invoice_email()` otomatik tetiklenir (doc_events hook)

### 6. Print Formatlar

**Mevcut Print Formatlar:**
- `lieferando_invoice_format`: Lieferando faturaları için
- `lieferando_invoice_analysis_format`: Analysis dokümanları için

**Özellikler:**
- HTML/CSS tabanlı şablonlar
- Jinja2 template engine
- Invoice data JSON'dan parse edilir
- Custom styling ve layout

---

## 🔄 İş Akışı Analizi

### Email'den Fatura Oluşturma Akışı

```
1. Email Gelişi
   ↓
2. Communication DocType Oluşturma
   ↓
3. doc_events Hook Tetiklenmesi
   (after_insert / on_update)
   ↓
4. process_invoice_email() Çağrısı
   ↓
5. Email Filtreleme
   - Communication type = "Communication"
   - Sent or Received = "Received"
   - Subject kontrolü (invoice keywords)
   ↓
6. PDF Attachment Bulma
   ↓
7. Platform Tespiti
   - Dosya adından (öncelikli)
   - PDF içeriğinden
   ↓
8. PDF Text Extraction (PyPDF2)
   ↓
9. Regex Pattern Matching
   - Platform-spesifik extraction
   ↓
10. Duplicate Kontrolü
    - invoice_number bazlı kontrol
    ↓
11. Invoice DocType Oluşturma
    - Platform-spesifik DocType
    - Field mapping
    - Child table items (order_items, tip_items)
    ↓
12. PDF Attachment
    - File DocType oluşturma
    - pdf_file field'ına bağlama
    ↓
13. Bildirim Gönderme
    - Real-time notification
    - Notification Log
    ↓
14. DB Commit
```

### Analysis Oluşturma Akışı

```
1. Lieferando Invoice Analysis Oluşturma
   ↓
2. before_insert / before_save Validation
   - lieferando_invoice field kontrolü
   ↓
3. validate() Çağrısı
   ↓
4. load_from_invoice()
   - Invoice'dan veri yükleme
   - invoice_data_json oluşturma
   ↓
5. validate_data()
   - Negatif değer kontrolü
   - Mantıksal tutarlılık kontrolü
   - Warnings/Errors toplama
   ↓
6. calculate_all_amounts()
   - Service fee hesaplama
   - Management fee hesaplama
   - Culinary commission hesaplama
   - Payment to restaurant hesaplama
   ↓
7. Save
```

---

## 📊 DocType Yapıları Detay

### Lieferando Invoice - Field Kategorileri

1. **Invoice Information**
   - invoice_number, invoice_date, period_start, period_end, status

2. **Supplier Section**
   - supplier_name, supplier_address, supplier_email, supplier_phone
   - supplier_ust_idnr, supplier_bank_name, supplier_iban
   - supplier_geschäftsführer, supplier_amtsgericht, supplier_hrb

3. **Customer Section**
   - restaurant_name, customer_number, restaurant_address
   - customer_company, customer_bank_iban, customer_tax_number

4. **Orders Section**
   - total_orders, total_revenue
   - online_paid_orders, online_paid_amount
   - cash_paid_orders, cash_paid_amount
   - chargeback_orders, chargeback_amount
   - cash_service_fee_amount
   - stamp_card_orders, stamp_card_amount

5. **Fees Section**
   - service_fee_rate, service_fee_amount
   - admin_fee_rate, admin_fee_amount

6. **Amounts Section**
   - tax_rate, subtotal, tax_amount
   - paid_online_payments, outstanding_amount
   - total_amount

7. **Payout Section**
   - payout_amount, outstanding_balance
   - ausstehende_am_datum, ausstehende_onlinebezahlungen_betrag
   - rechnungsausgleich_betrag, auszahlung_gesamt

8. **Metadata Section**
   - pdf_file, email_subject, email_from
   - received_date, processed_date
   - extraction_confidence, raw_text

9. **AI Validation Section**
   - ai_validation_status, ai_validation_summary
   - ai_validation_date, ai_validation_confidence
   - ai_validation_result

10. **Orders Detail Section**
    - Child Table: order_items
    - Child Table: tip_items (opsiyonel)

---

## 🔌 API Fonksiyonları

### Constants (`constants.py`)

**Amaç:** Magic numbers ve hardcoded değerlerin merkezi yönetimi

**Önemli Sabitler:**
- `DEFAULT_CULINARY_ACCOUNT_FEE = 0.35`
- `SERVICE_FEE_OWN_DELIVERY = 12`
- `SERVICE_FEE_DELIVERY = 30`
- `DEFAULT_EXTRACTION_CONFIDENCE = 60`
- Platform isimleri, DocType isimleri, field isimleri
- Email keywords, log mesajları

### Email Handler (`invoice_email_handler.py`)

**Ana Fonksiyonlar:**

1. **process_invoice_email(doc, method)**
   - Communication DocType event handler
   - Email filtreleme ve PDF attachment bulma
   - Platform tespiti ve routing
   - Duplicate kontrolü
   - Invoice oluşturma ve bildirim

2. **create_invoice_from_pdf(communication_doc, pdf_attachment)**
   - Platform tespiti (filename + content)
   - PDF extraction
   - Platform-spesifik invoice oluşturma

3. **extract_invoice_data_from_pdf(pdf_attachment)**
   - PyPDF2 ile text extraction
   - Platform detection
   - Platform-spesifik field extraction

4. **Platform-Spesifik Extraction:**
   - `extract_lieferando_fields(full_text)`
   - `extract_wolt_fields(full_text)`
   - `extract_uber_eats_fields(full_text)`

5. **Platform Detection:**
   - `detect_platform_from_filename(file_name)`
   - `detect_invoice_platform(full_text)`

6. **PDF Utility Functions:**
   - `check_pdf_has_uber_eats_header(pdf_attachment)`
   - `check_pdf_has_selbstfakturierung(pdf_attachment)`
   - `check_pdf_has_wolt_netting_report(pdf_attachment)`

7. **Netting Report Handler:**
   - `handle_wolt_netting_report(communication_doc, pdf_attachment)`
   - `extract_netting_fields(full_text)`

8. **Utility Functions:**
   - `parse_decimal(value)`: String'den decimal çevirme
   - `parse_date(date_str)`: Tarih formatı parsing
   - `attach_pdf_to_invoice()`: PDF attachment
   - `generate_temp_invoice_number()`: Geçici fatura numarası
   - `notify_invoice_created()`: Bildirim gönderme
   - `show_summary_notification()`: Özet bildirimi

### Email Tasks (`email_tasks.py`)

1. **sync_gmail_invoices()**
   - Scheduled task handler
   - Aktif Email Account'ları bulma
   - Email çekme (receive())
   - Error handling ve logging

### AI Validation (`invoice_ai_validation.py`)

1. **validate_invoice_with_ai(invoice_doctype, invoice_name)**
   - OpenAI API çağrısı
   - PDF text ile DocType data karşılaştırması
   - Validation result oluşturma
   - Sonuçları DocType'a kaydetme

2. **recheck_invoice_with_ai(doctype, name, show_message)**
   - Whitelisted server method
   - UI'dan çağrılabilir
   - Success/error mesajları

3. **prepare_invoice_data_for_ai(invoice_doc)**
   - DocType verilerini AI için hazırlama
   - Metadata filtreleme
   - JSON formatına çevirme

4. **update_ai_validation_fields(invoice_doc, validation_result)**
   - Validation sonuçlarını DocType'a yazma
   - set_value kullanımı (submitted docs için)

### Stamp Card Update (`update_stamp_card_data.py`)

1. **update_invoice_stamp_card_data(invoice_name)**
   - Tek fatura için stamp card güncelleme
   - raw_text'ten extraction
   - Field update

2. **update_all_invoices()**
   - Tüm faturaları güncelleme
   - Batch processing
   - Özet rapor

---

## ✨ Özellikler ve Yetenekler

### 1. Otomatik Email İşleme
- ✅ Communication DocType hook integration
- ✅ Multi-platform detection (Lieferando/Wolt/Uber Eats)
- ✅ Duplicate prevention (invoice_number bazlı)
- ✅ Real-time notifications
- ✅ Error handling ve logging

### 2. PDF Veri Çıkarma
- ✅ PyPDF2 text extraction
- ✅ Regex pattern matching
- ✅ Platform-spesifik parsing
- ✅ Order items extraction
- ✅ Tip items extraction (Lieferando)
- ✅ Netting report handling (Wolt)

### 3. Data Validation
- ✅ Field validation (negatif değerler, mantıksal tutarlılık)
- ✅ AI-powered validation (OpenAI GPT-4o)
- ✅ Confidence scoring
- ✅ Recommendation system

### 4. Analysis & Calculations
- ✅ Service fee calculations
- ✅ Management fee calculations
- ✅ Culinary commission calculations
- ✅ VAT calculations
- ✅ Payment to restaurant calculations
- ✅ Reference values (baseline calculations)

### 5. Reporting
- ✅ Print formats (HTML/CSS)
- ✅ Invoice data JSON export
- ✅ Analysis reports

### 6. Integration
- ✅ Scheduled email sync
- ✅ Email Account integration
- ✅ File attachment system
- ✅ Notification system

---

## 💪 Güçlü Yönler

1. **Modüler Yapı**
   - Platform-spesifik kod ayrımı
   - Reusable utility functions
   - Clear separation of concerns

2. **Robust Error Handling**
   - Try-catch blokları
   - Error logging (frappe.log_error)
   - Graceful degradation

3. **Extensibility**
   - Yeni platform ekleme kolaylığı
   - Configurable constants
   - Flexible field mapping

4. **User Experience**
   - Real-time notifications
   - Clear error messages
   - Progress indicators (batch operations)

5. **Data Integrity**
   - Duplicate prevention
   - Validation layers
   - AI validation for accuracy

6. **Documentation**
   - Inline comments (Turkish)
   - Function docstrings
   - Clear naming conventions

---

## 🚀 İyileştirme Önerileri

### 1. Performans Optimizasyonları

#### PDF Processing
- **Mevcut:** PyPDF2 ile text extraction (tüm sayfalar)
- **Öneri:** 
  - İlk sayfayı önce kontrol et (platform detection için)
  - Lazy loading (sadece gerektiğinde tüm sayfalar)
  - PDF caching (hash-based)

#### Database Queries
- **Mevcut:** Multiple `frappe.get_all()` calls
- **Öneri:**
  - Batch queries kullanımı
  - Index optimization (invoice_number, email fields)
  - Query result caching

#### Email Processing
- **Mevcut:** Her email için individual processing
- **Öneri:**
  - Batch email processing
  - Background jobs (Frappe Background Jobs)
  - Queue system (Redis/RQ)

### 2. Code Quality

#### Type Hints
- **Mevcut:** Minimal type hints
- **Öneri:**
  ```python
  def extract_lieferando_fields(full_text: str) -> dict:
      ...
  ```

#### Error Handling
- **Mevcut:** Generic Exception handling
- **Öneri:**
  - Specific exception types
  - Custom exception classes
  - Error recovery mechanisms

#### Testing
- **Mevcut:** Test dosyaları var ama kapsamı sınırlı
- **Öneri:**
  - Unit tests (extraction functions)
  - Integration tests (email processing)
  - Mock PDF files for testing
  - Test coverage > 80%

### 3. Feature Enhancements

#### PDF Extraction
- **Mevcut:** Regex-based extraction
- **Öneri:**
  - OCR support (scanned PDFs için)
  - Machine learning model (field extraction)
  - Multi-format support (HTML, XML invoices)

#### AI Validation
- **Mevcut:** OpenAI GPT-4o
- **Öneri:**
  - Local LLM option (privacy)
  - Batch validation
  - Validation caching
  - Confidence threshold configuration

#### Analysis Features
- **Mevcut:** Single invoice analysis
- **Öneri:**
  - Period-based analysis (monthly, quarterly)
  - Comparative analysis (platform comparison)
  - Trend analysis
  - Dashboard (charts, graphs)

### 4. Data Management

#### Backup & Recovery
- **Öneri:**
  - Automated backups
  - Point-in-time recovery
  - Export/Import utilities

#### Data Migration
- **Öneri:**
  - Migration scripts (version upgrades)
  - Data validation scripts
  - Rollback mechanisms

### 5. Security

#### API Keys
- **Mevcut:** Environment variables / site config
- **Öneri:**
  - Frappe secrets management
  - Key rotation
  - Access logging

#### Data Privacy
- **Öneri:**
  - PII field encryption
  - Data retention policies
  - GDPR compliance

### 6. Monitoring & Observability

#### Logging
- **Mevcut:** frappe.logger kullanımı
- **Öneri:**
  - Structured logging (JSON format)
  - Log levels (DEBUG, INFO, WARNING, ERROR)
  - Centralized logging (ELK stack)

#### Metrics
- **Öneri:**
  - Processing time metrics
  - Success/failure rates
  - Email processing queue length
  - PDF extraction accuracy

#### Alerting
- **Öneri:**
  - Error rate alerts
  - Processing delay alerts
  - System health checks

### 7. Documentation

#### Code Documentation
- **Öneri:**
  - Sphinx documentation
  - API documentation
  - Architecture diagrams

#### User Documentation
- **Öneri:**
  - User manual (Turkish)
  - Video tutorials
  - FAQ section

---

## 🔍 Teknik Detaylar

### Dependencies

**Python Packages:**
- `frappe` (framework)
- `PyPDF2` (PDF processing)
- `openai` (AI validation - optional)
- Standard library: `re`, `json`, `datetime`

**Frappe Framework:**
- Version: 15.0+
- Database: MariaDB/PostgreSQL
- Python: 3.10+

### Hooks Configuration

```python
# hooks.py
doc_events = {
    "Communication": {
        "after_insert": "invoice.api.invoice_email_handler.process_invoice_email",
        "on_update": "invoice.api.invoice_email_handler.process_invoice_email"
    }
}

scheduler_events = {
    "all": [
        "invoice.api.email_tasks.sync_gmail_invoices"
    ]
}
```

### Field Naming Conventions

- **Turkish fields:** `restaurant_name`, `invoice_number`
- **German fields:** `ausstehende_onlinebezahlungen_betrag`, `rechnungsausgleich_betrag`
- **English fields:** `total_revenue`, `service_fee_rate`
- **Abbreviations:** `ust_idnr` (Umsatzsteuer-Identifikationsnummer)

### Data Flow Patterns

1. **Email → Communication → Invoice**
   - Event-driven (doc_events)
   - Asynchronous processing

2. **Invoice → Analysis**
   - Manual creation
   - Synchronous validation/calculation

3. **Invoice → AI Validation**
   - Manual trigger (UI button)
   - External API call (OpenAI)

### Error Handling Patterns

```python
try:
    # Operation
except SpecificException as e:
    frappe.log_error(title="...", message=str(e))
    # Recovery or fallback
except Exception as e:
    frappe.log_error(title="...", message=str(e))
    frappe.throw(f"Error: {str(e)}")
```

### Logging Patterns

```python
logger = frappe.logger("invoice.module", allow_site=frappe.local.site)
logger.info("Message")
logger.warning("Warning")
logger.error("Error")
```

---

## 📝 Özet

Invoice app, yemek sipariş platformlarından gelen faturaları otomatik işleyen, analiz eden ve doğrulayan kapsamlı bir Frappe uygulamasıdır. 

**Ana Güçlü Yönler:**
- Modüler ve genişletilebilir yapı
- Multi-platform support
- AI-powered validation
- Comprehensive analysis capabilities

**Geliştirme Alanları:**
- Performance optimization
- Test coverage
- Monitoring & observability
- Documentation

**Kullanım Senaryoları:**
- Otomatik fatura işleme
- Komisyon hesaplamaları
- Fatura doğrulama
- Raporlama ve analiz

---

**Rapor Oluşturulma Tarihi:** 2025-01-27  
**Analiz Edilen Kod Satırı:** ~10,000+ satır  
**Dokümante Edilen Fonksiyon:** 50+ fonksiyon  
**DocType Sayısı:** 6+ DocType




