# pcrmgmtAPP/urls.py

from django.urls import path
from . import views
from django.contrib.auth.views import LoginView, LogoutView

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('isl-logs/', views.isl_logs, name='isl_logs'),
    path('isl-logs/edit/<str:log_id>/', views.edit_isl_log, name='edit_isl_log'),
    path('isl-logs/delete/<str:log_id>/', views.delete_isl_log, name='delete_isl_log'),
    path('isl-logs/print/<str:log_id>/', views.print_isl_log, name='print_isl_log'),
    path('isl-logs/pdf/<str:log_id>/', views.download_isl_pdf, name='download_isl_pdf'),
    path('isl-logs/toggle-verrechnet/<str:log_id>/', views.toggle_verrechnet, name='toggle_verrechnet'),
    path('autocomplete/customer/', views.autocomplete_customer, name='autocomplete_customer'),
    path('office-accounts/', views.office_accounts, name='office_accounts'),
    path('office-accounts/edit/<int:account_id>/', views.edit_account, name='edit_account'),
    path('office-accounts/delete/<int:account_id>/', views.delete_account, name='delete_account'),
    path('office-accounts/print/<int:account_id>/', views.print_account, name='print_account'),
    path('office-accounts/pdf/<int:account_id>/', views.download_pdf, name='download_pdf'),
    path('gdata-accounts/', views.gdata_accounts, name='gdata_accounts'),
    path('garantie-tracker/', views.garantie_tracker, name='garantie_tracker'),
    path('settings/', views.settings_view, name='settings'),
    path('tasks/', views.tasks_view, name='tasks'),
    path('logs/', views.logs, name='logs'),
    path('isl-logs/report/', views.generate_report, name='generate_report'),  # Report generation
    path('isl-logs/api/logs/', views.api_logs, name='api_logs'),  # New API endpoint
    path('database-status/', views.database_status, name='database_status'),
    path('accounts/register/', views.register, name='register'),
    path('accounts/login/', LoginView.as_view(template_name='registration/login.html'), name='login'),
    path('accounts/logout/', LogoutView.as_view(next_page='/'), name='logout'),
    path('accounts/profile/', views.profile, name='profile'),
    path('garantie/', views.garantie_list, name='garantie_list'),
    path('garantie/create/', views.garantie_create, name='garantie_create'),
    path('garantie/update/<int:pk>/', views.garantie_update, name='garantie_update'),
    path('garantie/delete/<int:pk>/', views.garantie_delete, name='garantie_delete'),

    # RMA Manager
    path('rma-manager/', views.rma_manager_selection, name='rma_manager'),
    path('rma-manager/general/', views.general_rma, name='general_rma'),
    path('rma-manager/computacenter/', views.computacenter_rma, name='computacenter_rma'),
    path('rma-manager/logs/', views.rma_logs, name='rma_logs'),
    path('tasks/start-rma-email-import/', views.start_rma_email_import, name='start_rma_email_import'),

    # ------ New Ticket Actions ------
    path('rma/ticket/<int:ticket_id>/close/', views.close_ticket_view, name='close_ticket_view'),
    path('rma/ticket/<int:ticket_id>/reopen/', views.reopen_ticket_view, name='reopen_ticket_view'),
    path('rma/ticket/<int:ticket_id>/edit/', views.edit_ticket, name='edit_ticket'),
    path('rma/ticket/<int:ticket_id>/delete/', views.delete_ticket, name='delete_ticket'),
    path('rma/ticket/<int:ticket_id>/print/', views.print_ticket, name='print_ticket'),
    path('rma/ticket/<int:ticket_id>/pdf/', views.pdf_ticket, name='pdf_ticket'),
]
