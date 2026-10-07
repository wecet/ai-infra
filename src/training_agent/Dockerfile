FROM python:3.12-slim
WORKDIR /app
COPY src/training_agent/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY libs/ai_interfaces /tmp/ai_interfaces
RUN pip install --no-cache-dir /tmp/ai_interfaces && rm -rf /tmp/ai_interfaces
COPY src/training_agent/app.py ./app.py
COPY src/training_agent/workbenches.py ./workbenches.py
EXPOSE 8090
HEALTHCHECK --interval=20s --timeout=3s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8090/health', timeout=2)"
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8090"]
