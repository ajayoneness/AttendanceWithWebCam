from django.db import models
import face_recognition
import json
import numpy as np

class Student(models.Model):
    name = models.CharField(max_length=100)
    student_id = models.CharField(max_length=50, unique=True)
    phone = models.CharField(max_length=15)
    email = models.EmailField(unique=True)
    profile_image = models.ImageField(upload_to='profile_images/')
    face_encoding = models.TextField(blank=True, null=True)  # stored as a JSON list

    def save(self, *args, **kwargs):
        # Save first to ensure profile_image file exists.
        super().save(*args, **kwargs)
        # If the face encoding is not yet set, compute it.
        if self.profile_image and not self.face_encoding:
            try:
                image = face_recognition.load_image_file(self.profile_image.path)
                encodings = face_recognition.face_encodings(image)
                if encodings:
                    encoding = encodings[0]
                    self.face_encoding = json.dumps(encoding.tolist())
                    super().save(update_fields=['face_encoding'])
            except Exception as e:
                print(f"Error computing face encoding for {self.name}: {e}")

    def __str__(self):
        return self.name

class Attendance(models.Model):
    student = models.ForeignKey(Student, on_delete=models.CASCADE)
    date = models.DateField(auto_now_add=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.student.name} - {self.date}"
