import base64
import os
import urllib.request
import cv2
from deepface import DeepFace
from flask import (
    Blueprint,
    current_app,
    flash,
    jsonify,
    redirect,
    request,
    render_template,
    url_for,
)
import numpy as np
import ssl

from app import db
from app.models import Student  

att_bp = Blueprint("att", __name__)

@att_bp.route('/', methods=['GET'])
def attendance_page():
    return render_template("attendance/attandance_wth_face.html")


@att_bp.route("/verify", methods=["POST"])  # Cleaned up to only need POST
def verify_face():
    data = request.json
    if not data or "image" not in data:
        return jsonify({"status": "error", "message": "Missing image data"}), 400

    try:
        # 1. Fetch all students from the database
        students = Student.query.all()
        if not students:
            return jsonify({"status": "error", "message": "No students found in database."}), 404

        # 2. Decode the incoming base64 webcam image frame
        image_data = data["image"].split(",")[1]
        image_bytes = base64.b64decode(image_data)

        # Convert bytes to an OpenCV image array
        nparr = np.frombuffer(image_bytes, np.uint8)
        current_frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

        # 3. Loop through students to find a face match
        # ... inside your verify_face() route ...
        for student in students:
            cloudinary_url = student.face_photo_path
            if not cloudinary_url:
                continue

            try:
                # 2. Create a context that ignores certificate validation errors
                context = ssl._create_unverified_context()

                # 3. Pass the context directly into urlopen
                with urllib.request.urlopen(cloudinary_url, context=context) as url_response:
                    cloudinary_img_bytes = np.asarray(bytearray(url_response.read()), dtype=np.uint8)
                    reference_image = cv2.imdecode(cloudinary_img_bytes, cv2.IMREAD_COLOR)


                    # Perform Face Verification with DeepFace
                    result = DeepFace.verify(
                        img1_path=reference_image,
                        img2_path=current_frame,
                        enforce_detection=False,
                    )

                if result["verified"]:
                    distance = float(result["distance"])
                    threshold = float(result["threshold"])
                    confidence = max(0, min(100, (1 - (distance / threshold)) * 100))

                    return jsonify(
                        {
                            "status": "success",
                            "match": True,
                            "student_id": student.id,
                            "student_name": getattr(student, "name_kana", "Unknown"),
                            "message": f"Face verified! Welcome, {getattr(student, 'name', 'Student')}.",
                            "confidence": f"{confidence:.1f}%",
                        }
                    )

            except Exception as e:
                current_app.logger.warning(
                    f"Failed matching for student {student.id}: {str(e)}"
                )
                continue

        # 4. If loop finishes without returning, no match found
        return jsonify(
            {
                "status": "success",
                "match": False,
                "message": "Access denied: Face does not match any registered student.",
            }
        )

    except Exception as e:
        return jsonify({"status": "error", "message": f"Processing error: {str(e)}"}), 500