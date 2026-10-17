FROM python:3.12-slim
WORKDIR /app
COPY src/training_agent/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
# CPU wheels keep the default demo image small; GPU agents can override the index.
ARG PYTORCH_INDEX_URL=https://download.pytorch.org/whl/cpu
COPY src/training_agent/requirements-pytorch.txt ./requirements-pytorch.txt
RUN pip install --no-cache-dir -r requirements-pytorch.txt --index-url ${PYTORCH_INDEX_URL}
COPY libs/ai_interfaces /tmp/ai_interfaces
RUN pip install --no-cache-dir /tmp/ai_interfaces && rm -rf /tmp/ai_interfaces
COPY src/training_agent/app.py ./app.py
COPY src/training_agent/workbenches.py ./workbenches.py
COPY src/training_agent/jobs.py src/training_agent/evaluation.py src/training_agent/preview.py src/training_agent/isolated_worker.py ./
EXPOSE 8090
HEALTHCHECK --interval=20s --timeout=3s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8090/health', timeout=2)"
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8090"]
