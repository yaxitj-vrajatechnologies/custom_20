# -*- coding: utf-8 -*-pack
{
    # App information
    'name': 'Compare Vendor Price | Vendor Quotation Comparison & Automated Purchase Ordering | Multi-Vendor RFQ Comparison | Odoo Vendor Price Comparison | Multi-Vendor RFQ & Automatic Purchase Orders',
    'category': 'Purchases',
    'version': '20.0.1.0',
    'summary': '''multi-vendor RFQ requests, CSV quotation exchange, automatic price and lead-time comparison, lowest-price supplier selection, manual vendor override, automatic Purchase Order creation, and merging results into existing draft POs
Odoo Vendor Price Comparison
Odoo Supplier Price Comparison
Odoo Multi-Vendor RFQ
Odoo Purchase Enquiry Module
Supplier Bid Comparison
How to compare multiple vendor prices in Odoo
Odoo module to compare vendor quotations
Compare supplier prices and lead times in Odoo
Send RFQs to multiple vendors from Odoo
Automatically compare vendor quotations in Odoo
Automatically select the lowest-price vendor in Odoo
Select the best supplier based on price and lead time
Complete vendor price comparison and RFQ automation solution that lets you raise a purchase enquiry, send RFQ to multiple vendors in one click, and compare their quoted price and lead time side by side before creating Purchase Orders.
                Each vendor receives an auto-generated price sheet on RFQ send, and their filled sheet is imported back with rows matched to products by Product Code first, falling back to Product Name, so every product is compared reliably even without a code.
                Clean state-driven workflow moving through Draft, RFQ Sent, Compared, and PO Created, with the best price and lead time picked automatically per product and the winning vendor still changeable by hand at any time.
                Guarded Recompare option lets you safely re-import an updated vendor file and re-run the comparison after the first pass, without leaving every field open to accidental edits in between.
                Create PO groups the chosen vendor per product and creates one Purchase Order per vendor, merging into an existing draft PO for that vendor instead of duplicating it wherever one already exists.
                Full chatter logging on every stage change, smart buttons for quick navigation to related Vendors, Quotations, and Purchase Orders, and a dedicated Vendor Quotations view for tracking every response in one place.
                odoo vendor price comparison, rfq automation odoo, multi vendor rfq, purchase enquiry odoo, vendor quotation comparison, best price selection odoo, lead time comparison, purchase order automation, vendor management odoo, rfq to po odoo, price comparison purchase, quotation import odoo, csv quotation import, purchase price benchmarking, vendor sourcing odoo, competitive vendor pricing, rfq workflow odoo, purchase negotiation tool, odoo procurement automation, vendor bid comparison
                Vendor Price Comparison Engine
                Multi Vendor RFQ Automation
                Purchase Enquiry to PO Workflow
                Automated Vendor Quotation Comparison
                Best Price Vendor Selection
                RFQ and Quotation Management
                Odoo Purchase Price Comparison
                Vendor Sourcing and Bid Comparison
                Automated Purchase Order Creation
                Purchase Procurement Automation Odoo''',
    'license': 'OPL-1',
    'description': "",

    # Dependencies
    'depends': ['purchase', 'product', 'mail'],

    # Views
    'data': [
        'security/ir.access.csv',
        'data/ir_sequence_data.xml',
        'views/price_enquiry_views.xml',
        'views/price_quotation_views.xml',
        'views/menu_views.xml',
    ],

    # Odoo Store Specific
    'images': ['static/description/cover.gif'],

    # Author
    'author': 'Vraja Technologies',
    'website': 'https://www.vrajatechnologies.com',
    'maintainer': 'Vraja Technologies',
    'live_test_url': 'https://www.vrajatechnologies.com/contactus',

    # Technical
    'demo': [],
    'installable': True,
    'application': True,
    'autoinstall': False,
    'price': '99',
    'currency': 'EUR',

}
# version changelog
