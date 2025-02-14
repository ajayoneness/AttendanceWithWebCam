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
from .models import Student, Attendance  # Update with correct import path
from .serializers import StudentSerializer, AttendanceSerializer
from django.utils import timezone
from io import BytesIO
import openpyxl
from reportlab.pdfgen import canvas
import logging
import tempfile
from collections import defaultdict



logger = logging.getLogger(__name__)

class StudentCreateAPIView(APIView):
    parser_classes = (MultiPartParser, FormParser)

    def post(self, request, format=None):
        serializer = StudentSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class StudentListAPIView(APIView):
    def get(self, request, format=None):
        students = Student.objects.all()
        serializer = StudentSerializer(students, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)



class AttendanceUploadAPIView(APIView):
    parser_classes = (MultiPartParser, FormParser)
    
    def post(self, request, format=None):
        temp_path = None
        try:
            video_file = request.FILES.get('video')
            if not video_file:
                return Response({"error": "No video file provided."}, status=status.HTTP_400_BAD_REQUEST)
            
            # Validate video file
            max_size = 50 * 1024 * 1024  # 50 MB
            if video_file.size > max_size:
                return Response(
                    {"error": "Video file is too large. Maximum allowed size is 50 MB."},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Use temporary file with automatic cleanup
            with tempfile.NamedTemporaryFile(delete=False, suffix=".mp4") as tmp_file:
                for chunk in video_file.chunks():
                    tmp_file.write(chunk)
                temp_path = tmp_file.name

            recognized_students = self.process_video(temp_path)
            return Response(
                {"message": "Attendance marked.", "students": [s.name for s in recognized_students]},
                status=status.HTTP_200_OK
            )
            
        except Exception as e:
            logger.error(f"Error processing video request: {str(e)}", exc_info=True)
            return Response({"error": "Internal server error"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        finally:
            if temp_path and os.path.exists(temp_path):
                try:
                    os.unlink(temp_path)
                    logger.info(f"Temporary file {temp_path} deleted")
                except PermissionError:
                    logger.warning(f"Could not delete temporary file {temp_path}, retrying...")
                    # Add retry logic or async cleanup if needed

    def process_video(self, video_path):
        video_capture = None
        try:
            video_capture = cv2.VideoCapture(video_path)
            if not video_capture.isOpened():
                raise ValueError(f"Could not open video file: {video_path}")

            # Get cached encodings
            known_encodings, student_mapping = self.get_cached_encodings()
            recognized_students = set()

            # Video processing parameters
            frame_skip = 5  # Process every 5th frame
            target_width = 640  # Reduced resolution
            confidence_threshold = 0.5
            max_processing_seconds = 30

            frame_count = 0
            start_time = timezone.now()

            while True:
                if (timezone.now() - start_time).seconds > max_processing_seconds:
                    logger.warning("Exceeded maximum processing time")
                    break

                ret, frame = video_capture.read()
                if not ret:
                    break

                frame_count += 1
                if frame_count % frame_skip != 0:
                    continue

                # Resize frame
                height, width = frame.shape[:2]
                if width > target_width:
                    scale = target_width / width
                    frame = cv2.resize(frame, (int(width * scale), int(height * scale)))

                # Convert to RGB
                rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

                # Face detection
                face_locations = face_recognition.face_locations(rgb_frame, model="hog")
                if not face_locations:
                    continue

                # Process face encodings
                face_encodings = face_recognition.face_encodings(rgb_frame, face_locations)
                for face_encoding in face_encodings:
                    face_distances = face_recognition.face_distance(known_encodings, face_encoding)
                    best_match_index = np.argmin(face_distances)
                    
                    if face_distances[best_match_index] < confidence_threshold:
                        recognized_students.add(student_mapping[best_match_index])

            self.create_attendance_records(recognized_students)
            return recognized_students

        except Exception as e:
            logger.error(f"Video processing error: {str(e)}", exc_info=True)
            raise
        finally:
            if video_capture:
                video_capture.release()

    @staticmethod
    def get_cached_encodings():
        if not hasattr(settings, 'FACE_ENCODINGS_CACHE'):
            students = Student.objects.exclude(face_encoding__isnull=True).only('id', 'name', 'face_encoding')
            encodings = []
            mapping = []
            
            for student in students:
                try:
                    encoding = np.array(json.loads(student.face_encoding))
                    encodings.append(encoding)
                    mapping.append(student)
                except (TypeError, json.JSONDecodeError) as e:
                    logger.warning(f"Invalid encoding for student {student.id}: {str(e)}")
            
            settings.FACE_ENCODINGS_CACHE = (encodings, mapping)
            logger.info("Loaded and cached face encodings")
        
        return settings.FACE_ENCODINGS_CACHE

    @staticmethod
    def create_attendance_records(students):
        today = timezone.now().date()
        existing = set(Attendance.objects.filter(
            date=today, 
            student__in=students
        ).values_list('student_id', flat=True))

        new_attendance = [
            Attendance(student=student, date=today)
            for student in students
            if student.id not in existing
        ]

        if new_attendance:
            Attendance.objects.bulk_create(new_attendance)
            logger.info(f"Created {len(new_attendance)} new attendance records")






# def process_video_file(video_path):
#     # Load all students with a computed face encoding.
#     students = Student.objects.exclude(face_encoding__isnull=True)
#     known_encodings = []
#     student_mapping = []  # parallel list to known_encodings
#     for student in students:
#         try:
#             encoding_list = json.loads(student.face_encoding)
#             known_enc = np.array(encoding_list)
#             known_encodings.append(known_enc)
#             student_mapping.append(student)
#         except Exception as e:
#             print(f"Error loading encoding for {student}: {e}")

#     recognized_students = set()
#     video_capture = cv2.VideoCapture(video_path)
#     frame_count = 0
#     while True:
#         ret, frame = video_capture.read()
#         if not ret:
#             break
#         frame_count += 1
#         # Process every 10th frame (for performance).
#         if frame_count % 10 != 0:
#             continue
#         rgb_frame = frame[:, :, ::-1]  # convert from BGR to RGB
#         face_locations = face_recognition.face_locations(rgb_frame)
#         face_encodings = face_recognition.face_encodings(rgb_frame, face_locations)
#         for face_encoding in face_encodings:
#             matches = face_recognition.compare_faces(known_encodings, face_encoding, tolerance=0.6)
#             if True in matches:
#                 first_match_index = matches.index(True)
#                 student = student_mapping[first_match_index]
#                 recognized_students.add(student)
#     video_capture.release()
#     # Mark attendance (only once per day).
#     today = timezone.now().date()
#     for student in recognized_students:
#         if not Attendance.objects.filter(student=student, date=today).exists():
#             Attendance.objects.create(student=student)
#     return recognized_students

# class AttendanceUploadAPIView(APIView):
#     parser_classes = (MultiPartParser, FormParser)
    
#     def post(self, request, format=None):
#         video_file = request.FILES.get('video')
#         if not video_file:
#             return Response({"error": "No video file provided."}, status=status.HTTP_400_BAD_REQUEST)
        
#         # Save the uploaded video temporarily.
#         video_path = os.path.join(settings.MEDIA_ROOT, 'temp_video.mp4')
#         with open(video_path, 'wb+') as destination:
#             for chunk in video_file.chunks():
#                 destination.write(chunk)
#         try:
#             recognized_students = process_video_file(video_path)
#             student_names = [student.name for student in recognized_students]
#             os.remove(video_path)  # Clean up the temporary file.
#             return Response({"message": "Attendance marked.", "students": student_names}, status=status.HTTP_200_OK)
#         except Exception as e:
#             return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)




class AttendanceReportAPIView(APIView):
    def get(self, request, format=None):
        attendances = Attendance.objects.all().order_by('-timestamp')
        serializer = AttendanceSerializer(attendances, many=True)
        return Response(serializer.data)

# class AttendanceExcelExportAPIView(APIView):
#     def get(self, request, format=None):
#         attendances = Attendance.objects.all().order_by('date')
#         workbook = openpyxl.Workbook()
#         sheet = workbook.active
#         sheet.title = "Attendance Report"
#         # Header row.
#         sheet.append(["Student Name", "Student ID", "Date", "Timestamp"])
#         for attendance in attendances:
#             sheet.append([
#                 attendance.student.name,
#                 attendance.student.student_id,
#                 attendance.date.strftime("%Y-%m-%d"),
#                 attendance.timestamp.strftime("%Y-%m-%d %H:%M:%S")
#             ])
#         stream = BytesIO()
#         workbook.save(stream)
#         stream.seek(0)
#         response = HttpResponse(
#             stream,
#             content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
#         )
#         response['Content-Disposition'] = 'attachment; filename="attendance_report.xlsx"'
#         return response

# class AttendancePDFExportAPIView(APIView):
#     def get(self, request, format=None):
#         attendances = Attendance.objects.all().order_by('date')
#         buffer = BytesIO()
#         p = canvas.Canvas(buffer)
#         p.setFont("Helvetica", 12)
#         y = 800
#         p.drawString(50, y, "Attendance Report")
#         y -= 30
#         headers = "Student Name | Student ID | Date | Timestamp"
#         p.drawString(50, y, headers)
#         y -= 20
#         for attendance in attendances:
#             line = f"{attendance.student.name} | {attendance.student.student_id} | {attendance.date.strftime('%Y-%m-%d')} | {attendance.timestamp.strftime('%H:%M:%S')}"
#             p.drawString(50, y, line)
#             y -= 20
#             if y < 50:
#                 p.showPage()
#                 y = 800
#         p.showPage()
#         p.save()
#         buffer.seek(0)
#         return FileResponse(buffer, as_attachment=True, filename='attendance_report.pdf')







class AttendanceExcelExportAPIView(APIView):
    def get(self, request, format=None):
        attendances = Attendance.objects.all().order_by('date')
        
        # Deduplicate entries by student and date
        unique_entries = {}
        for attendance in attendances:
            key = (attendance.student.id, attendance.date)
            if key not in unique_entries:
                unique_entries[key] = attendance
        unique_attendances = list(unique_entries.values())
        
        # Calculate attendance statistics
        unique_dates = {att.date for att in unique_attendances}
        total_dates = len(unique_dates)
        
        # Collect student data
        student_data = defaultdict(lambda: {
            'name': None,
            'student_id': None,
            'count': 0,
            'percentage': 0.0
        })
        
        for att in unique_attendances:
            student = att.student
            student_data[student.id]['name'] = student.name
            student_data[student.id]['student_id'] = student.student_id
            student_data[student.id]['count'] += 1
        
        # Calculate percentages
        for student_id, data in student_data.items():
            if total_dates > 0:
                data['percentage'] = (data['count'] / total_dates) * 100
            else:
                data['percentage'] = 0.0
        
        # Calculate overall average
        percentages = [data['percentage'] for data in student_data.values()]
        average_percentage = sum(percentages) / len(percentages) if percentages else 0.0
        
        # Generate Excel report
        workbook = openpyxl.Workbook()
        sheet = workbook.active
        sheet.title = "Attendance Report"
        
        # Main data header
        sheet.append(["Student Name", "Student ID", "Date", "Timestamp"])
        
        # Data rows
        for attendance in unique_attendances:
            sheet.append([
                attendance.student.name,
                attendance.student.student_id,
                attendance.date.strftime("%Y-%m-%d"),
                attendance.timestamp.strftime("%Y-%m-%d %H:%M:%S")
            ])
        
        # Student summary section
        sheet.append([])
        sheet.append(["Student Attendance Summary"])
        sheet.append(["Student Name", "Student ID", "Days Present", "Attendance Percentage"])
        
        for data in student_data.values():
            sheet.append([
                data['name'],
                data['student_id'],
                data['count'],
                f"{data['percentage']:.2f}%"
            ])
        
        # Overall average
        sheet.append([])
        sheet.append(["Overall Average Attendance Percentage", f"{average_percentage:.2f}%"])
        
        # Prepare response
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
        
        # Deduplicate entries by student and date
        unique_entries = {}
        for attendance in attendances:
            key = (attendance.student.id, attendance.date)
            if key not in unique_entries:
                unique_entries[key] = attendance
        unique_attendances = list(unique_entries.values())
        
        # Calculate attendance statistics
        unique_dates = {att.date for att in unique_attendances}
        total_dates = len(unique_dates)
        
        student_counts = defaultdict(int)
        for att in unique_attendances:
            student_counts[att.student.id] += 1
        
        # Calculate overall average attendance percentage
        percentages = []
        for count in student_counts.values():
            if total_dates > 0:
                percentage = (count / total_dates) * 100
            else:
                percentage = 0.0
            percentages.append(percentage)
        overall_average_percentage = sum(percentages) / len(percentages) if percentages else 0.0
        
        # Generate PDF report
        buffer = BytesIO()
        p = canvas.Canvas(buffer)
        p.setFont("Helvetica", 12)
        y = 800  # Starting Y position
        
        # Header for attendance details
        p.drawString(50, y, "Attendance Report")
        y -= 30
        p.drawString(50, y, "Student Name | Student ID | Date | Timestamp")
        y -= 30
        
        # Attendance data rows
        for attendance in unique_attendances:
            if y < 50:  # Add new page if needed
                p.showPage()
                y = 800
                p.setFont("Helvetica", 12)
            
            line = f"{attendance.student.name} | {attendance.student.student_id} | {attendance.date.strftime('%Y-%m-%d')} | {attendance.timestamp.strftime('%Y-%m-%d %H:%M:%S')}"
            p.drawString(50, y, line)
            y -= 20
        
        # Display overall average attendance percentage
        if y < 100:
            p.showPage()
            y = 800
            p.setFont("Helvetica", 12)
        p.drawString(50, y, f"Overall Average Attendance Percentage: {overall_average_percentage:.2f}%")
        y -= 30
        
        # Individual student averages section header
        p.drawString(50, y, "Individual Student Averages:")
        y -= 30
        p.drawString(50, y, "Student Name | Student ID | Attendance Count | Attendance Percentage")
        y -= 30
        
        # Data rows for individual student averages
        for student_id, count in student_counts.items():
            if y < 50:
                p.showPage()
                y = 800
                p.setFont("Helvetica", 12)
            
            student_name = next(
                (att.student.name for att in unique_attendances if att.student.id == student_id),
                "N/A"
            )
            student_percentage = (count / total_dates * 100) if total_dates > 0 else 0.0
            line = f"{student_name} | {student_id} | {count} | {student_percentage:.2f}%"
            p.drawString(50, y, line)
            y -= 20
        
        p.showPage()
        p.save()
        buffer.seek(0)
        return FileResponse(buffer, as_attachment=True, filename='attendance_report.pdf')








logger = logging.getLogger(__name__)

class AttendanceImageUploadAPIView(APIView):
    parser_classes = (MultiPartParser, FormParser)
    
    def post(self, request, format=None):
        try:
            image_file = request.FILES.get('image')
            if not image_file:
                return Response({"error": "No image file provided."}, status=status.HTTP_400_BAD_REQUEST)
            
            # Validate image size
            max_size = 10 * 1024 * 1024  # 10 MB
            if image_file.size > max_size:
                return Response(
                    {"error": "Image file is too large. Maximum allowed size is 10 MB."},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Process image in memory without saving to disk
            image_data = image_file.read()
            recognized_students = self.process_image(image_data)
            
            return Response(
                {"message": "Attendance marked.", "students": [s.name for s in recognized_students]},
                status=status.HTTP_200_OK
            )
            
        except Exception as e:
            logger.error(f"Error processing request: {str(e)}", exc_info=True)
            return Response({"error": "Internal server error"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def process_image(self, image_data):
        try:
            # Load image from bytes
            image = cv2.imdecode(np.frombuffer(image_data, np.uint8), cv2.IMREAD_COLOR)
            if image is None:
                raise ValueError("Invalid image file")

            # Resize large images for faster processing
            max_dimension = 2000
            height, width = image.shape[:2]
            if max(height, width) > max_dimension:
                scale = max_dimension / max(height, width)
                image = cv2.resize(image, (int(width * scale), int(height * scale)))

            # Convert to RGB
            rgb_image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)

            # Get pre-loaded encodings
            known_encodings, student_mapping = self.get_cached_encodings()

            # Detect faces
            face_locations = face_recognition.face_locations(rgb_image, model="hog")
            logger.info(f"Detected {len(face_locations)} faces")

            # Process encodings
            recognized_students = set()
            for encoding in face_recognition.face_encodings(rgb_image, face_locations):
                matches = face_recognition.compare_faces(known_encodings, encoding, tolerance=0.5)
                face_distances = face_recognition.face_distance(known_encodings, encoding)
                
                # Get best match instead of first match
                best_match_index = np.argmin(face_distances)
                if matches[best_match_index]:
                    recognized_students.add(student_mapping[best_match_index])

            # Create attendance records
            self.create_attendance_records(recognized_students)
            
            return recognized_students

        except Exception as e:
            logger.error(f"Image processing error: {str(e)}", exc_info=True)
            raise

    @staticmethod
    def get_cached_encodings():
        # Cache encodings to avoid database hits on every request
        if not hasattr(settings, 'FACE_ENCODINGS_CACHE'):
            students = Student.objects.exclude(face_encoding__isnull=True).only('id', 'name', 'face_encoding')
            encodings = []
            mapping = []
            
            for student in students:
                try:
                    encoding = np.array(json.loads(student.face_encoding))
                    encodings.append(encoding)
                    mapping.append(student)
                except (TypeError, json.JSONDecodeError) as e:
                    logger.warning(f"Invalid encoding for student {student.id}: {str(e)}")
            
            settings.FACE_ENCODINGS_CACHE = (encodings, mapping)
            logger.info("Loaded and cached face encodings")
        
        return settings.FACE_ENCODINGS_CACHE

    @staticmethod
    def create_attendance_records(students):
        today = timezone.now().date()
        existing = set(Attendance.objects.filter(
            date=today, 
            student__in=students
        ).values_list('student_id', flat=True))

        new_attendance = [
            Attendance(student=student, date=today)
            for student in students
            if student.id not in existing
        ]

        if new_attendance:
            Attendance.objects.bulk_create(new_attendance)
            logger.info(f"Created {len(new_attendance)} new attendance records")