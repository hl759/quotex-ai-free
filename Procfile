web: gunicorn --workers 1 --threads 2 --bind 0.0.0.0:$PORT --timeout 180 --keep-alive 5 --max-requests 200 --max-requests-jitter 20 app:app
