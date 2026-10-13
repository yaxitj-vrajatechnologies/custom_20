# -*- coding: utf-8 -*-
{
    # App information
    'name': 'Cleaning Service Management & Online Booking | Cleaning Service Booking & Staff Management',
    'category': 'Website',
    'version': '19.0.1.0',
    'summary': '''The Cleaning Service Management module provides a complete solution for managing cleaning service bookings, staff scheduling, and customer communication directly within Odoo.
            The module includes an online booking form on your website where customers can submit cleaning service requests with their preferred date, shift, and time slot. Logged-in customers have their details automatically filled in, making the booking process quick and convenient.
            It also supports recurring cleaning services where customers can schedule regular cleanings on a daily, weekly, or monthly basis. The system automatically validates the end date based on the selected interval to ensure accurate scheduling.
            The module provides a built-in availability checker that allows managers to verify which employees and cleaning teams are available for a specific date, shift, and time slot before making an assignment, preventing scheduling conflicts.
            It also allows configuring cleaning shifts, time slots, and holidays so the booking calendar always reflects real working availability. Customers can only select valid dates, avoiding bookings on off days or holidays.
            The module includes role-based access control where cleaning managers can only view and manage bookings assigned to them, while administrators have full visibility over all bookings across the business.
            Additionally, the module sends automatic email notifications to assigned managers whenever a new booking is assigned to them, ensuring timely communication and eliminating the need for manual follow-up.
            This solution ensures efficient booking management, streamlined staff scheduling, and smooth communication between customers and the cleaning team within Odoo.

            Cleaning Service Booking & Management
            Cleaning Business Management
            Cleaning Booking Management
            Cleaning Staff Management
            Cleaning Appointment & Booking System
            Cleaning Team & Shift Management
            Odoo Cleaning Business Management Solution
            Cleaning Service Scheduler for Odoo
            Cleaning Company Management
            Odoo Cleaning Service Booking
            Cleaning Service Management & Online Booking System
            Housekeeping Service Booking & Staff Scheduling 
            Odoo Cleaning Service Management System''',
    'license': 'OPL-1',
    'description': "",

    # Dependencies
    'depends': ['website', 'sale_timesheet'],

    # Views
    'data': [
        'data/service_type_data.xml',
        'data/cleaning_shift_data.xml',
        'data/project_data.xml',
        'data/email_template.xml',
        'data/website_menu.xml',
        'security/access_booking_request.xml',
        'security/ir.access.csv',
        'views/booking_request_view.xml',
        'views/service_type_vts_view.xml',
        'views/cleaning_shift_view.xml',
        'views/cleaning_team_view.xml',
        'views/project_task_view.xml',
        'views/hr_employee_view.xml',
        'views/booking_dashboard_view.xml',
        'views/website_cleaning.xml',
        'views/cleaning_holiday_view.xml',
        'views/empl_availability_view.xml',
    ],

    'assets': {
        'web.assets_backend': [
            'https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js',
            'cleaning_service_management_vts/static/src/js/dashboard.js',
            'cleaning_service_management_vts/static/src/xml/dashboard.xml',
            'cleaning_service_management_vts/static/src/css/dashboard.css',
        ],

        'web.assets_frontend': [
            'cleaning_service_management_vts/static/src/lib/jquery-ui/jquery-ui.css',
            'cleaning_service_management_vts/static/src/lib/jquery-ui/jquery-ui.js',
            'cleaning_service_management_vts/static/src/css/cleaning_form.css',
            'cleaning_service_management_vts/static/src/js/cleaning_form.js',
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
    'demo': [],
    'installable': True,
    'application': True,
    'auto_install': False,
    'price': '199',
    'currency': 'EUR',
}
