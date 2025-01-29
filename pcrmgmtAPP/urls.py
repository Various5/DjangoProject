# DjangoProject\pcrmgmtAPP\urls.py

from django.urls import path
from . import views
from django.contrib.auth.views import LoginView, LogoutView
from django.conf.urls.static import static
from django.conf import settings
urlpatterns = [
    path('', views.dashboard, name='dashboard'),

    # ISL Logs
    path('isl-logs/', views.isl_logs, name='isl_logs'),
    path('isl-logs/edit/<str:log_id>/', views.edit_isl_log, name='edit_isl_log'),
    path('isl-logs/delete/<str:log_id>/', views.delete_isl_log, name='delete_isl_log'),
    path('isl-logs/print/<str:log_id>/', views.print_isl_log, name='print_isl_log'),
    path('isl-logs/pdf/<str:log_id>/', views.download_isl_pdf, name='download_isl_pdf'),
    path('isl-logs/toggle-verrechnet/<str:log_id>/', views.toggle_verrechnet, name='toggle_verrechnet'),

    # Office Accounts
    path('office-accounts/', views.office_accounts, name='office_accounts'),
    path('office-accounts/edit/<int:account_id>/', views.edit_account, name='edit_account'),
    path('office-accounts/delete/<int:account_id>/', views.delete_account, name='delete_account'),
    path('office-accounts/print/<int:account_id>/', views.print_account, name='print_account'),
    path('office-accounts/pdf/<int:account_id>/', views.download_pdf, name='download_pdf'),

    # Garantie Tracker
    path('garantie-tracker/', views.garantie_tracker, name='garantie_tracker'),

    # Settings
    path('settings/', views.settings_view, name='settings'),

    # Tasks
    path('tasks/', views.tasks_view, name='tasks'),

    # Logs
    path('logs/', views.logs, name='logs'),

    # Report generation (ISL)
    path('isl-logs/report/', views.generate_report, name='generate_report'),
    path('isl-logs/api/logs/', views.api_logs, name='api_logs'),  # optional leftover

    path('database-status/', views.database_status, name='database_status'),

    # Registration / Auth
    path('accounts/register/', views.register, name='register'),
    path('accounts/login/', LoginView.as_view(template_name='registration/login.html'), name='login'),
    path('accounts/logout/', LogoutView.as_view(next_page='/'), name='logout'),
    path('accounts/profile/', views.profile, name='profile'),

    # Garantie CRUD
    path('garantie/', views.garantie_list, name='garantie_list'),
    path('garantie/create/', views.garantie_create, name='garantie_create'),
    path('garantie/update/<int:pk>/', views.garantie_update, name='garantie_update'),
    path('garantie/delete/<int:pk>/', views.garantie_delete, name='garantie_delete'),

    # RMA Manager
    path('rma-manager/', views.rma_manager_selection, name='rma_manager'),
    path('rma-manager/general/', views.general_rma, name='general_rma'),
    path('rma-manager/computacenter/', views.computacenter_rma, name='computacenter_rma'),
    path('rma-manager/logs/', views.rma_logs, name='rma_logs'),
    path('tasks/start-rma-email-import/', views.start_rma_email_import, name='start_rma_email_import'),  # if you use it

    # Ticket actions
    path('rma/ticket/<int:ticket_id>/close/', views.close_ticket_view, name='close_ticket_view'),
    path('rma/ticket/<int:ticket_id>/reopen/', views.reopen_ticket_view, name='reopen_ticket_view'),
    path('rma/ticket/<int:ticket_id>/edit/', views.edit_ticket, name='edit_ticket'),
    path('rma/ticket/<int:ticket_id>/delete/', views.delete_ticket, name='delete_ticket'),
    path('rma/ticket/<int:ticket_id>/print/', views.print_ticket, name='print_ticket'),
    path('rma/ticket/<int:ticket_id>/pdf/', views.pdf_ticket, name='pdf_ticket'),

    # GData Accounts
    path('gdata-accounts/', views.gdata_accounts, name='gdata_accounts'),
    path('gdata-accounts/edit/<int:account_id>/', views.edit_gdata_account, name='edit_gdata_account'),
    path('gdata-accounts/delete/<int:account_id>/', views.delete_gdata_account, name='delete_gdata_account'),
    path('gdata-accounts/toggle-email-sent/<int:account_id>/', views.toggle_email_sent, name='toggle_email_sent'),
    path('gdata-accounts/update-license/<int:account_id>/', views.update_license, name='update_license'),
    # Add other paths like edit, delete, etc.
    path('autocomplete/address/', views.autocomplete_address, name='autocomplete_address'),
    path('autocomplete/customer/', views.autocomplete_customer, name='autocomplete_customer'),
    path('maintenance/', views.maintenance_dashboard, name='maintenance_dashboard'),

    # Maintenance
    path('maintenance/', views.maintenance_dashboard, name='maintenance_dashboard'),

    # Maintenance Config
    path('maintenance/configs/', views.config_list, name='maintenance_config_list'),
    path('maintenance/configs/create/', views.config_create, name='maintenance_config_create'),
    path('maintenance/configs/<int:pk>/edit/', views.config_edit, name='maintenance_config_edit'),
    path('maintenance/configs/<int:pk>/delete/', views.config_delete, name='maintenance_config_delete'),

    # Neu hinzugefügt, damit der "Report"-Button nicht ins Leere führt:
    path('maintenance/configs/<int:pk>/report/', views.maintenance_report_pdf, name='maintenance_report'),

    # Maintenance Tasks
    path('maintenance/tasks/', views.task_list, name='maintenance_task_list'),
    path('maintenance/tasks/<int:task_id>/detail/', views.task_detail, name='maintenance_task_detail'),
    path('maintenance/tasks/<int:task_id>/claim/', views.task_claim_details,
         name='maintenance_task_claim_details'),
    path('maintenance/tasks/<int:task_id>/complete/', views.maintenance_task_complete,
         name='maintenance_task_complete'),
    path('maintenance/tasks/<int:task_id>/delete/', views.task_delete, name='task_delete'),
    path('maintenance/tasks/create/', views.task_create, name='task_create'),
    path('maintenance/full_create/', views.maintenance_full_create, name='maintenance_full_create'),
    path('maintenance/overview/', views.maintenance_overview, name='maintenance_overview'),
    path('maintenance/tasks/<int:task_id>/pdf/', views.maintenance_task_pdf, name='maintenance_task_pdf'),

]
urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
