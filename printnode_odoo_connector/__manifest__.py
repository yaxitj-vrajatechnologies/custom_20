# -*- coding: utf-8 -*-
{
    # App information
    'name': 'Odoo PrintNode Integration | Automated & Remote Printing Solution | PrintNode Odoo Connector | Direct Print | Shipping Label Print | Invoice Print | Direct Label & Report Printing | Print Instantly from Odoo to Any Printer with PrintNode',
    'category': 'Inventory/Inventory',
    'version': '20.0.1.0',
    'summary': '''The PrintNode Odoo Connector module provides seamless integration between Odoo and PrintNode, enabling automated and remote printing directly from Odoo to printers connected through PrintNode.
                The module imports computers from PrintNode along with their associated printers and supported paper sizes, allowing administrators to manage available printing devices directly within Odoo.
                It also allows configuring automatic printing rules, which can trigger the direct printing of documents or attachments based on defined conditions. This helps automate printing workflows and reduces manual intervention.
                The module provides report printing settings where administrators can configure specific users who can access the Print Wizard to print reports directly through PrintNode from Odoo.
                Additionally, the module supports direct label printing, allowing shipping labels or product labels to be printed automatically through PrintNode without downloading the files manually.
                This integration ensures efficient printer management, automated document printing, and streamlined printing workflows between Odoo and PrintNode.
                Direct Print Odoo Connector
                Advanced PrintNode Connector
                Auto Printing Integration
                Odoo Remote Printing
                PrintNode Integration for Odoo
                Odoo PrintNode Connector – Direct & Auto Printing 
                Report Printing
                Smart Printing for Odoo
                vraja PrintNode Integration
                Odoo Instant Printing
                vraja Direct Print
                Vraja Auto Printing
                Vraja Technologies Printnode Connector
                automate printing workflow Odoo
		warehouse label printing automation
		invoice printing automation Odoo
		delivery slip auto printing Odoo
		barcode label printing Odoo
		POS receipt printing Odoo PrintNode
		print attachments automatically Odoo
		centralized printing system Odoo
                vraja_featured_apps
                
                Intégration PrintNode Odoo | Connecteur d’Impression Directe Odoo | Workflow d’Impression Automatique Odoo | Gestion à Distance des Imprimantes Odoo | Impression d’Étiquettes et de Rapports Odoo (French)
                Integración PrintNode Odoo | Conector de Impresión Directa Odoo | Flujo de Impresión Automática Odoo | Gestión Remota de Impresoras Odoo | Impresión de Etiquetas y Reportes Odoo (Spanish)
                Odoo PrintNode Integratie | Odoo Direct Print Connector | Odoo Automatische Printworkflow | Odoo Printerbeheer op Afstand | Odoo Label- en Rapportafdrukken (Dutch)
                Integración PrintNode Odoo | Conector de Impresión Directa Odoo | Flujo de Impresión Automática Odoo | Gestión Remota de Impresoras Odoo | Impresión de Etiquetas y Reportes Odoo (Mexican)''',
    'license': 'OPL-1',
    'description': "",

    # Dependencies
    'depends': ['mail', 'account','stock_delivery', 'sale', 'purchase'],

    # Views
    'data': [
        'security/ir.access.csv',
        'data/ir_cron_view.xml',
        'data/printnode_rule_action_view.xml',
        'views/res_user_view.xml',
        'views/res_company_view.xml',
        'views/printnode_view.xml',
        'views/printnode_printjob_view.xml',
        'views/printnode_rule_view.xml',
        'views/delivery_carrier_view.xml',
        'views/printnode_computer_view.xml',
        'views/printnode_paper_view.xml',
        'views/printnode_printer_view.xml',
        'views/ir_action_report_view.xml',
        'views/shipping_label_view.xml',
        'views/printnode_log_view.xml',
    ],

    "assets": {
        "web.assets_backend": [
            "printnode_odoo_connector/static/src/js/pdf_options_modal.js",
            "printnode_odoo_connector/static/src/js/printnode_report_handler.js",
            "printnode_odoo_connector/static/src/xml/report_pdf_options.xml",
        ],
    },

    # Odoo Store Specific
    'images': ['static/description/cover.gif'],

    # Author
    'author': 'Vraja Technologies',
    'website': 'http://www.vrajatechnologies.com',
    'maintainer': 'Vraja Technologies',
    'live_test_url': 'https://www.vrajatechnologies.com/contactus',

    # Technical
    'post_init_hook': 'post_init_hook',
    'demo': [],
    'installable': True,
    'application': True,
    'auto_install': False,
    'price': '59',
    'currency': 'EUR',
}
