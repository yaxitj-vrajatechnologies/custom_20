# -*- coding: utf-8 -*-
{
    # App information
    'name': 'Hubstaff Odoo Integration | Project | Task | Time Tracking | User SyncHubstaff Odoo Integration | Project | Task | Time Tracking | User Sync'"Hubstaff Odoo Integration | Project | Task | Time Tracking | User Sync""",
    "version": "20.0.1.0",
    'sequence': 1,
    "category": "Project",
    'summary': '''The Hubstaff Odoo Integration module enables seamless synchronization between Hubstaff and Odoo for efficient project management and time tracking.
     This integration connects Hubstaff time tracking data with Odoo projects and tasks, allowing businesses to manage work, teams, and productivity in a centralized system.

     It supports:
     Projects Sync (Import/Export)
     Tasks Sync (Import/Export)
     Users Sync
     Time Tracking Entries Import

     Key Features:
     Bi-directional synchronization of projects between Hubstaff and Odoo
     Sync tasks and link them with Odoo project tasks
     Import time entries from Hubstaff into Odoo timesheets
     Sync users between Hubstaff and Odoo
     OAuth2 authentication with secure access and refresh token handling
     Automatic scheduled synchronization using cron jobs
     Manual sync options for projects, tasks, and users
     Webhook support for real-time updates
     Centralized management of Hubstaff data inside Odoo
     Improved productivity tracking and reporting

     Odoo Hubstaff Integration
     Odoo Time Tracking Integration
     Hubstaff Project Sync Odoo
     Hubstaff Task Sync Odoo
     Odoo Employee Time Tracking
     Odoo Productivity Monitoring
     Odoo Timesheet Automation
     Odoo API Integration Hubstaff
     Odoo Project Management Integration

     Intégration Hubstaff Odoo
     Suivi du temps Odoo Hubstaff
     Synchronisation projet Odoo Hubstaff
     Automatisation des feuilles de temps Odoo

     Integración Hubstaff Odoo
     Seguimiento de tiempo Odoo Hubstaff
     Sincronización de proyectos Odoo Hubstaff
     Automatización de hojas de tiempo Odoo

     Hubstaff Odoo-integratie
     Tijdregistratie Odoo Hubstaff
     Project synchronisatie Odoo Hubstaff
     Odoo automatisering werktijden

     Integración Hubstaff Odoo
     Seguimiento de tiempo Odoo Hubstaff
     Sincronización de tareas Odoo Hubstaff
     Automatización de tiempos Odoo''',
    'license': 'OPL-1',

    # Dependencies
    "depends": ['project','hr_timesheet'],

    # Views
    "data": [
        'data/ir_cron.xml',
        'data/ir_sequence.xml',
        'security/ir.access.csv',
        'wizard/hubstaff_operations.xml',
        'views/hubstaff_webhook.xml',
        'views/hubstaff_log.xml',
        'views/hubstaff_instance_integration.xml',
        'views/project_project.xml',
        'views/project_task.xml',
         'views/res_users.xml',
        'views/account_analytic_line.xml',
        'views/menu_item.xml',
        'wizard/hubstaff_export_project_wizard.xml',
    ],
    
    # Odoo Store Specific
    'images': ['static/description/cover.gif'],

    # Author
    'author': 'Vraja Technologies',
    'website': 'https://www.vrajatechnologies.com',
    'maintainer': 'Vraja Technologies',

    # Technical
    'demo': [],
    'installable': True,
    'application': True,
    'autoinstall': False,
    'live_test_url': 'https://www.vrajatechnologies.com/contactus',
    'price': '99',
    'currency': 'EUR',
}
