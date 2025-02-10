# attendance/urls.py
from django.urls import path
from .views import (
    StudentCreateAPIView,
    AttendanceUploadAPIView,
    AttendanceReportAPIView,
    AttendanceExcelExportAPIView,
    AttendancePDFExportAPIView,
)

urlpatterns = [
    path('students/', StudentCreateAPIView.as_view(), name='student-create'),
    path('attendance/upload/', AttendanceUploadAPIView.as_view(), name='attendance-upload'),
    path('attendance/report/', AttendanceReportAPIView.as_view(), name='attendance-report'),
    path('attendance/export/excel/', AttendanceExcelExportAPIView.as_view(), name='attendance-export-excel'),
    path('attendance/export/pdf/', AttendancePDFExportAPIView.as_view(), name='attendance-export-pdf'),
]
