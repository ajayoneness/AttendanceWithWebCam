# attendance/views.py
import os
import cv2
import json
import numpy as np
import face_recognition
from django.conf import settings
from django.http import HttpResponse, FileResponse
from rest_framework.views import APIView
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework import status
from rest_framework.response import Response
from .models import Student, Attendance
from .serializers import StudentSerializer, AttendanceSerializer
from django.utils import timezone
from io import BytesIO
import openpyxl
from reportlab.pdfgen import canvas

class StudentCreateAPIView(APIView):
    parser_classes = (MultiPartParser, FormParser)

    def post(self, request, format=None):
        serializer = StudentSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

def process_video_file(video_path):
    # Load all students with a computed face encoding.
    students = Student.objects.exclude(face_encoding__isnull=True)
    known_encodings = []
    student_mapping = []  # parallel list to known_encodings
    for student in students:
        try:
            encoding_list = json.loads(student.face_encoding)
            known_enc = np.array(encoding_list)
            known_encodings.append(known_enc)
            student_mapping.append(student)
        except Exception as e:
            print(f"Error loading encoding for {student}: {e}")

    recognized_students = set()
    video_capture = cv2.VideoCapture(video_path)
    frame_count = 0
    while True:
        ret, frame = video_capture.read()
        if not ret:
            break
        frame_count += 1
        # Process every 10th frame (for performance).
        if frame_count % 10 != 0:
            continue
        rgb_frame = frame[:, :, ::-1]  # convert from BGR to RGB
        face_locations = face_recognition.face_locations(rgb_frame)
        face_encodings = face_recognition.face_encodings(rgb_frame, face_locations)
        for face_encoding in face_encodings:
            matches = face_recognition.compare_faces(known_encodings, face_encoding, tolerance=0.6)
            if True in matches:
                first_match_index = matches.index(True)
                student = student_mapping[first_match_index]
                recognized_students.add(student)
    video_capture.release()
    # Mark attendance (only once per day).
    today = timezone.now().date()
    for student in recognized_students:
        if not Attendance.objects.filter(student=student, date=today).exists():
            Attendance.objects.create(student=student)
    return recognized_students

class AttendanceUploadAPIView(APIView):
    parser_classes = (MultiPartParser, FormParser)
    
    def post(self, request, format=None):
        video_file = request.FILES.get('video')
        if not video_file:
            return Response({"error": "No video file provided."}, status=status.HTTP_400_BAD_REQUEST)
        
        # Save the uploaded video temporarily.
        video_path = os.path.join(settings.MEDIA_ROOT, 'temp_video.mp4')
        with open(video_path, 'wb+') as destination:
            for chunk in video_file.chunks():
                destination.write(chunk)
        try:
            recognized_students = process_video_file(video_path)
            student_names = [student.name for student in recognized_students]
            os.remove(video_path)  # Clean up the temporary file.
            return Response({"message": "Attendance marked.", "students": student_names}, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class AttendanceReportAPIView(APIView):
    def get(self, request, format=None):
        attendances = Attendance.objects.all().order_by('-timestamp')
        serializer = AttendanceSerializer(attendances, many=True)
        return Response(serializer.data)

class AttendanceExcelExportAPIView(APIView):
    def get(self, request, format=None):
        attendances = Attendance.objects.all().order_by('date')
        workbook = openpyxl.Workbook()
        sheet = workbook.active
        sheet.title = "Attendance Report"
        # Header row.
        sheet.append(["Student Name", "Student ID", "Date", "Timestamp"])
        for attendance in attendances:
            sheet.append([
                attendance.student.name,
                attendance.student.student_id,
                attendance.date.strftime("%Y-%m-%d"),
                attendance.timestamp.strftime("%Y-%m-%d %H:%M:%S")
            ])
        stream = BytesIO()
        workbook.save(stream)
        stream.seek(0)
        response = HttpResponse(
            stream,
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        response['Content-Disposition'] = 'attachment; filename="attendance_report.xlsx"'
        return response

class AttendancePDFExportAPIView(APIView):
    def get(self, request, format=None):
        attendances = Attendance.objects.all().order_by('date')
        buffer = BytesIO()
        p = canvas.Canvas(buffer)
        p.setFont("Helvetica", 12)
        y = 800
        p.drawString(50, y, "Attendance Report")
        y -= 30
        headers = "Student Name | Student ID | Date | Timestamp"
        p.drawString(50, y, headers)
        y -= 20
        for attendance in attendances:
            line = f"{attendance.student.name} | {attendance.student.student_id} | {attendance.date.strftime('%Y-%m-%d')} | {attendance.timestamp.strftime('%H:%M:%S')}"
            p.drawString(50, y, line)
            y -= 20
            if y < 50:
                p.showPage()
                y = 800
        p.showPage()
        p.save()
        buffer.seek(0)
        return FileResponse(buffer, as_attachment=True, filename='attendance_report.pdf')
