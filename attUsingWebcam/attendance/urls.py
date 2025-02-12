# attendance/urls.py
from django.urls import path
from .views import (
    StudentCreateAPIView,
    AttendanceUploadAPIView,
    AttendanceReportAPIView,
    AttendanceExcelExportAPIView,
    AttendancePDFExportAPIView,
    AttendanceImageUploadAPIView,
    StudentListAPIView,
)

urlpatterns = [
    path('students/', StudentCreateAPIView.as_view(), name='student-create'),
    path('studentslist/', StudentListAPIView.as_view(), name='student-list'),
    path('attendance/upload/', AttendanceUploadAPIView.as_view(), name='attendance-upload'),
    path('attendance/report/', AttendanceReportAPIView.as_view(), name='attendance-report'),
    path('attendance/export/excel/', AttendanceExcelExportAPIView.as_view(), name='attendance-export-excel'),
    path('attendance/export/pdf/', AttendancePDFExportAPIView.as_view(), name='attendance-export-pdf'),
    path('attendance/image-upload/', AttendanceImageUploadAPIView.as_view(), name='attendance-export-pdf'),
]
